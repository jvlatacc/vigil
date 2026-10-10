"""Decision-loop tests: the partition, expiry, and revocation paths.

The control plane is respx-mocked; the clock is the FakeClock; the
sentinel is an in-process queue (the loop consumes via ``drain``). These
are the acceptance criteria from the work item: nothing enforces before
the grace window lapses, expiry undoes live actions and goes PASSIVE,
observed revocation halts, and every decision journals.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import respx

from core.edge.policy import PolicyPack
from core.edge.target_guard import TargetGuard
from services.warden.engine import (
    DecisionLoop,
    DryRunExecutor,
    ExecutionResult,
    ExecutorRegistry,
    LoopDeps,
)
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics
from services.warden.modes import ModeMachine, OperatingMode
from services.warden.sentinel import Sentinel
from services.warden.storage import PolicyStore
from services.warden.sync import PolicySync
from services.warden.triage import LocalSlm
from tests.unit.warden.helpers import (
    WARDEN_NOW,
    FakeClock,
    free_port,
    make_pack_bytes,
    make_policy_key,
    make_root,
    policy_response_doc,
)

CP = "http://control-plane.test"

GOOD_ALERT = {
    "id": "al-1",
    "indicator": "ip",
    "value": "198.51.100.7",  # TEST-NET-2: never a protected target
    "mitre": ["T1071"],
    "confidence": 0.93,
}


class RecordingExecutor:
    """A block_ip executor that records calls and reports real execution."""

    name = "recording"
    action_type = "block_ip"

    def __init__(self) -> None:
        self.enforced: list[tuple[str, str]] = []
        self.undone: list[tuple[str, str]] = []

    def enforce(self, action: Any, target: str) -> ExecutionResult:
        self.enforced.append((action.type, target))
        return ExecutionResult(status="executed", executor=self.name)

    def undo(self, action: Any, target: str) -> ExecutionResult:
        self.undone.append((action.type, target))
        return ExecutionResult(status="executed", executor=self.name)


def make_loop(
    tmp_path: Path,
    *,
    clock: FakeClock | None = None,
    registry: ExecutorRegistry | None = None,
    pack_overrides: dict[str, Any] | None = None,
    grace_window_seconds: float = 900.0,
    slm: LocalSlm | None = None,
) -> tuple[DecisionLoop, Sentinel, Journal, FakeClock, ExecutorRegistry]:
    """A loop over a respx-mocked sync, an in-process sentinel, a journal."""
    clock = clock or FakeClock()
    key = make_policy_key()
    data_dir = tmp_path / "data"
    store = PolicyStore(data_dir)
    store.save_credentials("wn-test", "node-tok")
    journal = Journal(data_dir / "journal.jsonl")
    metrics = WardenMetrics()
    sync = PolicySync(
        trust_root=make_root(key),
        store=store,
        base_url=CP,
        enrollment_token=None,
        clock=clock,
        metrics=metrics,
    )
    sentinel = Sentinel(
        bind_host="127.0.0.1", port=free_port(), token="local-tok", metrics=metrics
    )
    registry = registry or ExecutorRegistry()
    pack_bytes = make_pack_bytes(key, **(pack_overrides or {}))
    respx.get(f"{CP}/api/v1/edge/policy").mock(
        side_effect=[
            httpx.Response(200, json=policy_response_doc(pack_bytes)),
            *[httpx.Response(503) for _ in range(7)],
        ]
    )

    def guard_for(pack: PolicyPack) -> TargetGuard:
        return TargetGuard.from_pack(
            pack,
            self_addresses=("127.0.0.1",),
            gateway_addresses=("198.51.100.1",),
            control_plane_addresses=("198.51.100.9",),
            dns_resolvers=("198.51.100.53",),
        )

    loop = DecisionLoop(
        deps=LoopDeps(
            sync=sync,
            sentinel=sentinel,
            journal=journal,
            registry=registry,
            guard_provider=guard_for,
            clock=clock,
            metrics=metrics,
            slm=slm,
        ),
        interval_seconds=60.0,
        max_alert_batch=10,
        grace_window_seconds=grace_window_seconds,
        machine=ModeMachine(grace_window_seconds=grace_window_seconds),
    )
    return loop, sentinel, journal, clock, registry


def journal_records(journal: Journal) -> list[dict[str, Any]]:
    if not journal._path.exists():
        return []
    return [json.loads(line) for line in journal._path.read_text().splitlines()]


async def drive_to_autonomous(loop: DecisionLoop, clock: FakeClock) -> None:
    """One successful sync, three misses, then past the grace window.

    Returns with the machine in AUTONOMOUS — the grace lapse and the
    enforcement pass land in the same tick, so tests queue alerts after
    this returns (or during the outage, to observe them being held).
    """
    await loop.tick()  # pack installs -> SYNCED
    for _ in range(3):
        clock.advance(minutes=1)
        await loop.tick()
    clock.advance(seconds=901)
    await loop.tick()
    assert loop.machine.mode is OperatingMode.AUTONOMOUS


class TestOutageToAutonomous:
    @respx.mock
    async def test_sync_fails_then_grace_lapses_then_autonomous_enforces(
        self, tmp_path: Path
    ) -> None:
        executor = RecordingExecutor()
        registry = ExecutorRegistry()
        registry.register(executor)
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, registry=registry
        )

        # Tick 1: the pack installs; SYNCED observes. Then the outage
        # begins; the alert arrives; nothing may enforce before the
        # grace window lapses - the alert is held, not dropped.
        await loop.tick()
        assert loop.machine.mode is OperatingMode.SYNCED
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        for _ in range(3):
            clock.advance(minutes=1)
            await loop.tick()
        assert loop.machine.mode is OperatingMode.DEGRADED
        assert executor.enforced == []
        assert not journal_records(journal)
        assert sentinel.queue.qsize() == 1  # held, not dropped

        # Grace window elapses while the sync is still failing: AUTONOMOUS
        # arrives and the held alert enforces in that same tick.
        clock.advance(seconds=901)
        await loop.tick()
        assert loop.machine.mode is OperatingMode.AUTONOMOUS
        assert executor.enforced == [("block_ip", "198.51.100.7")]
        assert sentinel.queue.qsize() == 0
        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["mode"] == "AUTONOMOUS"
        assert records[0]["idempotency_key"] == "block_ip:198.51.100.7"
        assert records[0]["execution"]["status"] == "executed"

    @respx.mock
    async def test_unenforceable_pack_never_installs_and_nothing_enforces(
        self, tmp_path: Path
    ) -> None:
        # "A disallowed action type refuses" is enforced where it can be
        # honest: the pack loader refuses a rule the envelope's allowlist
        # never allows (P-RULE-UNENFORCEABLE), so a pack that widens
        # beyond the allowlist cannot install — and Warden, holding no
        # pack, enforces nothing and stays in BOOTSTRAP. The ladder's own
        # envelope check remains as defense-in-depth behind this.
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path,
            registry=ExecutorRegistry(),
            pack_overrides={
                "envelope": {
                    "allowed_actions": [],
                    "max_actions_per_hour": 5,
                    "max_action_ttl_minutes": 30,
                    "require_reversible": True,
                    "confidence_floor": 0.9,
                    "allow_slm_decisions": False,
                }
            },
        )
        for _ in range(3):
            await loop.tick()
        assert loop.machine.mode is OperatingMode.BOOTSTRAP
        assert loop.status()["policy_version"] is None

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert loop.status()["live_actions"] == 0
        assert not journal_records(journal)

    @respx.mock
    async def test_protected_target_never_reaches_the_executor(
        self, tmp_path: Path
    ) -> None:
        executor = RecordingExecutor()
        registry = ExecutorRegistry()
        registry.register(executor)
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, registry=registry
        )
        await drive_to_autonomous(loop, clock)

        # The configured control-plane address is protected - the guard
        # refuses it before any executor runs, and the refusal journals.
        sentinel.queue.put_nowait({**GOOD_ALERT, "id": "al-2", "value": "198.51.100.9"})
        await loop.tick()

        assert executor.enforced == []
        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["execution"]["status"] == "refused"
        assert records[0]["execution"]["reason"] == "protected-target"


class TestPolicyExpiry:
    @respx.mock
    async def test_expiry_undoes_live_actions_and_goes_passive(
        self, tmp_path: Path
    ) -> None:
        key = make_policy_key()
        # A pack that expires three minutes after the fixture's NOW: the
        # drive to AUTONOMOUS lands at ~91s, enforcement at ~91s, expiry
        # at ~251s.
        pack_bytes = make_pack_bytes(key, not_after=WARDEN_NOW + timedelta(minutes=3))
        clock = FakeClock()
        data_dir = tmp_path / "data"
        store = PolicyStore(data_dir)
        store.save_credentials("wn-test", "node-tok")
        journal = Journal(data_dir / "journal.jsonl")
        metrics = WardenMetrics()
        sync = PolicySync(
            trust_root=make_root(key),
            store=store,
            base_url=CP,
            enrollment_token=None,
            clock=clock,
            metrics=metrics,
        )
        sentinel = Sentinel(
            bind_host="127.0.0.1", port=free_port(), token="t", metrics=metrics
        )
        executor = RecordingExecutor()
        registry = ExecutorRegistry()
        registry.register(executor)
        respx.get(f"{CP}/api/v1/edge/policy").mock(
            side_effect=[
                httpx.Response(200, json=policy_response_doc(pack_bytes)),
                *[httpx.Response(503) for _ in range(8)],
            ]
        )

        def guard_for(pack: PolicyPack) -> TargetGuard:
            return TargetGuard.from_pack(pack)

        loop = DecisionLoop(
            deps=LoopDeps(
                sync=sync,
                sentinel=sentinel,
                journal=journal,
                registry=registry,
                guard_provider=guard_for,
                clock=clock,
                metrics=metrics,
            ),
            interval_seconds=60.0,
            max_alert_batch=10,
            grace_window_seconds=60.0,
            machine=ModeMachine(grace_window_seconds=60.0),
        )

        # Reach AUTONOMOUS and enforce one live action.
        await loop.tick()
        for _ in range(3):
            clock.advance(seconds=10)
            await loop.tick()
        clock.advance(seconds=61)
        await loop.tick()
        assert loop.machine.mode is OperatingMode.AUTONOMOUS
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert executor.enforced == [("block_ip", "198.51.100.7")]
        assert len(loop._live) == 1

        # The clock passes not_after: undo, then PASSIVE - never stale
        # enforcement.
        clock.advance(minutes=2)
        await loop.tick()
        assert loop.machine.mode is OperatingMode.PASSIVE
        assert executor.undone == [("block_ip", "198.51.100.7")]
        assert loop._live == {}

        # PASSIVE never enforces on stale authority: a queued alert stays
        # queued and no new allow record lands.
        records_after_undo = journal_records(journal)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert sentinel.queue.qsize() == 1
        assert journal_records(journal) == records_after_undo
        undo_records = [
            r for r in records_after_undo if r["idempotency_key"].endswith(":undo")
        ]
        assert len(undo_records) == 1
        assert undo_records[0]["execution"]["status"] == "undone"
        assert undo_records[0]["execution"]["reason"] == "policy-expired"


class TestRevocation:
    @respx.mock
    async def test_observed_revocation_undoes_and_halts(self, tmp_path: Path) -> None:
        executor = RecordingExecutor()
        registry = ExecutorRegistry()
        registry.register(executor)
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, registry=registry
        )
        await drive_to_autonomous(loop, clock)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert executor.enforced == [("block_ip", "198.51.100.7")]

        # The policy route now answers 401 - observed revocation.
        policy_route = respx.get(f"{CP}/api/v1/edge/policy")
        policy_route.mock(return_value=httpx.Response(401))
        await loop.tick()
        assert loop.machine.mode is OperatingMode.REVOKED
        assert executor.undone == [("block_ip", "198.51.100.7")]
        assert loop.status()["halted"] is True

        # The loop is halted: no further sync attempts, no enforcement.
        calls = policy_route.call_count
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        clock.advance(hours=1)
        await loop.tick()
        await loop.tick()
        assert policy_route.call_count == calls
        assert executor.enforced == [("block_ip", "198.51.100.7")]
        assert loop.machine.mode is OperatingMode.REVOKED


class TestSyncedModeObserves:
    @respx.mock
    async def test_nothing_enforces_before_autonomous(self, tmp_path: Path) -> None:
        executor = RecordingExecutor()
        registry = ExecutorRegistry()
        registry.register(executor)
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, registry=registry
        )
        await loop.tick()
        assert loop.machine.mode is OperatingMode.SYNCED
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        clock.advance(minutes=1)
        await loop.tick()
        clock.advance(minutes=1)
        await loop.tick()
        assert loop.machine.mode is OperatingMode.SYNCED
        assert executor.enforced == []
        assert not journal_records(journal)
        assert sentinel.queue.qsize() == 1


class TestExecutorHonesty:
    @respx.mock
    async def test_dry_run_executor_journals_dry_run_not_executed(
        self, tmp_path: Path
    ) -> None:
        registry = ExecutorRegistry()
        registry.register(DryRunExecutor())
        loop, sentinel, journal, clock, _registry = make_loop(
            tmp_path, registry=registry
        )
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["execution"]["status"] == "dry_run"
        assert records[0]["execution"]["executor"] == "dry_run"
        # Nothing was really blocked: nothing is live, nothing to undo.
        assert loop.status()["live_actions"] == 0

    @respx.mock
    async def test_unregistered_action_type_never_reaches_a_subprocess(
        self, tmp_path: Path
    ) -> None:
        loop, sentinel, journal, clock, registry = make_loop(tmp_path)
        assert registry.registered_types() == ()  # nothing registered at all
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["execution"]["status"] == "unexecuted"
        assert records[0]["execution"]["executor"] == "none"
        assert loop.status()["live_actions"] == 0


class TestLoopStatus:
    @respx.mock
    async def test_status_surfaces_mode_and_policy(self, tmp_path: Path) -> None:
        loop, _sentinel, _journal, _clock, _registry = make_loop(tmp_path)
        await loop.tick()
        status = loop.status()
        assert status["mode"] == "SYNCED"
        assert status["policy_version"] == 42
        assert status["live_actions"] == 0
        assert status["halted"] is False
