"""Reconciler tests: the reconnect half of the mesh.

The control plane is an httpx.MockTransport that records every request
body; the journal is real (hash-chained, on disk, 0600); the machine is
driven directly. These are the reconnect acceptance criteria: merges
dedupe by the server's receipt range, a chain gap resends from the
server-held head + 1, revoked nodes stop pushing, the drain is
mode-gated, and RECONCILING closes only when the journal is fully
drained.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from core.edge.journal import record_hash
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics
from services.warden.modes import ModeMachine, OperatingMode
from services.warden.reconciler import Reconciler
from services.warden.storage import PolicyStore
from tests.unit.warden.helpers import FakeClock

CP = "http://control-plane.test"


def make_journal(tmp_path: Path, count: int) -> Journal:
    """A real journal with ``count`` wire-shaped records chained from genesis."""
    journal = Journal(tmp_path / "journal.jsonl")
    for i in range(count):
        target = f"198.51.100.{10 + i}"
        journal.append(
            mode="AUTONOMOUS",
            idempotency_key=f"block_ip:{target}",
            action_type="block_ip",
            target=target,
            decision_rule=f"edge-001 met ({i})",
            execution={"status": "executed", "executor": "recording"},
            ts="2026-10-09T13:02:11Z",
        )
    return journal


def make_reconciler(
    tmp_path: Path,
    *,
    journal: Journal,
    handler: Callable[[httpx.Request], httpx.Response],
    machine: ModeMachine | None = None,
    mode: OperatingMode = OperatingMode.SYNCED,
    policy_version: Callable[[], int | None] | None = lambda: 42,
    batch_size: int = 100,
    with_credentials: bool = True,
) -> tuple[Reconciler, ModeMachine, list[dict[str, Any]], list[httpx.Request]]:
    """A reconciler over a recording MockTransport and a real journal."""
    machine = machine or ModeMachine(grace_window_seconds=900.0)
    machine.mode = mode
    store = PolicyStore(tmp_path / "data")
    if with_credentials:
        store.save_credentials("wn-test", "node-tok")
    bodies: list[dict[str, Any]] = []
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content.decode())
        bodies.append(body)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(recording_handler))
    reconciler = Reconciler(
        journal=journal,
        store=store,
        base_url=CP,
        machine=machine,
        policy_version=policy_version or (lambda: None),
        batch_size=batch_size,
        interval_seconds=30.0,
        clock=FakeClock(),
        metrics=WardenMetrics(),
        client=client,
    )
    return reconciler, machine, bodies, requests


def ok_response(
    accepted_through: int,
    *,
    merged: int = 0,
    duplicates: list[int] | None = None,
    rejected: list[dict[str, Any]] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "accepted_through": accepted_through,
            "merged_count": merged,
            "duplicate_ids": duplicates or [],
            "rejected": rejected or [],
            "receipt_id": "r-1",
        },
    )


class TestHappyPathMerge:
    async def test_pushes_journal_batches_to_the_frozen_contract(
        self, tmp_path: Path
    ) -> None:
        journal = make_journal(tmp_path, 2)
        reconciler, _machine, bodies, requests = make_reconciler(
            tmp_path, journal=journal, handler=lambda request: ok_response(2)
        )

        await reconciler.tick()

        assert len(requests) == 1
        assert requests[0].url.path == "/api/v1/edge/journal"
        assert requests[0].headers["Authorization"] == "Bearer node-tok"
        assert bodies[0]["node_id"] == "wn-test"
        assert bodies[0]["policy_version"] == 42
        assert [r["seq"] for r in bodies[0]["records"]] == [1, 2]
        # The chain head is the hash of the last record in the batch —
        # what the server pins as its per-node receipt head.
        last = bodies[0]["records"][-1]
        assert bodies[0]["chain_head"] == record_hash(last["prev_hash"], last)
        assert reconciler.acked_seq == 2

    async def test_receipt_range_is_the_dedupe_nothing_repushes(
        self, tmp_path: Path
    ) -> None:
        journal = make_journal(tmp_path, 2)
        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path,
            journal=journal,
            handler=lambda request: ok_response(
                2, merged=1, duplicates=[1], rejected=[{"seq": 2, "code": "P-ENVELOPE"}]
            ),
        )
        await reconciler.tick()
        assert reconciler.acked_seq == 2

        # Duplicates and rejections advanced the chain position either
        # way: the next cycle pushes nothing — dedupe lives in the
        # watermark, not in retrying what the server already has.
        await reconciler.tick()
        assert len(requests) == 1

    async def test_batching_pushes_in_batches_until_drained(
        self, tmp_path: Path
    ) -> None:
        journal = make_journal(tmp_path, 3)
        reconciler, machine, bodies, _requests = make_reconciler(
            tmp_path,
            journal=journal,
            mode=OperatingMode.RECONCILING,
            batch_size=2,
            handler=lambda request: ok_response(
                max(r["seq"] for r in json.loads(request.content)["records"])
            ),
        )

        await reconciler.tick()
        assert len(bodies[0]["records"]) == 2  # [1, 2]
        # The drain is not empty: RECONCILING holds — the node does not
        # call itself SYNCED with undelivered history.
        assert machine.mode is OperatingMode.RECONCILING

        await reconciler.tick()
        assert [r["seq"] for r in bodies[1]["records"]] == [3]
        assert reconciler.acked_seq == 3
        # Drained to empty: only now does RECONCILING close to SYNCED.
        assert machine.mode is OperatingMode.SYNCED


class TestChainGap:
    async def test_gap_409_resyncs_and_resends_from_server_head(
        self, tmp_path: Path
    ) -> None:
        journal = make_journal(tmp_path, 7)
        # The server already holds 1-5 (its receipt head); this node's
        # watermark starts at 0 — a restarted warden finding its place
        # through the 409 itself, since the contract has no
        # receipt-read endpoint.
        phase = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            phase["n"] += 1
            if phase["n"] == 1:
                return httpx.Response(
                    409,
                    json={
                        "reason": "chain-gap",
                        "detail": "batch does not chain from server head",
                        "server_last_seq": 5,
                        "resend_from": 6,
                    },
                )
            return ok_response(7)

        reconciler, _machine, bodies, _requests = make_reconciler(
            tmp_path, journal=journal, handler=handler
        )

        await reconciler.tick()
        assert reconciler.acked_seq == 5

        # The next cycle resumes exactly at server head + 1 — no replay
        # of what the server holds, no gap.
        await reconciler.tick()
        assert [r["seq"] for r in bodies[1]["records"]] == [6, 7]
        assert reconciler.acked_seq == 7


class TestAuthRefusal:
    async def test_revoked_node_stops_pushing(self, tmp_path: Path) -> None:
        journal = make_journal(tmp_path, 2)
        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path,
            journal=journal,
            handler=lambda request: httpx.Response(403),
        )

        await reconciler.tick()
        assert reconciler.acked_seq == 0
        assert reconciler.halted_reason == "auth-refused-403"

        # A refused identity cannot be fixed by retrying: the drain is
        # halted, no further requests are made, and revocation proper
        # arrives through the sync channel (the machine's only
        # tightening input).
        await reconciler.tick()
        assert len(requests) == 1
        assert reconciler.acked_seq == 0


class TestModeGating:
    async def test_pushes_only_in_synced_and_reconciling(self, tmp_path: Path) -> None:
        journal = make_journal(tmp_path, 1)
        for mode in (
            OperatingMode.BOOTSTRAP,
            OperatingMode.DEGRADED,
            OperatingMode.AUTONOMOUS,
            OperatingMode.PASSIVE,
            OperatingMode.REVOKED,
        ):
            reconciler, _machine, _bodies, requests = make_reconciler(
                tmp_path, journal=journal, mode=mode, handler=lambda r: ok_response(1)
            )
            await reconciler.tick()
            assert requests == [], f"pushed in {mode}"

        # The connected postures push.
        for mode in (OperatingMode.SYNCED, OperatingMode.RECONCILING):
            reconciler, _machine, _bodies, requests = make_reconciler(
                tmp_path, journal=journal, mode=mode, handler=lambda r: ok_response(1)
            )
            await reconciler.tick()
            assert len(requests) == 1, f"did not push in {mode}"

    async def test_empty_drain_completes_reconciling(self, tmp_path: Path) -> None:
        machine = ModeMachine(grace_window_seconds=900.0)
        machine.mode = OperatingMode.RECONCILING
        journal = Journal(tmp_path / "journal.jsonl")  # nothing to push
        reconciler, machine, _bodies, requests = make_reconciler(
            tmp_path, journal=journal, machine=machine, handler=lambda r: ok_response(0)
        )

        await reconciler.tick()
        assert requests == []  # nothing to push
        assert machine.mode is OperatingMode.SYNCED


class TestPreconditions:
    async def test_no_credentials_cannot_push(self, tmp_path: Path) -> None:
        journal = make_journal(tmp_path, 1)
        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path,
            journal=journal,
            with_credentials=False,
            handler=lambda r: ok_response(1),
        )
        await reconciler.tick()
        assert requests == []
        assert reconciler.acked_seq == 0

    async def test_no_policy_version_cannot_push(self, tmp_path: Path) -> None:
        journal = make_journal(tmp_path, 1)
        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path,
            journal=journal,
            policy_version=None,
            handler=lambda r: ok_response(1),
        )
        await reconciler.tick()
        assert requests == []
        assert reconciler.acked_seq == 0


class TestResilience:
    async def test_transport_miss_retries_next_cycle(self, tmp_path: Path) -> None:
        journal = make_journal(tmp_path, 1)
        phase = {"down": True}

        def handler(request: httpx.Request) -> httpx.Response:
            if phase["down"]:
                raise httpx.ConnectError("down")
            return ok_response(1)

        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path,
            journal=journal,
            handler=handler,
        )

        await reconciler.tick()
        assert reconciler.acked_seq == 0  # a miss is not a refusal: nothing moved

        # The next cycle retries — and lands.
        phase["down"] = False
        await reconciler.tick()
        assert reconciler.acked_seq == 1
        assert requests[-1].url.path == "/api/v1/edge/journal"

    async def test_wire_illegal_record_halts_the_drain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The node-side wire pin: a record the frozen contract cannot
        # carry would get the whole batch refused (and, with contiguity,
        # everything behind it). The reconciler halts instead of pushing.
        journal = make_journal(tmp_path, 1)
        monkeypatch.setattr(
            "services.warden.reconciler.record_wire_error", lambda record: "boom"
        )
        reconciler, _machine, _bodies, requests = make_reconciler(
            tmp_path, journal=journal, handler=lambda r: ok_response(1)
        )

        await reconciler.tick()
        assert requests == []
        assert reconciler.halted_reason is not None
        assert "boom" in reconciler.halted_reason

        # Sticky: the writer is buggy — retrying cannot fix it.
        await reconciler.tick()
        assert requests == []
