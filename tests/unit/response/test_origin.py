"""The origin verifier decides exactly what the Medic verifier decides (#944).

Mirroring ``services/medic/contracts/trust_check.py`` is deliberate (the
import fence keeps the verifiers apart), so parity is proven on the same
inputs rather than trusted from a comment: the same PAE bytes, the same
strict-JSON refusals, and the same verdicts on tampered, unregistered,
revoked, expired and oversized envelopes.
"""

import json
from types import SimpleNamespace

import pytest

from core.response.guards_config import GuardConfigError
from core.response.origin import (
    EXPECTED_PAYLOAD_TYPES,
    MAX_IAT_AGE_SECONDS,
    MAX_IAT_FUTURE_SKEW_SECONDS,
    OriginConfigError,
    OriginReplayCache,
    OriginTrustIndex,
    attestation_covers,
    pae,
    verify_attestation,
)
from tests.security._origin_factory import (
    FINDING,
    NOW,
    Signer,
    b64,
    medic_envelope,
    medic_keyid,
    medic_root,
    medic_trust_check,
)

pytestmark = pytest.mark.unit

FINDING_BYTES = json.dumps(FINDING).encode()


# The default roots belong to this signer, so tests that sign with "the
# default origin" verify against the same key instead of a random one.
_DEFAULT_SIGNER = Signer()


def _default_roots() -> dict:
    return OriginTrustIndex.from_entries([_DEFAULT_SIGNER.trust_entry()]).roots


def _verify(header, roots=None, **kwargs):
    data = header.encode() if isinstance(header, str) else header
    return verify_attestation(
        data,
        roots if roots is not None else _default_roots(),
        now=NOW,
        **kwargs,
    )


# --- Parity with the Medic verifier -----------------------------------------


def test_the_pae_encoding_is_byte_for_byte_the_medic_encoding():
    trust_check = medic_trust_check()
    for payload_type, payload in [
        ("https://vigil.example/schemas/finding/v1", FINDING_BYTES),
        ("application/vnd.deeptempo.medic.pack.v1+json", b"x" * 37),
        ("", b""),
    ]:
        assert pae(payload_type, payload) == trust_check.pae(payload_type, payload)


def test_duplicate_json_keys_fail_both_verifiers():
    trust_check = medic_trust_check()
    signer = Signer()
    root = medic_root(
        signer.trust_entry()["public_key"],
        medic_keyid(signer.trust_entry()["public_key"]),
        payload_types=(trust_check.PACK,),
    )
    mine = (
        b'{"payload_type": "a", "payload_type": "b",'
        b' "payload": "", "signatures": []}'
    )
    assert _verify(mine.decode()).codes == {"O-JSON"}
    theirs = (
        b'{"payloadType": "a", "payloadType": "b",' b' "payload": "", "signatures": []}'
    )
    verdict = trust_check.verify_envelope(
        theirs, root, expected={trust_check.PACK}, now=NOW
    )
    assert verdict.codes == {"S-JSON"}


def test_a_non_standard_json_constant_fails_both_verifiers():
    # NaN parses in Python's json by default; both verifiers must refuse it,
    # because a NaN confidence would read as "not a real number" downstream.
    trust_check = medic_trust_check()
    signer = Signer()
    root = medic_root(
        signer.trust_entry()["public_key"],
        medic_keyid(signer.trust_entry()["public_key"]),
        payload_types=(trust_check.PACK,),
    )
    assert _verify(
        b'{"payload_type": "x", "payload": "aGk=", "signatures": [], "extra": NaN}'
    ).codes == {"O-JSON"}
    verdict = trust_check.verify_envelope(
        b'{"payloadType": "x", "payload": "aGk=", "signatures": [], "extra": NaN}',
        root,
        expected={trust_check.PACK},
        now=NOW,
    )
    assert verdict.codes == {"S-JSON"}


def test_a_flipped_payload_byte_fails_both_verifiers():
    trust_check = medic_trust_check()
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry()]).roots

    tampered = json.loads(signer.sign_finding(iat=int(NOW.timestamp())))
    tampered["payload"] = b64(FINDING_BYTES[:-1] + bytes([FINDING_BYTES[-1] ^ 0x01]))
    assert _verify(json.dumps(tampered), roots).codes == {"O-SIG"}

    public_b64 = signer.trust_entry()["public_key"]
    root = medic_root(
        public_b64, medic_keyid(public_b64), payload_types=(trust_check.PACK,)
    )
    medic_payload = b'{"pack": "contents", "n": 1}'
    envelope = json.loads(
        medic_envelope(signer, medic_payload, payload_type=trust_check.PACK)
    )
    envelope["payload"] = b64(medic_payload[:-1] + bytes([medic_payload[-1] ^ 0x01]))
    verdict = trust_check.verify_envelope(
        json.dumps(envelope).encode(), root, expected={trust_check.PACK}, now=NOW
    )
    assert "S-SIG" in verdict.codes


def test_an_unregistered_key_fails_both_verifiers():
    trust_check = medic_trust_check()
    signer = Signer()
    attacker = Signer(origin_id="impostor-01")

    assert _verify(attacker.sign_finding(iat=int(NOW.timestamp()))).codes == {
        "O-UNKNOWN"
    }

    public_b64 = signer.trust_entry()["public_key"]
    root = medic_root(
        public_b64, medic_keyid(public_b64), payload_types=(trust_check.PACK,)
    )
    envelope = medic_envelope(
        attacker,
        b"{}",
        payload_type=trust_check.PACK,
        keyid=medic_keyid(attacker.trust_entry()["public_key"]),
    )
    verdict = trust_check.verify_envelope(
        envelope, root, expected={trust_check.PACK}, now=NOW
    )
    assert "S-SCOPE" in verdict.codes


def test_a_disabled_origin_fails_like_a_medic_revoked_key():
    trust_check = medic_trust_check()
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry(enabled=False)]).roots
    assert _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots).codes == {
        "O-REVOKED"
    }

    public_b64 = signer.trust_entry()["public_key"]
    kid = medic_keyid(public_b64)
    root = medic_root(
        public_b64, kid, payload_types=(trust_check.PACK,), revoked=(kid,)
    )
    envelope = medic_envelope(signer, b"{}", payload_type=trust_check.PACK)
    verdict = trust_check.verify_envelope(
        envelope, root, expected={trust_check.PACK}, now=NOW
    )
    assert "S-REVOKED" in verdict.codes


def test_an_expired_key_fails_both_verifiers():
    trust_check = medic_trust_check()
    signer = Signer()
    roots = OriginTrustIndex.from_entries(
        [signer.trust_entry(not_after="2026-01-01T00:00:00+00:00")]
    ).roots
    assert _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots).codes == {
        "O-KEY-EXPIRED"
    }

    public_b64 = signer.trust_entry()["public_key"]
    root = medic_root(
        public_b64,
        medic_keyid(public_b64),
        payload_types=(trust_check.PACK,),
        key_not_after="2026-01-01T00:00:00Z",
    )
    envelope = medic_envelope(signer, b"{}", payload_type=trust_check.PACK)
    verdict = trust_check.verify_envelope(
        envelope, root, expected={trust_check.PACK}, now=NOW
    )
    assert "S-KEY-EXPIRED" in verdict.codes


def test_an_oversized_envelope_fails_both_verifiers(monkeypatch):
    trust_check = medic_trust_check()
    signer = Signer()
    monkeypatch.setattr("core.response.origin.MAX_ATTESTATION_BYTES", 64)
    assert _verify(signer.sign_finding(iat=int(NOW.timestamp()))).codes == {"O-SIZE"}

    monkeypatch.setattr(trust_check, "MAX_ENVELOPE_BYTES", 64)
    public_b64 = signer.trust_entry()["public_key"]
    root = medic_root(
        public_b64, medic_keyid(public_b64), payload_types=(trust_check.PACK,)
    )
    envelope = medic_envelope(signer, b"x" * 200, payload_type=trust_check.PACK)
    verdict = trust_check.verify_envelope(
        envelope, root, expected={trust_check.PACK}, now=NOW
    )
    assert "S-SIZE" in verdict.codes


def test_a_correctly_signed_medic_envelope_verifies():
    # The positive case for the parity fixtures: if this stopped holding, the
    # shared fixture builder broke and every parity reject above is suspect.
    trust_check = medic_trust_check()
    signer = Signer()
    public_b64 = signer.trust_entry()["public_key"]
    root = medic_root(
        public_b64, medic_keyid(public_b64), payload_types=(trust_check.PACK,)
    )
    envelope = medic_envelope(
        signer, b'{"pack": "contents"}', payload_type=trust_check.PACK
    )
    verdict = trust_check.verify_envelope(
        envelope, root, expected={trust_check.PACK}, now=NOW
    )
    assert verdict.ok
    assert verdict.payload == b'{"pack": "contents"}'


# --- The origin verifier's own behavior -------------------------------------


def test_a_registered_origin_stamps_its_finding():
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry()]).roots
    verdict = _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots)
    assert verdict.ok
    assert verdict.origin_id == signer.origin_id
    assert verdict.payload == FINDING_BYTES
    assert verdict.nonces == ["01J-TEST-NONCE-0001"]


def test_a_payload_type_vigil_does_not_accept_is_refused():
    signer = Signer()
    header = signer.sign_finding(
        iat=int(NOW.timestamp()), payload_type="https://evil.example/finding"
    )
    assert _verify(header).codes == {"O-TYPE"}


@pytest.mark.parametrize(
    "mutate, code",
    [
        (lambda env: env.pop("payload_type"), "O-ENVELOPE"),
        (lambda env: env.pop("payload"), "O-ENVELOPE"),
        (lambda env: env.pop("signatures"), "O-ENVELOPE"),
        (lambda env: env.__setitem__("signatures", []), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].pop("keyid"), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].pop("sig"), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].pop("jti"), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].__setitem__("iat", True), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].__setitem__("iat", 1.5), "O-ENVELOPE"),
        (lambda env: env["signatures"][0].__setitem__("jti", ""), "O-ENVELOPE"),
    ],
)
def test_a_structurally_broken_envelope_is_refused(mutate, code):
    signer = Signer()
    env = json.loads(signer.sign_finding(iat=int(NOW.timestamp())))
    mutate(env)
    assert _verify(json.dumps(env)).codes == {code}


def test_payload_that_is_not_base64_is_refused():
    signer = Signer()
    env = json.loads(signer.sign_finding(iat=int(NOW.timestamp())))
    env["payload"] = "not base64 !!"
    assert _verify(json.dumps(env)).codes == {"O-ENVELOPE"}


def test_a_scope_mismatch_is_refused_when_a_scope_is_required():
    signer = Signer()
    roots = OriginTrustIndex.from_entries(
        [signer.trust_entry(scope="auto_response")]
    ).roots
    header = signer.sign_finding(iat=int(NOW.timestamp()))
    assert _verify(header, roots, required_scope="auto_response").ok
    assert _verify(header, roots, required_scope="threat_feed").codes == {"O-SCOPE"}


def test_a_wildcard_scope_covers_any_required_scope():
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry(scope="*")]).roots
    header = signer.sign_finding(iat=int(NOW.timestamp()))
    assert _verify(header, roots, required_scope="auto_response").ok


def test_an_iat_older_than_300_seconds_is_stale():
    signer = _DEFAULT_SIGNER
    fresh = signer.sign_finding(iat=int(NOW.timestamp()) - MAX_IAT_AGE_SECONDS)
    stale = signer.sign_finding(iat=int(NOW.timestamp()) - MAX_IAT_AGE_SECONDS - 1)
    assert _verify(fresh).ok
    assert _verify(stale).codes == {"O-STALE"}


def test_an_iat_too_far_in_the_future_is_refused():
    signer = _DEFAULT_SIGNER
    within = signer.sign_finding(iat=int(NOW.timestamp()) + MAX_IAT_FUTURE_SKEW_SECONDS)
    beyond = signer.sign_finding(
        iat=int(NOW.timestamp()) + MAX_IAT_FUTURE_SKEW_SECONDS + 1
    )
    assert _verify(within).ok
    assert _verify(beyond).codes == {"O-CLOCK"}


def test_a_naive_now_is_read_as_utc():
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry()]).roots
    verdict = verify_attestation(
        signer.sign_finding(iat=int(NOW.timestamp())).encode(),
        roots,
        now=NOW.replace(tzinfo=None),
    )
    assert verdict.ok


def test_an_empty_root_registry_verifies_nothing():
    signer = Signer()
    verdict = _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots={})
    assert verdict.codes == {"O-UNKNOWN"}
    assert verdict.payload is None


# --- Trust-root entries ------------------------------------------------------


def _settings(**overrides):
    signer = Signer()
    base = dict(
        daemon_containment_quotas_enabled=True,
        daemon_subnet_scope_prefix=24,
        daemon_containment_quota_subnet_pct_per_min=5.0,
        daemon_containment_quota_global_per_min=30,
        daemon_containment_quota_global_per_hour=200,
        daemon_breaker_cooldown_seconds=900,
        daemon_breaker_invariant_probe_trip=3,
        daemon_breaker_origin_flood_trip=10,
        daemon_protected_assets="[]",
        daemon_trusted_origins=json.dumps([signer.trust_entry()]),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_the_index_bridges_daemon_trusted_origins():
    index = OriginTrustIndex.from_settings(_settings())
    assert len(index) == 1
    assert index.scope_of("sensor-edge-01") == "*"


def test_an_unknown_origin_has_no_scope():
    assert OriginTrustIndex.empty().scope_of("nobody") is None


@pytest.mark.parametrize(
    "entry, expected_fragment",
    [
        (["not-a-dict"], "expected a JSON object"),
        ([{}], "origin_id"),
        ([{"origin_id": "  ", "public_key": "aWgv"}], "origin_id"),
        ([{"origin_id": "x"}], "public_key"),
        ([{"origin_id": "x", "public_key": "!!!"}], "not decodable base64"),
        ([{"origin_id": "x", "public_key": b64(b"short")}], "32-byte"),
        ([{"origin_id": "x", "public_key": b64(b"x" * 32), "scope": ""}], "scope"),
        (
            [{"origin_id": "x", "public_key": b64(b"x" * 32), "enabled": "true"}],
            "enabled",
        ),
        (
            [
                {
                    "origin_id": "x",
                    "public_key": b64(b"x" * 32),
                    "not_after": "yesterday",
                }
            ],
            "not_after",
        ),
    ],
)
def test_a_misconfigured_origin_entry_refuses_to_load(entry, expected_fragment):
    with pytest.raises(OriginConfigError) as excinfo:
        OriginTrustIndex.from_entries(entry)
    assert expected_fragment in str(excinfo.value)
    assert "daemon_trusted_origins" in str(excinfo.value)


def test_a_misconfigured_seed_list_refuses_to_load():
    # Seed-list JSON parsing is GuardConfig territory (shared with the other
    # Feature 7 knobs); origin-specific validation is OriginConfigError.
    with pytest.raises((GuardConfigError, OriginConfigError)):
        OriginTrustIndex.from_settings(_settings(daemon_trusted_origins="[not json"))


def test_duplicate_origin_ids_refuse_to_load():
    signer = Signer()
    with pytest.raises(OriginConfigError) as excinfo:
        OriginTrustIndex.from_entries([signer.trust_entry(), signer.trust_entry()])
    assert "duplicate" in str(excinfo.value)


# --- Binding the verified payload to the ingested body -----------------------


def test_the_attestation_covers_the_body_it_stamps():
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry()]).roots
    verdict = _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots)
    assert attestation_covers(verdict, FINDING)
    # The sender may serialize differently between signing and transport.
    reordered = dict(reversed(list(FINDING.items())))
    assert attestation_covers(verdict, reordered)


def test_an_attestation_for_different_content_covers_nothing():
    signer = Signer()
    roots = OriginTrustIndex.from_entries([signer.trust_entry()]).roots
    verdict = _verify(signer.sign_finding(iat=int(NOW.timestamp())), roots)
    other = {**FINDING, "finding_id": "webhook-other"}
    assert not attestation_covers(verdict, other)
    assert not attestation_covers(verdict, [FINDING])


def test_a_failed_verdict_covers_nothing():
    verdict = verify_attestation(b"not json", {}, now=NOW)
    assert not attestation_covers(verdict, FINDING)


# --- Replay cache ------------------------------------------------------------


async def test_a_nonce_is_a_replay_the_second_time():
    cache = OriginReplayCache()
    assert await cache.seen_or_record("jti-1") is False
    assert await cache.seen_or_record("jti-1") is True
    assert await cache.seen_or_record("jti-2") is False


async def test_an_empty_nonce_is_never_a_replay():
    cache = OriginReplayCache()
    assert await cache.seen_or_record("") is False


def test_the_expected_payload_type_is_the_finding_schema():
    assert EXPECTED_PAYLOAD_TYPES == frozenset(
        {"https://vigil.example/schemas/finding/v1"}
    )
