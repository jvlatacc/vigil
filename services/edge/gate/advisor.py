"""The SLM advisor — an advisory classifier, never the final authority.

Calls the local model through Ollama (or any OpenAI-compatible endpoint — the
paved road, R§3) with one structured-output request per observation. The
verdict enters the gate as confidence only; the model process never receives
credentials, and its output is never evidence of compromise by itself (W).
Single-shot by design: no tool round-trips, no agentic loop.

Blocking HTTP: callers run classify() via asyncio.to_thread so the event loop
never stalls behind a slow local model.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Literal

import httpx

from services.edge.gate.gate import SlmVerdict
from services.edge.observations.base import Observation
from services.edge.policy.model import Rule

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_VERSION = "edge-advisor-v1"

SYSTEM_PROMPT = (
    "You classify one network observation for a defensive gate. Reply with "
    'only a JSON object: {"classification": "malicious" | "benign" | '
    '"uncertain", "confidence": <float 0..1>, "evidence": "<short reason>"}. '
    "Confidence is your certainty the observation is malicious. You advise; "
    "a deterministic gate decides."
)

CLASSIFICATIONS = ("malicious", "benign", "uncertain")
MAX_EVIDENCE_CHARS = 200


@dataclass(frozen=True)
class AdvisorConfig:
    base_url: str
    model: str
    api: Literal["ollama", "openai"] = "ollama"
    timeout_s: float = 5.0


class SlmAdvisor:
    def __init__(
        self,
        config: AdvisorConfig,
        *,
        model_digest: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.model_digest = model_digest
        self._client = httpx.Client(
            base_url=config.base_url, timeout=config.timeout_s, transport=transport
        )

    def classify(
        self, observation: Observation, rule: Rule | None
    ) -> SlmVerdict | None:
        """None on transport failure — the advisor being down is survivable
        by design, and the gate runs deterministic-only. A response that
        cannot be parsed into a usable verdict comes back as a verdict with
        wellformed=False (same degradation, but recorded as model output)."""
        try:
            content = self._complete(observation, rule)
        except httpx.HTTPError as exc:
            logger.warning(
                "SLM advisor unreachable (%s): %s", self.config.base_url, exc
            )
            return None
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("SLM response unusable: %s", exc)
            return _malformed(self.config.model, self.model_digest)
        return _parse_verdict(
            content, model_id=self.config.model, model_digest=self.model_digest
        )

    def close(self) -> None:
        self._client.close()

    def _complete(self, observation: Observation, rule: Rule | None) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_payload(observation, rule)},
        ]
        if self.config.api == "ollama":
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            return str(response.json()["message"]["content"])
        response = self._client.post(  # OpenAI-compatible endpoint
            "/v1/chat/completions",
            json={"model": self.config.model, "messages": messages, "temperature": 0},
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])


def _user_payload(observation: Observation, rule: Rule | None) -> str:
    return json.dumps(
        {
            "event_type": observation.event_type,
            "direction": observation.direction,
            "dest_ip": observation.dest_ip,
            "dest_domain": observation.dest_domain,
            "proto": observation.proto,
            "matched_rule": rule.rule_id if rule else None,
        }
    )


def _malformed(model_id: str, model_digest: str) -> SlmVerdict:
    return SlmVerdict(
        confidence=0.0,
        model_id=model_id,
        model_digest=model_digest,
        classification="uncertain",
        evidence="",
        wellformed=False,
    )


def _parse_verdict(content: str, *, model_id: str, model_digest: str) -> SlmVerdict:
    """Structured output, strictly: strip code fences, parse, validate shape.
    Anything off -> wellformed=False; the gate then runs deterministic-only."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        return _malformed(model_id, model_digest)
    if not isinstance(parsed, dict):
        return _malformed(model_id, model_digest)
    classification = parsed.get("classification")
    raw_confidence = parsed.get("confidence")
    if classification not in CLASSIFICATIONS:
        return _malformed(model_id, model_digest)
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
        return _malformed(model_id, model_digest)
    value = float(raw_confidence)
    if math.isnan(value) or math.isinf(value):
        return _malformed(model_id, model_digest)
    evidence = parsed.get("evidence", "")
    if not isinstance(evidence, str):
        return _malformed(model_id, model_digest)
    return SlmVerdict(
        confidence=min(1.0, max(0.0, value)),
        model_id=model_id,
        model_digest=model_digest,
        classification=classification,
        evidence=evidence[:MAX_EVIDENCE_CHARS],
        wellformed=True,
    )
