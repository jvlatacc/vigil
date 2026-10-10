"""PolicySync tests: enroll, fetch, verify-before-parse, monotonic store.

Every control-plane interaction is respx-mocked. The tamper, replay, and
revocation paths are the point: a green fetch proves transport, not safety.
"""

from __future__ import annotations

from typing import Any

import httpx
import respx

from services.warden.storage import PolicyStore
from services.warden.sync import (
    S_AUTH,
    S_BAD_RESPONSE,
    S_HTTP,
    S_NO_CREDENTIALS,
    S_NO_POLICY,
    S_PAYLOAD_HASH,
    S_STORE_TAMPERED,
    S_TRANSPORT,
    PolicySync,
)
from tests.unit.warden.helpers import (
    WARDEN_NOW,
    FakeClock,
    make_pack_bytes,
    make_policy_key,
    make_root,
    policy_response_doc,
)

CP = "http://control-plane.test"


def make_sync(
    store: PolicyStore,
    root: dict,
    *,
    enrollment_token: str | None = None,
    clock: FakeClock | None = None,
    **overrides: Any,
) -> PolicySync:
    return PolicySync(
        trust_root=root,
        store=store,
        base_url=CP,
        enrollment_token=enrollment_token,
        clock=clock or FakeClock(),
        **overrides,
    )


class TestEnrollmentAndFetch:
    @respx.mock
    async def test_first_sync_enrolls_then_fetches_and_stores_pack(
        self, tmp_path
    ) -> None:
        key = make_policy_key()
        root = make_root(key)
        store = PolicyStore(tmp_path)
        enroll = respx.post(f"{CP}/api/v1/edge/enroll").mock(
            return_value=httpx.Response(
                200, json={"node_id": "wn-abc123", "token": "node-tok"}
            )
        )
        fetch = respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=42))
            )
        )
        sync = make_sync(store, root, enrollment_token="one-time-tok")

        outcome = await sync.sync_once()

        assert outcome.ok
        assert outcome.changed
        assert outcome.pack is not None
        assert outcome.pack.policy_version == 42
        assert enroll.called
        assert fetch.called
        assert store.load_credentials() == ("wn-abc123", "node-tok")
        assert store.load_policy() is not None

    @respx.mock
    async def test_sync_with_stored_credentials_skips_enrollment(
        self, tmp_path
    ) -> None:
        key = make_policy_key()
        root = make_root(key)
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-stored", "node-tok")
        enroll = respx.post(f"{CP}/api/v1/edge/enroll").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=7))
            )
        )
        sync = make_sync(store, root)

        outcome = await sync.sync_once()

        assert outcome.ok
        assert outcome.pack is not None
        assert outcome.pack.policy_version == 7
        assert not enroll.called

    async def test_no_credentials_and_no_token_refuses(self, tmp_path) -> None:
        sync = make_sync(PolicyStore(tmp_path), make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert S_NO_CREDENTIALS in outcome.codes
        assert "WARDEN_ENROLLMENT_TOKEN" in outcome.detail


class TestVersionGate:
    @respx.mock
    async def test_re_fetching_same_pack_reports_no_change(self, tmp_path) -> None:
        key = make_policy_key()
        pack_bytes = make_pack_bytes(key, version=42)
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        route = respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, json=policy_response_doc(pack_bytes))
        )
        sync = make_sync(store, make_root(key))

        first = await sync.sync_once()
        second = await sync.sync_once()

        assert first.ok and first.changed
        assert second.ok
        assert not second.changed
        assert route.call_count == 2

    @respx.mock
    async def test_newer_version_installs_and_older_is_refused(self, tmp_path) -> None:
        key = make_policy_key()
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=42))
            )
        )
        sync = make_sync(store, make_root(key))
        await sync.sync_once()

        v43 = policy_response_doc(make_pack_bytes(key, version=43))
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, json=v43)
        )
        upgraded = await sync.sync_once()
        assert upgraded.ok and upgraded.changed
        assert upgraded.pack is not None
        assert upgraded.pack.policy_version == 43

        # A replayed, still-signed v42 must not take force over v43.
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=42))
            )
        )
        downgraded = await sync.sync_once()
        assert not downgraded.ok
        assert "P-VERSION-REPLAY" in downgraded.codes
        assert store.load_policy() == v43  # the refused pack never persisted


class TestTamperAndCorruption:
    @respx.mock
    async def test_tampered_payload_is_refused_and_store_unchanged(
        self, tmp_path
    ) -> None:
        key = make_policy_key()
        good_doc = policy_response_doc(make_pack_bytes(key, version=42))
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, json=good_doc)
        )
        sync = make_sync(store, make_root(key))
        assert (await sync.sync_once()).ok

        tampered = dict(good_doc)
        envelope = dict(tampered["envelope"])
        envelope["payload"] = envelope["payload"][:-4] + "AAAA"
        tampered["envelope"] = envelope
        tampered["policy_version"] = 43
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, json=tampered)
        )

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert S_PAYLOAD_HASH not in outcome.codes  # refused before the hash stage
        assert store.load_policy() == good_doc

    @respx.mock
    async def test_payload_hash_mismatch_refuses_the_pack(self, tmp_path) -> None:
        key = make_policy_key()
        doc = policy_response_doc(make_pack_bytes(key, version=42))
        doc["payload_hash"] = "0" * 64
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, json=doc)
        )
        sync = make_sync(store, make_root(key))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert S_PAYLOAD_HASH in outcome.codes
        assert store.load_policy() is None

    @respx.mock
    async def test_tampered_store_refuses_until_operator_intervenes(
        self, tmp_path
    ) -> None:
        """A tampered policy file is tampering, not a missing watermark."""
        key = make_policy_key()
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=42))
            )
        )
        first_sync = make_sync(store, make_root(key))
        assert (await first_sync.sync_once()).ok

        # Tamper the stored policy on disk, then restart (fresh in-memory state).
        stored = store.load_policy()
        assert stored is not None
        stored["envelope"]["payload"] = "dGFtcGVyZWQ="
        store.save_policy(stored)

        restarted = make_sync(store, make_root(key))
        outcome = await restarted.sync_once()

        assert not outcome.ok
        assert S_STORE_TAMPERED in outcome.codes
        assert outcome.refused_stored
        # Even a valid newer pack is refused while the store cannot be trusted:
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=43))
            )
        )
        still_refused = await restarted.sync_once()
        assert not still_refused.ok
        assert S_STORE_TAMPERED in still_refused.codes


class TestTransportAndAuth:
    @respx.mock
    async def test_401_marks_the_outcome_revoked(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(401, json={"detail": "unknown token"})
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert outcome.revoked
        assert S_AUTH in outcome.codes

    @respx.mock
    async def test_403_marks_the_outcome_revoked(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(403, json={"detail": "node revoked"})
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert outcome.revoked
        assert outcome.http_status == 403

    @respx.mock
    async def test_404_is_no_policy_yet_not_revocation(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(404, json={"detail": "none"})
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert not outcome.revoked
        assert S_NO_POLICY in outcome.codes

    @respx.mock
    async def test_500_is_an_http_miss(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(500, text="boom")
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert not outcome.revoked
        assert S_HTTP in outcome.codes

    @respx.mock
    async def test_connection_error_is_a_transport_miss(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert S_TRANSPORT in outcome.codes

    @respx.mock
    async def test_non_json_body_is_a_bad_response(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(200, text="<html>not json</html>")
        )
        sync = make_sync(store, make_root(make_policy_key()))

        outcome = await sync.sync_once()

        assert not outcome.ok
        assert S_BAD_RESPONSE in outcome.codes


class TestExpiryViaClock:
    @respx.mock
    async def test_expired_pack_is_refused_at_restart(self, tmp_path) -> None:
        """A restart against an expired stored pack refuses, never re-installs."""
        key = make_policy_key()
        store = PolicyStore(tmp_path)
        store.save_credentials("wn-abc123", "node-tok")
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            return_value=httpx.Response(
                200, json=policy_response_doc(make_pack_bytes(key, version=42))
            )
        )
        clock = FakeClock(WARDEN_NOW)
        first = make_sync(store, make_root(key), clock=clock)
        assert (await first.sync_once()).ok

        clock.advance(days=7)  # past the pack's not_after (NOW + 6 days)
        restarted = make_sync(store, make_root(key), clock=clock)

        outcome = await restarted.sync_once()

        assert not outcome.ok
        assert "P-EXPIRED" in outcome.codes
        # The store keeps the (expired) pack — a refusal writes nothing.
        stored = store.load_policy()
        assert stored is not None
        assert stored["policy_version"] == 42
