"""Decision-loop tests: the partition, expiry, and cap paths.

The control plane is respx-mocked; the clock is the FakeClock; the
sentinel is an in-process queue (the loop consumes via ``drain``).
These are the enforcement-loop acceptance criteria: nothing enforces
before the grace window lapses, expiry undoes live actions and goes
PASSIVE, per-action TTL expiry undoes, the hourly cap refuses under
sustained alerts, observed revocation halts, and every decision —
allow or refuse — journals in the wire shapes the frozen reconcile
contract carries.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import respx

from core.edge.executors import (
    BLOCKED,
    CLEAR,
    EXECUTED,
    FAILED,
    DryRunBlockIpExecutor,
    ExecutionResult,
    LocalExecutor,
    register,
)
from core.edge.policy import EdgeAction, PolicyPack
from core.edge.target_guard import TargetGuard
from services.warden.engine import DecisionLoop, LoopDeps
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
        self.fail_undo = False

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        self.enforced.append((action.type, target))
        return ExecutionResult(
            success=True, status=EXECUTED, executor=self.name, end_state=BLOCKED
        )

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult:
        self.undone.append((action.type, target))
        if self.fail_undo:
            return ExecutionResult(
                success=False,
                status=FAILED,
                executor=self.name,
                end_state=BLOCKED,
                code="undo-failed",
                message="nft delete failed",
            )
        return ExecutionResult(
            success=True, status=EXECUTED, executor=self.name, end_state=CLEAR
        )


def make_registry(executor: LocalExecutor | None = None) -> dict[str, LocalExecutor]:
    """A registry with exactly one executor (or none, for refusal tests)."""
    registry: dict[str, LocalExecutor] = {}
    if executor is not None:
        register(registry, executor)
    return registry


def make_loop(
    tmp_path: Path,
    *,
    clock: FakeClock | None = None,
    registry: dict[str, LocalExecutor] | None = None,
    pack_overrides: dict[str, Any] | None = None,
    grace_window_seconds: float = 900.0,
    slm: LocalSlm | None = None,
) -> tuple[DecisionLoop, Sentinel, Journal, FakeClock, dict[str, LocalExecutor]]:
    """A loop over a respx-mocked sync, an in-process sentinel, a journal.

    The policy route serves the signed pack once and then 503s forever —
    the outage every partition test drives into.
    """
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
    executors = (
        registry if registry is not None else make_registry(DryRunBlockIpExecutor())
    )
    pack_bytes = make_pack_bytes(key, **(pack_overrides or {}))
    served = {"pack": False}

    def policy_handler(request: httpx.Request) -> httpx.Response:
        if not served["pack"]:
            served["pack"] = True
            return httpx.Response(200, json=policy_response_doc(pack_bytes))
        return httpx.Response(503)

    respx.get(f"{CP}/api/v1/edge/policy").mock(side_effect=policy_handler)

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
            registry=executors,
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
    return loop, sentinel, journal, clock, executors


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
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path, registry=make_registry(executor)
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
        assert records[0]["action_type"] == "block_ip"
        assert records[0]["target"] == "198.51.100.7"
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
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
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
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path, registry=make_registry(executor)
        )
        await drive_to_autonomous(loop, clock)

        # The configured control-plane address is protected - the guard
        # refuses it before any executor runs, and the refusal journals
        # as a wire-shaped non-enforcement record (action_type "none").
        sentinel.queue.put_nowait({**GOOD_ALERT, "id": "al-2", "value": "198.51.100.9"})
        await loop.tick()

        assert executor.enforced == []
        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["action_type"] == "none"
        assert records[0]["target"] == "198.51.100.9"
        assert records[0]["execution"]["status"] == "failed"
        assert records[0]["execution"]["executor"] == "decision"
        assert "protected-target" in records[0]["decision_rule"]

    @respx.mock
    async def test_pack_whose_rules_exceed_the_envelope_never_takes_force(
        self, tmp_path: Path
    ) -> None:
        # A disallowed action type cannot even reach the ladder: the v1
        # pack schema closes the action vocabulary and the pack validator
        # refuses a rule the envelope's allowlist never allows
        # (P-RULE-UNENFORCEABLE). The ladder's own allowlist step —
        # proven at core/edge level in tests/unit/edge/test_decision.py —
        # is the backstop for a mismatch constructed any other way. What
        # the engine owes here is fail-closed ingestion: the pack
        # installs nothing, nothing enforces, nothing journals, and the
        # node keeps retrying sync rather than half-trusting the pack.
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            registry=make_registry(executor),
            pack_overrides={
                "rules": [
                    {
                        "rule_id": "edge-002",
                        "match": {
                            "indicator": "ip",
                            "mitre": ["T1071"],
                            "min_local_confidence": 0.85,
                        },
                        "action": {"type": "block_ip", "ttl_minutes": 10},
                    }
                ],
                "envelope": {
                    "allowed_actions": [],
                    "max_actions_per_hour": 5,
                    "max_action_ttl_minutes": 30,
                    "require_reversible": True,
                    "confidence_floor": 0.9,
                    "allow_slm_decisions": False,
                },
            },
        )
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        for _ in range(3):
            clock.advance(minutes=1)
            await loop.tick()

        assert executor.enforced == []
        assert journal_records(journal) == []
        assert loop.machine.mode is OperatingMode.BOOTSTRAP


class TestActionTtl:
    """Per-action TTL expiry: undo, journal, retry a failed undo."""

    @respx.mock
    async def test_action_ttl_expiry_undoes_live_action(self, tmp_path: Path) -> None:
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            registry=make_registry(executor),
            pack_overrides={
                "rules": [
                    {
                        "rule_id": "edge-ttl",
                        "match": {
                            "indicator": "ip",
                            "mitre": ["T1071"],
                            "min_local_confidence": 0.85,
                        },
                        "action": {"type": "block_ip", "ttl_minutes": 10},
                    }
                ],
            },
        )
        await drive_to_autonomous(loop, clock)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert executor.enforced == [("block_ip", "198.51.100.7")]
        assert len(loop._live) == 1

        # The rule's own TTL (10 min) lapses while AUTONOMOUS holds: the
        # next tick undoes the live action and journals the undo.
        clock.advance(minutes=11)
        await loop.tick()
        assert loop.machine.mode is OperatingMode.AUTONOMOUS
        assert executor.undone == [("block_ip", "198.51.100.7")]
        assert loop._live == {}
        records = journal_records(journal)
        undo_records = [
            r for r in records if r["idempotency_key"] == "block_ip:198.51.100.7:undo"
        ]
        assert len(undo_records) == 1
        assert undo_records[0]["action_type"] == "none"
        assert undo_records[0]["target"] == "198.51.100.7"
        # Non-enforcement records carry the wire's not-an-enforcement
        # status; the undo's own outcome rides decision_rule.
        assert undo_records[0]["execution"]["status"] == "failed"
        assert "ttl-expired" in undo_records[0]["decision_rule"]

    @respx.mock
    async def test_failed_ttl_undo_retries_next_tick(self, tmp_path: Path) -> None:
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            registry=make_registry(executor),
            pack_overrides={
                "rules": [
                    {
                        "rule_id": "edge-ttl",
                        "match": {
                            "indicator": "ip",
                            "mitre": ["T1071"],
                            "min_local_confidence": 0.85,
                        },
                        "action": {"type": "block_ip", "ttl_minutes": 10},
                    }
                ],
            },
        )
        await drive_to_autonomous(loop, clock)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert len(loop._live) == 1

        # The undo subprocess fails: the block is still live (end state
        # BLOCKED), so the action stays live and retries — a failed undo
        # is never allowed to read as "containment lifted".
        executor.fail_undo = True
        clock.advance(minutes=11)
        await loop.tick()
        assert loop._live
        records = journal_records(journal)
        assert records[-1]["execution"]["status"] == "failed"
        assert "ttl-expired" in records[-1]["decision_rule"]
        assert "undo of block_ip:198.51.100.7" in records[-1]["decision_rule"]
        assert "failed" in records[-1]["decision_rule"]

        # The retry converges: next tick, undo succeeds, live clears.
        executor.fail_undo = False
        clock.advance(minutes=1)
        await loop.tick()
        assert loop._live == {}
        assert executor.undone == [
            ("block_ip", "198.51.100.7"),
            ("block_ip", "198.51.100.7"),
        ]


class TestPolicyExpiry:
    @respx.mock
    async def test_expiry_undoes_live_actions_and_goes_passive(
        self, tmp_path: Path
    ) -> None:
        # A pack that expires three minutes after the fixture's NOW: the
        # drive to AUTONOMOUS lands at ~91s, enforcement at ~91s, expiry
        # at ~211s.
        clock = FakeClock()
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            clock=clock,
            registry=make_registry(executor),
            grace_window_seconds=60.0,
            pack_overrides={"not_after": WARDEN_NOW + timedelta(minutes=3)},
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
        # queued and no new record lands.
        records_after_undo = journal_records(journal)
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()
        assert sentinel.queue.qsize() == 1
        assert journal_records(journal) == records_after_undo
        undo_records = [
            r for r in records_after_undo if r["idempotency_key"].endswith(":undo")
        ]
        assert len(undo_records) == 1
        assert undo_records[0]["action_type"] == "none"
        assert undo_records[0]["target"] == "198.51.100.7"
        assert undo_records[0]["execution"]["status"] == "failed"
        assert "policy-expired" in undo_records[0]["decision_rule"]


class TestHourlyCap:
    """The envelope's max_actions_per_hour under sustained alerts."""

    def cap_pack(self, **overrides: Any) -> dict[str, Any]:
        envelope = {
            "allowed_actions": ["block_ip"],
            "max_actions_per_hour": 1,
            "max_action_ttl_minutes": 30,
            "require_reversible": True,
            "confidence_floor": 0.9,
            "allow_slm_decisions": False,
        }
        return {"envelope": {**envelope, **overrides}}

    @respx.mock
    async def test_cap_refuses_after_the_limit_and_resets_next_hour(
        self, tmp_path: Path
    ) -> None:
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            registry=make_registry(executor),
            pack_overrides=self.cap_pack(),
        )
        await drive_to_autonomous(loop, clock)

        # Two alerts in one batch, cap 1/hour: the first enforces, the
        # second is refused with a journal record — silent dropping of
        # denied actions is exactly the failure this test forbids.
        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        sentinel.queue.put_nowait({**GOOD_ALERT, "id": "al-2", "value": "198.51.100.8"})
        await loop.tick()
        assert executor.enforced == [("block_ip", "198.51.100.7")]

        records = journal_records(journal)
        assert len(records) == 2
        by_key = {r["idempotency_key"]: r for r in records}
        allowed = by_key["block_ip:198.51.100.7"]
        refused = by_key["refused:block_ip:198.51.100.8"]
        assert allowed["execution"]["status"] == "executed"
        assert refused["action_type"] == "none"
        assert refused["target"] == "198.51.100.8"
        assert refused["execution"]["status"] == "failed"
        assert "rate-cap-reached" in refused["decision_rule"]
        assert loop.status()["live_actions"] == 1

        # The budget is a fixed wall-hour bucket: crossing into the next
        # hour resets it, and the next alert enforces again.
        clock.advance(minutes=50)  # 12:15-ish -> past 13:00
        sentinel.queue.put_nowait(
            {**GOOD_ALERT, "id": "al-3", "value": "198.51.100.10"}
        )
        await loop.tick()
        assert executor.enforced == [
            ("block_ip", "198.51.100.7"),
            ("block_ip", "198.51.100.10"),
        ]
        # Those 50 minutes also carried the first block past its 30-minute
        # TTL: the tick's expiry sweep lifted it before the new alert
        # arrived — an hourly cap reset never resurrects expired authority.
        assert executor.undone == [("block_ip", "198.51.100.7")]
        assert loop.status()["live_actions"] == 1

    @respx.mock
    async def test_sustained_alerts_never_exceed_one_live_action_per_hour(
        self, tmp_path: Path
    ) -> None:
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path,
            registry=make_registry(executor),
            pack_overrides=self.cap_pack(),
        )
        await drive_to_autonomous(loop, clock)

        # Five alerts inside one wall hour, cap 1: exactly one enforces;
        # the other four refuse and journal.
        for i in range(5):
            sentinel.queue.put_nowait(
                {**GOOD_ALERT, "id": f"al-{i}", "value": f"198.51.100.{20 + i}"}
            )
        await loop.tick()
        assert len(executor.enforced) == 1
        records = journal_records(journal)
        assert len(records) == 5
        enforced_count = sum(
            1 for r in records if r["execution"]["status"] == "executed"
        )
        refused_count = sum(
            1
            for r in records
            if r["action_type"] == "none" and "rate-cap-reached" in r["decision_rule"]
        )
        assert enforced_count == 1
        assert refused_count == 4


class TestRevocation:
    @respx.mock
    async def test_observed_revocation_undoes_and_halts(self, tmp_path: Path) -> None:
        executor = RecordingExecutor()
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path, registry=make_registry(executor)
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
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path, registry=make_registry(executor)
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
        loop, sentinel, journal, clock, _reg = make_loop(
            tmp_path, registry=make_registry(DryRunBlockIpExecutor())
        )
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["execution"]["status"] == "dry_run"
        assert records[0]["execution"]["executor"] == "dryrun"
        # Nothing was really blocked: nothing is live, nothing to undo.
        assert loop.status()["live_actions"] == 0

    @respx.mock
    async def test_unregistered_action_type_never_reaches_a_subprocess(
        self, tmp_path: Path
    ) -> None:
        # Empty registry: the ladder's allow decision still journals, but
        # executor_for refuses before any subprocess can exist — recorded
        # honestly as a failed execution, never a claimed block.
        loop, sentinel, journal, clock, registry = make_loop(
            tmp_path, registry=make_registry(None)
        )
        assert registry == {}
        await drive_to_autonomous(loop, clock)

        sentinel.queue.put_nowait(dict(GOOD_ALERT))
        await loop.tick()

        records = journal_records(journal)
        assert len(records) == 1
        assert records[0]["execution"]["status"] == "failed"
        assert records[0]["execution"]["executor"] == "none"
        assert "unregistered-action-type" in records[0]["decision_rule"]
        assert loop.status()["live_actions"] == 0


class TestLoopStatus:
    @respx.mock
    async def test_status_surfaces_mode_and_policy(self, tmp_path: Path) -> None:
        loop, _sentinel, _journal, _clock, _reg = make_loop(tmp_path)
        await loop.tick()
        status = loop.status()
        assert status["mode"] == "SYNCED"
        assert status["policy_version"] == 42
        assert status["live_actions"] == 0
        assert status["halted"] is False
