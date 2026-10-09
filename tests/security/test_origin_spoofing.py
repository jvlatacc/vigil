"""Spoofing attacks against origin attestation, end to end (#944).

Each test is an attack an adversary who controls sensor traffic can run
against a daemon with registered trust roots: not verifier properties (the
unit suite in tests/unit/response/test_origin.py owns those) but the spoofs
the guard chain exists to stop. The pipeline each attack faces is the one the
webhook runs — verify against trust roots, reject replayed nonces, require
the verified payload to be the body — so a verdict here is a verdict about
the stamp a finding would actually carry.
"""

from __future__ import annotations

import json
import time

import pytest

from core.response.origin import (
    O_COVERAGE,
    O_REPLAY,
    O_SIG,
    O_STALE,
    O_TYPE,
    O_UNKNOWN,
    OriginReplayCache,
    OriginTrustIndex,
    attestation_covers,
)
from tests.security._origin_factory import Signer


@pytest.fixture
def registry() -> Signer:
    """A daemon with one registered sensor and a fixed verification clock."""
    return Signer(origin_id="sensor-edge-01")


def _index(signer: Signer) -> OriginTrustIndex:
    return OriginTrustIndex.from_entries([signer.trust_entry()])


async def _stamp(
    index: OriginTrustIndex,
    header: str,
    body,
    *,
    replay: OriginReplayCache | None = None,
) -> tuple[bool, frozenset[str] | None]:
    """The webhook's stamp pipeline: verify, replay-check, bind, stamp."""
    verdict = index.verify(header.encode())
    if not verdict.ok:
        return False, verdict.codes
    replay = replay or OriginReplayCache()
    for jti in verdict.nonces:
        if await replay.seen_or_record(jti):
            return False, frozenset({O_REPLAY})
    if not attestation_covers(verdict, body):
        return False, frozenset({O_COVERAGE})
    return True, verdict.origin_id


async def test_a_transplanted_attestation_does_not_stamp_a_forged_finding(
    registry: Signer,
):
    """The attacker records a genuine attestation and posts it over a finding
    of their own making: the verified payload is not the body, no stamp."""
    victim = {"finding_id": "f-victim", "severity": "critical"}
    forged = {
        "finding_id": "f-dc",
        "severity": "critical",
        "entity_context": {"src_ips": ["10.0.0.53"]},
    }
    header = registry.sign_finding(victim)
    ok, codes = await _stamp(_index(registry), header, forged)
    assert ok is False
    assert codes == frozenset({O_COVERAGE})


async def test_a_captured_attestation_cannot_be_replayed(registry: Signer):
    """The attacker replays a sniffed attestation byte for byte: the nonce
    verifies once and never again."""
    body = {"finding_id": "f-1"}
    header = registry.sign_finding(body)
    replay = OriginReplayCache()
    ok, _ = await _stamp(_index(registry), header, body, replay=replay)
    assert ok is True
    ok, codes = await _stamp(_index(registry), header, body, replay=replay)
    assert ok is False
    assert codes == frozenset({O_REPLAY})


async def test_a_self_minted_key_is_not_a_registered_origin(registry: Signer):
    """The attacker generates their own Ed25519 key and signs: nothing is
    registered under their origin id, so nothing verifies."""
    attacker = Signer(origin_id="attacker-edge")
    header = attacker.sign_finding({"finding_id": "f-forged"})
    ok, codes = await _stamp(_index(registry), header, {"finding_id": "f-forged"})
    assert ok is False
    assert O_UNKNOWN in codes


async def test_a_key_cannot_borrow_a_registered_origin_id(registry: Signer):
    """The attacker signs with their own key but names a registered origin in
    the keyid: the registered key is not theirs, so the signature fails."""
    attacker = Signer(origin_id="attacker-edge")
    header = attacker.sign_finding({"finding_id": "f-forged"}, keyid="sensor-edge-01")
    ok, codes = await _stamp(_index(registry), header, {"finding_id": "f-forged"})
    assert ok is False
    assert codes == frozenset({O_SIG})


async def test_an_old_attestation_delivered_late_is_stale(registry: Signer):
    """The attacker stores a valid attestation and delivers it past the
    freshness window: the clock, not the key, refuses it."""
    body = {"finding_id": "f-late"}
    header = registry.sign_finding(body, iat=int(time.time()) - 3600)
    ok, codes = await _stamp(_index(registry), header, body)
    assert ok is False
    assert codes == frozenset({O_STALE})


async def test_appending_a_signature_poisons_the_whole_envelope(registry: Signer):
    """The attacker appends their own signature to a genuinely signed
    envelope, hoping partial credit: one bad signature fails everything —
    a result with a payload but also an error is never verified."""
    body = {"finding_id": "f-multi"}
    envelope = json.loads(registry.sign_finding(body))
    envelope["signatures"].append(
        {
            "keyid": "sensor-edge-01",
            "sig": "AAAAMCAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAw",  # attacker bytes
            "iat": int(time.time()),
            "jti": "01J-ATTACKER-NONCE-2",
        }
    )
    ok, codes = await _stamp(_index(registry), json.dumps(envelope), body)
    assert ok is False
    assert codes == frozenset({O_SIG})


async def test_a_one_field_mutation_breaks_the_stamp(registry: Signer):
    """The attacker alters one finding field — the IP the responder acts on —
    and keeps the original header: bytes changed, coverage fails."""
    body = {
        "finding_id": "f-mutate",
        "entity_context": {"src_ips": ["203.0.113.7"]},
    }
    header = registry.sign_finding(body)
    mutated = json.loads(json.dumps(body))
    mutated["entity_context"]["src_ips"] = ["10.0.0.53"]
    ok, codes = await _stamp(_index(registry), header, mutated)
    assert ok is False
    assert codes == frozenset({O_COVERAGE})


async def test_a_finding_envelope_cannot_pass_as_another_payload_type(
    registry: Signer,
):
    """The attacker rewraps a signed payload under a different payload type:
    the verifier accepts only the finding schema here."""
    body = {"finding_id": "f-type"}
    envelope = json.loads(registry.sign_finding(body))
    envelope["payload_type"] = "https://evil.example/schemas/finding/v1"
    ok, codes = await _stamp(_index(registry), json.dumps(envelope), body)
    assert ok is False
    assert codes == frozenset({O_TYPE})
