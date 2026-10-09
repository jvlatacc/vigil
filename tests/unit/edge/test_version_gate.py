"""The per-node monotonic version gate — anti-replay for policy packs."""

from __future__ import annotations

import json

from core.edge.policy import (
    VersionState,
    check_policy_version,
    load_policy_pack,
    parse_policy,
)
from core.edge.signing import deterministic_json

from .helpers import NOW, default_root, generate_key, policy_doc, sign_policy


def _state(doc: dict | None = None) -> VersionState:
    payload = deterministic_json(doc or policy_doc())
    parsed = parse_policy(payload, now=NOW)
    assert parsed.ok and parsed.pack is not None
    return parsed.pack.version_state()


class TestVersionGate:
    def test_fresh_node_accepts_any_version(self):
        newer = _state(policy_doc(version=42))
        assert check_policy_version(None, newer).ok

    def test_newer_version_is_accepted(self):
        state = _state(policy_doc(version=41))
        newer = _state(policy_doc(version=42))
        assert check_policy_version(state, newer).ok

    def test_node_holding_v42_refuses_v41(self):
        state = _state(policy_doc(version=42))
        older = _state(policy_doc(version=41))
        check = check_policy_version(state, older)
        assert not check.ok and check.codes == {"P-VERSION-REPLAY"}

    def test_node_holding_v1_refuses_a_v1_fork(self):
        state = _state(policy_doc(version=1))
        fork = _state(
            policy_doc(
                version=1,
                envelope={
                    # Schema-legal fork: same version, widened rate cap —
                    # different bytes under the same version number.
                    "allowed_actions": ["block_ip"],
                    "max_actions_per_hour": 999,
                    "max_action_ttl_minutes": 30,
                    "require_reversible": True,
                    "confidence_floor": 0.9,
                    "allow_slm_decisions": False,
                },
            )
        )
        check = check_policy_version(state, fork)
        assert not check.ok and check.codes == {"P-VERSION-FORK"}

    def test_replay_of_much_older_version_is_refused(self):
        state = _state(policy_doc(version=42))
        older = _state(policy_doc(version=7))
        assert check_policy_version(state, older).codes == {"P-VERSION-REPLAY"}

    def test_same_version_different_payload_hash_is_a_fork(self):
        state = _state(policy_doc(version=42))
        fork = VersionState(42, "d" * 64)
        check = check_policy_version(state, fork)
        assert not check.ok and check.codes == {"P-VERSION-FORK"}

    def test_represented_v42_with_identical_bytes_is_a_resync(self):
        state = _state(policy_doc(version=42))
        check = check_policy_version(state, state)
        assert check.ok and check.same_pack

    def test_fork_refusal_names_the_stored_hash(self):
        state = _state(policy_doc(version=42))
        fork = VersionState(42, "a" * 64)
        check = check_policy_version(state, fork)
        assert state.payload_hash[:12] in check.errors[0][1]


class TestVersionGateInChain:
    """The gate as load_policy_pack applies it, against signed bytes."""

    def test_signed_downgrade_is_refused(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        v42 = sign_policy(policy_doc(version=42), [key])
        v41 = sign_policy(policy_doc(version=41), [key])
        first = load_policy_pack(v42, root, now=NOW)
        assert first.ok and first.pack is not None
        # An attacker re-serves an old, still-validly-signed pack:
        replay = load_policy_pack(v41, root, now=NOW, state=first.pack.version_state())
        assert not replay.ok and replay.codes == {"P-VERSION-REPLAY"}

    def test_signed_fork_of_same_version_is_refused(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        a = sign_policy(policy_doc(version=42), [key])
        b = sign_policy(
            policy_doc(
                version=42,
                envelope={
                    # Schema-legal fork: same version, widened rate cap.
                    "allowed_actions": ["block_ip"],
                    "max_actions_per_hour": 999,
                    "max_action_ttl_minutes": 30,
                    "require_reversible": True,
                    "confidence_floor": 0.9,
                    "allow_slm_decisions": False,
                },
            ),
            [key],
        )
        first = load_policy_pack(a, root, now=NOW)
        assert first.ok
        second = load_policy_pack(b, root, now=NOW, state=first.pack.version_state())
        assert not second.ok and second.codes == {"P-VERSION-FORK"}

    def test_resync_of_identical_pack_succeeds(self):
        key = generate_key()
        root = default_root(policy_keys=[key])
        data = sign_policy(policy_doc(version=42), [key])
        first = load_policy_pack(data, root, now=NOW)
        second = load_policy_pack(data, root, now=NOW, state=first.pack.version_state())
        assert second.ok and second.pack == first.pack

    def test_version_state_survives_a_roundtrip_through_json(self):
        """The node persists its version state between syncs — serialization
        must not lose the payload hash."""
        state = _state(policy_doc(version=42))
        revived = VersionState(
            **json.loads(
                json.dumps(
                    {"version": state.version, "payload_hash": state.payload_hash}
                )
            )
        )
        assert revived == state
