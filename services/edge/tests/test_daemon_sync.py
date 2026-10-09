"""Daemon sync-state behavior: partition changes what the daemon may do,
never whether it runs. Every scenario drives the real ``_sync_cycle`` over a
fake sync client — the state machine, offline window, and conflict-precedence
rules are the unit under test."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from services.edge.app.config import EdgeConfig
from services.edge.app.daemon import EdgeDaemon
from services.edge.app.states import OperatingState
from services.edge.executors.registry import ActionResult
from services.edge.journal.journal import (
    KIND_OBSERVATION,
    KIND_OFFLINE_WINDOW,
)
from services.edge.sync.client import SyncError
from services.edge.sync.reconciler import Reconciler
from services.edge.tests._fixtures import (
    EdgeSigner,
    bundle_payload,
    make_bundle,
    make_observation,
    sign_envelope,
    trust_root_for,
)


class FakeExecutor:
    name = "nftables"
    action_types = frozenset({"block_ip", "block_domain"})

    def __init__(self) -> None:
        self.applied = 0

    async def apply(
        self, action: Any, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        self.applied += 1
        return ActionResult(success=True, ref="vigil/edge/test")

    async def revert(self, ref: str) -> ActionResult:
        return ActionResult(success=True, ref=ref)


class FakeSyncClient:
    """The four sync calls, scripted. ``post_events`` acks everything by
    default — the reconciler has its own suite for server stalling."""

    def __init__(self) -> None:
        self.credential: str | None = "fake-cred"
        self.heartbeat_result: dict = {"ok": True, "revoked": False}
        self.heartbeat_error: SyncError | None = None
        self.policy_result: dict = {"bundle": None, "current_version": None}
        self.ack_all = True
        self.uploads: list[list[dict]] = []

    async def heartbeat(self, **kwargs: Any) -> dict:
        if self.heartbeat_error is not None:
            raise self.heartbeat_error
        return self.heartbeat_result

    def load_credential(self) -> bool:
        return self.credential is not None

    async def enroll(self, token: str, scope: dict) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def pull_policy(self, cursor: int | None) -> dict:
        return self.policy_result

    async def post_events(self, events: list[dict]) -> dict:
        self.uploads.append(events)
        if self.ack_all:
            return {
                "acked": [e["event_id"] for e in events],
                "duplicates": [],
                "rejected": [],
            }
        return {"acked": [], "duplicates": [], "rejected": []}


@pytest.fixture
def signer() -> EdgeSigner:
    return EdgeSigner()


def make_daemon(tmp_path: Path, signer: EdgeSigner) -> EdgeDaemon:
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps(trust_root_for(signer)))
    config = EdgeConfig(
        node_id="gw-test",
        data_dir=tmp_path / "data",
        trust_store=trust_file,
        model=None,
        node_labels={"vigil.ai/edge-role": "gateway"},
        journal_max_bytes=1 << 20,
    )
    daemon = EdgeDaemon(config)
    daemon._init_components()
    return daemon


def wire_client(daemon: EdgeDaemon, client: FakeSyncClient) -> None:
    daemon._client = client
    daemon._reconciler = Reconciler(client, daemon._journal, batch_size=10)


def activate(daemon: EdgeDaemon, signer: EdgeSigner, version: int = 7) -> None:
    payload = bundle_payload(
        version=version,
        not_before="2020-01-01T00:00:00Z",
        expires_at="2099-12-31T00:00:00Z",
    )
    from datetime import UTC, datetime

    result = daemon._cache.verify_and_activate(
        sign_envelope(payload, signer), now=datetime.now(UTC)
    )
    assert result.accepted, result.code


def kinds(records: list) -> list[str]:
    return [record.kind for record in records]


def test_boot_partitioned_then_first_healthy_cycle_reaches_synced(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        assert daemon._states.state is OperatingState.PARTITIONED  # cold start
        client = FakeSyncClient()
        wire_client(daemon, client)
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED
        # No window was ever opened: nothing offline happened.
        assert not [
            record
            for record in daemon._journal.unacked()
            if record.kind == KIND_OFFLINE_WINDOW
        ]

    asyncio.run(scenario())


def test_heartbeat_failure_partitions_but_enforcement_continues(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        client = FakeSyncClient()
        wire_client(daemon, client)
        await daemon._sync_cycle()  # healthy -> SYNCED
        assert daemon._states.state is OperatingState.SYNCED

        client.heartbeat_error = SyncError("WAN down")
        with pytest.raises(SyncError):
            await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.PARTITIONED
        window = [
            record
            for record in daemon._journal.unacked()
            if record.kind == KIND_OFFLINE_WINDOW
        ]
        assert len(window) == 1 and window[0].payload["phase"] == "open"

        # The point of the feature: the partition does not stop enforcement.
        blocks_before = executor.applied
        await daemon.handle_observation(make_observation())
        assert executor.applied == blocks_before + 1
        assert daemon._states.state is OperatingState.PARTITIONED

    asyncio.run(scenario())


def test_revocation_beats_allowance_degrades_and_stops_actions(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        client = FakeSyncClient()
        wire_client(daemon, client)
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED

        client.heartbeat_result = {"ok": True, "revoked": True}
        await daemon._sync_cycle()  # no raise: revocation is not a link error
        assert daemon._states.state is OperatingState.DEGRADED

        await daemon.handle_observation(make_observation())
        assert executor.applied == 0  # the cached bundle may not act anymore
        records = daemon._journal.unacked()
        assert kinds(records)[-1] == KIND_OBSERVATION  # journaled, tier-0 floor

    asyncio.run(scenario())


def test_expired_bundle_is_never_extended_locally(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        client = FakeSyncClient()
        wire_client(daemon, client)
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED

        # The clock passed expires_at mid-partition: the cache holds an
        # expired bundle and no pull can resurrect it.
        daemon._cache._current = make_bundle(
            version=7,
            not_before="2019-01-01T00:00:00Z",
            expires_at="2020-01-01T00:00:00Z",
        )
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.DEGRADED

        await daemon.handle_observation(make_observation())
        assert executor.applied == 0
        # A pull that serves nothing new cannot restore the tier: the same
        # cycle that degraded the node leaves it there.
        client.ack_all = True
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.DEGRADED

    asyncio.run(scenario())


def test_reconcile_completes_before_synced_and_window_closes_after(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        client = FakeSyncClient()
        wire_client(daemon, client)
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED

        # Partition: heartbeat dies, enforcement journals offline.
        client.heartbeat_error = SyncError("WAN down")
        with pytest.raises(SyncError):
            await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.PARTITIONED
        await daemon.handle_observation(make_observation())  # one offline action

        # Link restored, but the server commits nothing yet: the spec's
        # RECONCILING state, enforced limits active.
        client.heartbeat_error = None
        client.ack_all = False
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.RECONCILING

        # The commit lands: drain, close the window, then SYNCED.
        client.ack_all = True
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED
        await daemon._sync_cycle()  # uploads the closure record

        # The closure event is uploaded AFTER the replay and carries the
        # partition's shape — the ordering record is the payload itself.
        close_events = [
            event
            for batch in client.uploads
            for event in batch
            if event["kind"] == "offline_window"
            and event["payload"]["phase"] == "close"
        ]
        assert len(close_events) == 1
        timeline = [
            state["to"] for state in close_events[0]["payload"]["state_timeline"]
        ]
        assert "partitioned" in timeline and "reconciling" in timeline

    asyncio.run(scenario())


def test_closure_record_carries_the_drift_payload(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        daemon = make_daemon(tmp_path, signer)
        executor = FakeExecutor()
        daemon._executors.register(executor)
        activate(daemon, signer)
        client = FakeSyncClient()
        wire_client(daemon, client)

        client.heartbeat_error = SyncError("WAN down")
        with pytest.raises(SyncError):
            await daemon._sync_cycle()
        client.heartbeat_error = None
        await daemon.handle_observation(make_observation())  # blocked offline
        await daemon._sync_cycle()  # drained -> window closes
        await daemon._sync_cycle()  # uploads the closure record

        closes = [
            event
            for batch in client.uploads
            for event in batch
            if event["kind"] == "offline_window"
            and event["payload"]["phase"] == "close"
        ]
        assert len(closes) == 1
        payload = closes[0]["payload"]
        assert payload["node_id"] == "gw-test"
        assert payload["boot_id"] == daemon._boot_id
        assert [entry["rule_string"] for entry in payload["executed"]]
        assert payload["executed"][0]["rule_string"].startswith("edge.c2-egress-active")
        assert payload["needs_analyst"] is False  # everything executed + reverted
        # Boot-partitioned: no in-window transitions, so the timeline is
        # empty — the open record's reason carries the context instead.
        assert payload["opened_at"]

    asyncio.run(scenario())


def test_boot_without_credentials_partitions_and_journals_only(
    tmp_path: Path, signer: EdgeSigner
) -> None:
    async def scenario() -> None:
        trust_file = tmp_path / "trust.json"
        trust_file.write_text(json.dumps(trust_root_for(signer)))
        config = EdgeConfig(
            node_id="gw-test",
            data_dir=tmp_path / "data",
            trust_store=trust_file,
            model=None,
            node_labels={"vigil.ai/edge-role": "gateway"},
            journal_max_bytes=1 << 20,
            enrollment_token="",
        )
        daemon = EdgeDaemon(config)
        daemon._init_components()
        client = FakeSyncClient()
        client.credential = None  # no credential, no token: cannot authenticate
        wire_client(daemon, client)

        with pytest.raises(SyncError):
            await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.PARTITIONED

        await daemon.handle_observation(make_observation())
        records = daemon._journal.unacked()
        assert kinds(records)[-1] == KIND_OBSERVATION  # tier-0 floor holds

    asyncio.run(scenario())
