"""Verify-before-parse: a pack that should not verify is never parsed.

Ported from Medic's invalid-pack fixture classes (services/medic/contracts/
fixtures/packs/invalid/) with the edge content types. The property under test
is the ordering, not just the outcome: for every refusal the module makes,
the policy payload — tampered or not — does not reach ``parse_policy``.
"""

from __future__ import annotations

import json
from base64 import b64decode

import pytest

from core.edge import EDGE_POLICY, EDGE_TRUST_ROOT
from core.edge.policy import load_policy_pack, parse_policy
from core.edge.signing import deterministic_json, keyid_for, sign_envelope
from core.edge.verify import verify_envelope

from .helpers import (
    NOW,
    bake_root,
    build_root_doc,
    days,
    default_root,
    generate_key,
    policy_doc,
    sign_policy,
)


def _payload_bytes(envelope_bytes: bytes) -> bytes:
    """Decode the envelope's payload — what the parser would receive."""
    return b64decode(json.loads(envelope_bytes)["payload"])


class TestRejectedBeforeParsing:
    """Each rejection happens with the payload unparsed and unparsable."""

    def test_tampered_payload_is_refused_and_never_parsed(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(policy_doc(), [key])
        good = _payload_bytes(data)
        # Flip one character of the base64 payload: the signature no longer
        # covers it.
        start = data.index(b'"payload": "') + len(b'"payload": "')
        flipped = b"A" if data[start : start + 1] != b"A" else b"B"
        bad = data[:start] + flipped + data[start + 1 :]
        res = verify_envelope(bad, root, expected={EDGE_POLICY}, now=NOW)
        assert not res.ok and res.codes == {"S-SIG"}
        # The refused bytes never yield a pack:
        out = load_policy_pack(bad, root, now=NOW)
        assert out.pack is None and out.codes == {"S-SIG"}
        # The honest control still parses — proving the tamper is what broke
        # it, not a broken fixture:
        assert parse_policy(good, now=NOW).ok

    def test_expired_pack_is_refused(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(policy_doc(), [key])
        assert load_policy_pack(data, root, now=NOW).ok  # control
        out = load_policy_pack(data, root, now=NOW + days(30))
        assert out.pack is None and out.codes == {"P-EXPIRED"}

    def test_expired_signing_key_is_refused_before_parse(self):
        rk, pk = generate_key(), generate_key()
        doc = build_root_doc([rk], [pk])
        # The policy key died before the pack window even opens; the root
        # itself is still alive.
        doc["keys"][keyid_for(pk)]["not_after"] = "2026-10-01T00:00:00Z"
        root = bake_root(doc, [rk])
        data = sign_policy(policy_doc(), [pk])
        out = load_policy_pack(data, root, now=NOW)
        assert out.pack is None and out.codes == {"S-KEY-EXPIRED"}

    def test_unknown_signing_key_is_refused(self):
        root = default_root()  # root knows nothing about this key
        data = sign_policy(policy_doc(), [generate_key()])
        out = load_policy_pack(data, root, now=NOW)
        assert out.pack is None and out.codes == {"S-SCOPE"}

    def test_wrong_payload_type_is_refused(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(policy_doc(), [key])
        # Relabel the envelope as a trust root: the type-membership gate on
        # the envelope's payloadType field fires before any signature work,
        # without the payload being touched.
        env = json.loads(data)
        env["payloadType"] = EDGE_TRUST_ROOT
        out = load_policy_pack(json.dumps(env, indent=2).encode(), root, now=NOW)
        assert out.pack is None and out.codes == {"S-TYPE"}
        # And the other direction: valid bytes the caller does not accept here.
        res = verify_envelope(data, root, expected={EDGE_TRUST_ROOT}, now=NOW)
        assert res.codes == {"S-TYPE"} and res.payload is None

    def test_duplicate_keys_refused_after_signature_verifies(self):
        """The Medic duplicate-field class, adversarial edition: the poisoned
        pack carries a VALID signature by a key the root trusts, so the only
        thing standing between it and the parser is strict JSON."""
        key = generate_key()
        root = default_root(policy_keys=[key])
        payload = deterministic_json(policy_doc())
        poisoned = b'{"policy_version": 1, ' + payload[1:]
        assert poisoned.count(b'"policy_version"') == 2
        data = sign_envelope(poisoned, EDGE_POLICY, [key])
        # The signature verifies — the payload is exactly what was signed:
        assert verify_envelope(data, root, expected={EDGE_POLICY}, now=NOW).ok
        # …and the duplicate-key refusal is recorded at parse time:
        out = load_policy_pack(data, root, now=NOW)
        assert out.pack is None
        assert out.codes == {"P-JSON"} and "duplicate" in out.errors[0][1]

    def test_duplicate_keys_refused_by_the_wire_layer(self):
        from core.edge.wire import strict_json_loads

        with pytest.raises(ValueError, match="duplicate"):
            strict_json_loads(b'{"a": 1, "a": 2}')
        with pytest.raises(ValueError, match="duplicate"):
            strict_json_loads(b'{"policy_version": 1, "policy_version": 42, "b": []}')

    def test_trailing_data_is_refused(self):
        """Trailing DATA is refused; trailing whitespace is legal JSON."""
        from core.edge.wire import strict_json_loads

        with pytest.raises(ValueError, match="Extra data"):
            strict_json_loads(b'{"a": 1} {"b": 2}')
        assert strict_json_loads(b'{"a": 1}\n\n') == {"a": 1}

    def test_nan_confidence_is_refused_by_the_parser(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(
            policy_doc(
                envelope={
                    "allowed_actions": ["block_ip"],
                    "max_actions_per_hour": 5,
                    "max_action_ttl_minutes": 30,
                    "require_reversible": True,
                    "confidence_floor": 5.0,
                    "allow_slm_decisions": False,
                }
            ),
            [key],
        )
        out = load_policy_pack(data, root, now=NOW)
        # The approval_requirement precedent: out-of-range confidence never
        # reads as high — here it is a schema rejection, not a clamp.
        assert out.pack is None and out.codes == {"P-SCHEMA"}

    def test_unsigned_pack_is_refused(self):
        root = default_root()
        out = load_policy_pack(deterministic_json(policy_doc()), root, now=NOW)
        assert out.pack is None and out.codes == {"S-UNSIGNED"}

    def test_truncated_envelope_is_refused(self):
        root = default_root()
        data = sign_policy(policy_doc(), [generate_key()])
        out = load_policy_pack(data[: len(data) // 3], root, now=NOW)
        assert out.pack is None and out.codes == {"S-JSON"}

    def test_oversized_envelope_is_refused(self):
        root = default_root()
        out = load_policy_pack(b"x" * (1024 * 1024 + 1), root, now=NOW)
        assert out.pack is None and out.codes == {"S-SIZE"}

    def test_empty_signatures_is_a_recorded_shape_refusal(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        env = json.loads(sign_policy(policy_doc(), [key]))
        env["signatures"] = []
        out = load_policy_pack(json.dumps(env, indent=2).encode(), root, now=NOW)
        assert out.pack is None
        assert out.errors[0][0].startswith("S-") and out.errors[0][1]

    def test_parser_never_sees_payload_of_refused_envelope(self):
        """The ordering property itself: on a refused envelope, no document —
        not even the policy payload — is parsed by anything."""
        import core.edge.wire as wire

        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(policy_doc(), [key])
        seen: list[object] = []
        real_loads = json.loads

        def spy(*args, **kwargs):
            out = real_loads(*args, **kwargs)
            seen.append(out)
            return out

        orig = wire.json.loads
        wire.json.loads = spy  # type: ignore[assignment]
        try:
            env = json.loads(data)
            sig = env["signatures"][0]["sig"]
            env["signatures"][0]["sig"] = sig[:-4] + "AAAA"
            res = verify_envelope(
                json.dumps(env).encode(), root, expected={EDGE_POLICY}, now=NOW
            )
            assert res.codes == {"S-SIG"}
        finally:
            wire.json.loads = orig  # type: ignore[assignment]
        # The only thing json parsed was the envelope; no policy document —
        # a dict carrying a "format" key — was ever materialized:
        assert not any(isinstance(o, dict) and "format" in o for o in seen)
