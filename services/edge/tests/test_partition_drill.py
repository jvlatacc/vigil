"""The partition drill (spec acceptance criterion), in process.

Real SyncClient over a fake control plane, real reconciler, real journal,
real bundle cache, real daemon sync cycles. Script: connect and sync, cut
the WAN mid-run, keep enforcing on the cached bundle, restore, replay in
bounded batches — duplicate delivery (committed server-side, response lost)
produces zero duplicate rows — close the offline window with a drift report,
and return to SYNCED."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from services.edge.app.config import EdgeConfig
from services.edge.app.daemon import EdgeDaemon
from services.edge.app.states import OperatingState
from services.edge.executors.registry import ActionResult
from services.edge.sync.client import SyncClient, SyncError
from services.edge.sync.reconciler import Reconciler
from services.edge.tests._fixtures import (
    EdgeSigner,
    bundle_payload,
    make_observation,
    sign_envelope,
    trust_root_for,
)

BATCH_SIZE = 2


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


class FakeControlPlane:
    """The /internal/edge contract in miniature, with a WAN switch and a
    crash-after-commit mode. Dedup is by event_id — the drill's zero-
    duplicate assertion reads `commit_counts`, not the dict's own semantics."""

    def __init__(self, signer: EdgeSigner, node_id: str) -> None:
        self.signer = signer
        self.node_id = node_id
        self.bundle_version = 7
        self.up = True
        self.drop_next_response = False
        self.revoked = False
        self.committed: dict[str, dict] = {}
        self.commit_counts: dict[str, int] = {}
        self.duplicates_seen: list[str] = []
        self.upload_batches: list[list[int]] = []
        self.commit_watermark = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("WAN down", request=request)
        path = request.url.path
        if path == f"/internal/edge/{self.node_id}/policy":
            cursor = request.url.params.get("cursor")
            if self.bundle_version is not None and str(self.bundle_version) != cursor:
                payload = bundle_payload(version=self.bundle_version)
                row = {
                    "bundle_id": payload["bundle_id"],
                    "version": self.bundle_version,
                    "autonomy_tier": payload["autonomy_tier"],
                    "envelope": sign_envelope(payload, self.signer),
                }
                return httpx.Response(
                    200, json={"bundle": row, "current_version": self.bundle_version}
                )
            return httpx.Response(
                200, json={"bundle": None, "current_version": self.bundle_version}
            )
        if path == f"/internal/edge/{self.node_id}/events":
            events = json.loads(request.read()).get("events", [])
            self.upload_batches.append([])
            acked, duplicates, rejected = [], [], []
            for event in events:
                self.upload_batches[-1].append(event["local_sequence"])
                event_id = event["event_id"]
                if event_id in self.committed:
                    duplicates.append(event_id)
                    self.duplicates_seen.append(event_id)
                    continue
                if event.get("kind") not in (
                    "observation",
                    "action",
                    "revert",
                    "offline_window",
                ):
                    rejected.append(
                        {"event_id": event_id, "reason": "schema_version_unsupported"}
                    )
                    continue
                self.committed[event_id] = event
                self.commit_counts[event_id] = self.commit_counts.get(event_id, 0) + 1
                acked.append(event_id)
                self.commit_watermark = max(
                    self.commit_watermark, event["local_sequence"]
                )
            if self.drop_next_response:
                # The classic partition wound: the batch committed here, the
                # wire died before the ack — the node MUST replay and the
                # server MUST dedup.
                self.drop_next_response = False
                raise httpx.ConnectError(
                    "connection reset after commit", request=request
                )
            return httpx.Response(
                200,
                json={
                    "acked": acked,
                    "duplicates": duplicates,
                    "rejected": rejected,
                    "commit_watermark": self.commit_watermark,
                },
            )
        if path == f"/internal/edge/{self.node_id}/heartbeat":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "revoked": self.revoked,
                    "commit_watermark": self.commit_watermark,
                },
            )
        return httpx.Response(404, json={"error": "no such route"})


@pytest.fixture
def signer() -> EdgeSigner:
    return EdgeSigner()


def make_daemon(
    tmp_path: Path, signer: EdgeSigner
) -> tuple[EdgeDaemon, FakeExecutor, FakeControlPlane]:
    daemon = EdgeDaemon(_config_for(tmp_path, signer))
    daemon._init_components()
    executor = FakeExecutor()
    daemon._executors.register(executor)
    plane = FakeControlPlane(signer, "gw-test")
    client = SyncClient(
        control_url="http://control.test",
        node_id="gw-test",
        credential_file=tmp_path / "credential",
        transport=httpx.MockTransport(plane.handler),
    )
    client._credential = "drill-cred"
    daemon._client = client
    daemon._reconciler = Reconciler(client, daemon._journal, batch_size=BATCH_SIZE)
    return daemon, executor, plane


def test_partition_drill(tmp_path: Path, signer: EdgeSigner) -> None:
    async def scenario() -> None:
        daemon, executor, plane = make_daemon(tmp_path, signer)

        # -- connected: sync up, pull the signed bundle, enforce ----------
        await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.SYNCED
        assert daemon._cache.current is not None
        assert daemon._cache.current.version == 7

        await daemon.handle_observation(make_observation())
        assert executor.applied == 1  # connected containment

        # -- cut the WAN mid-run -----------------------------------------
        plane.up = False
        with pytest.raises(SyncError):
            await daemon._sync_cycle()
        assert daemon._states.state is OperatingState.PARTITIONED

        # The point of the feature: enforcement continues on the cached
        # bundle while the control plane is unreachable.
        await daemon.handle_observation(make_observation())
        await daemon.handle_observation(make_observation())
        assert executor.applied == 3

        # -- restore the link: first batch commits, then the wire dies ---
        plane.up = True
        plane.drop_next_response = True
        with pytest.raises(SyncError):
            await daemon._sync_cycle()

        # -- replay: the same event_ids go back up, server dedups --------
        await daemon._sync_cycle()  # replays + drains; window closes
        assert daemon._states.state is OperatingState.SYNCED
        await daemon._sync_cycle()  # uploads the offline-window closure

        # Bounded, in-order batches throughout.
        for batch in plane.upload_batches:
            assert len(batch) <= BATCH_SIZE
            assert batch == sorted(batch)

        # Duplicate delivery: the crashed batch was committed once, its
        # replay detected as duplicates — zero rows committed twice.
        assert plane.duplicates_seen, "the replay never happened"
        assert all(count == 1 for count in plane.commit_counts.values())
        assert len(plane.committed) == len(plane.commit_counts)

        # The offline window closed with a drift report on the wire —
        # read from the control plane's committed map, the server's own
        # view of what was durably delivered.
        closures = [
            event
            for event in plane.committed.values()
            if event["kind"] == "offline_window"
            and event["payload"]["phase"] == "close"
        ]
        assert len(closures) == 1
        payload = closures[0]["payload"]
        assert payload["node_id"] == "gw-test"
        assert len(payload["executed"]) == 2  # the two OFFLINE blocks; the
        # connected one predates the window and is not its business
        assert payload["executed"][0]["rule_string"].startswith("edge.c2-egress-active")
        assert payload["needs_analyst"] is False  # no losses, no pending holds

        # The journal is fully acknowledged — nothing lost, nothing stuck.
        assert daemon._journal.unacked() == []

    asyncio.run(scenario())

    # Reboot the daemon against the same data dir: the persisted bundle
    # reloads and stays active (revocation never happened in this drill).
    rebooted = EdgeDaemon(_config_for(tmp_path, signer))
    rebooted._init_components()
    assert rebooted._cache.current is not None
    assert rebooted._cache.current.version == 7


def _config_for(tmp_path: Path, signer: EdgeSigner) -> EdgeConfig:
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps(trust_root_for(signer)))
    return EdgeConfig(
        node_id="gw-test",
        data_dir=tmp_path / "data",
        trust_store=trust_file,
        model=None,
        node_labels={"vigil.ai/edge-role": "gateway"},
        journal_max_bytes=1 << 20,
        sync_batch_size=BATCH_SIZE,
    )
