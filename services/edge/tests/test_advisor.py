"""Advisor: structured-output parsing and transport-failure semantics."""

import json

import httpx

from services.edge.gate.advisor import AdvisorConfig, SlmAdvisor, _parse_verdict
from services.edge.tests._fixtures import make_bundle, make_observation

MODEL = "qwen2.5:1.5b"
DIGEST = "sha256:" + "b" * 64


def parse(content: str):
    return _parse_verdict(content, model_id=MODEL, model_digest=DIGEST)


def test_good_json_parses_with_digest_attribution() -> None:
    verdict = parse(
        '{"classification": "malicious", "confidence": 0.93, "evidence": "beacon"}'
    )
    assert verdict is not None
    assert verdict.wellformed
    assert verdict.confidence == 0.93
    assert verdict.model_id == MODEL
    assert verdict.model_digest == DIGEST  # the journal cites the exact model


def test_fenced_json_is_stripped() -> None:
    verdict = parse('```json\n{"classification": "benign", "confidence": 0.1}\n```')
    assert verdict is not None and verdict.wellformed
    assert verdict.classification == "benign"


def test_garbage_is_malformed() -> None:
    verdict = parse("I am unable to comply, human.")
    assert verdict is not None and not verdict.wellformed
    assert verdict.confidence == 0.0


def test_wrong_classification_key_is_malformed() -> None:
    assert parse('{"verdict": "malicious", "confidence": 0.9}').wellformed is False


def test_confidence_as_string_is_malformed() -> None:
    assert (
        parse('{"classification": "malicious", "confidence": "0.9"}').wellformed
        is False
    )


def test_nan_confidence_is_malformed() -> None:
    assert (
        parse('{"classification": "malicious", "confidence": NaN}').wellformed is False
    )


def test_out_of_range_confidence_clamps_into_unit_band() -> None:
    verdict = parse('{"classification": "malicious", "confidence": 1.7}')
    assert verdict is not None and verdict.wellformed
    assert verdict.confidence == 1.0


def test_non_string_evidence_is_malformed() -> None:
    assert (
        parse(
            '{"classification": "malicious", "confidence": 0.9, "evidence": 7}'
        ).wellformed
        is False
    )


def _ollama_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": content}})


def _advisor(handler) -> SlmAdvisor:
    config = AdvisorConfig(base_url="http://ollama.test", model=MODEL)
    return SlmAdvisor(
        config, model_digest=DIGEST, transport=httpx.MockTransport(handler)
    )


def test_classify_returns_verdict_on_ollama_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["format"] == "json"  # structured output requested
        assert body["messages"][0]["role"] == "system"
        return _ollama_response('{"classification": "malicious", "confidence": 0.97}')

    observation = make_observation()
    rule = make_bundle().match(observation)
    verdict = _advisor(handler).classify(observation, rule)
    assert verdict is not None and verdict.wellformed
    assert verdict.confidence == 0.97


def test_transport_failure_returns_none_gate_survives() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ollama down")

    verdict = _advisor(handler).classify(make_observation(), None)
    assert verdict is None


def test_http_500_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "gpu on fire"})

    verdict = _advisor(handler).classify(make_observation(), None)
    assert verdict is None


def test_wrong_json_shape_in_response_is_malformed_verdict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ollama_response("[1, 2, 3]")  # not an object

    verdict = _advisor(handler).classify(make_observation(), None)
    assert verdict is not None and not verdict.wellformed


def test_openai_compatible_shape_parses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"classification": "malicious", "confidence": 0.99}'
                        }
                    }
                ]
            },
        )

    config = AdvisorConfig(base_url="http://vllm.test", model=MODEL, api="openai")
    advisor = SlmAdvisor(
        config, model_digest=DIGEST, transport=httpx.MockTransport(handler)
    )
    verdict = advisor.classify(make_observation(), None)
    assert verdict is not None and verdict.wellformed
    assert verdict.confidence == 0.99
