"""The Warden decision loop: sync cadence, mode transitions, enforcement.

The loop is the process's beating heart — one component task that, on an
interval: runs a policy-sync cycle, folds the outcome into the mode
machine, undoes live actions when authority lapses or revocation is
observed, and — only in AUTONOMOUS, with a verified pack in force —
drains the Sentinel's queue through the decision ladder and the
executor registry, journaling every decision either way.

Enforcement truth table (fail-closed by construction):

- Mode not AUTONOMOUS → no enforcement pass runs at all. Alerts stay
  queued (bounded) and are handled when — if — AUTONOMOUS arrives.
- AUTONOMOUS but no verified pack → no enforcement (nothing authorizes).
- AUTONOMOUS with a pack → the ladder decides; refusals journal, allows
  execute through the registry and journal with the execution status.
- An action type with no registered executor never reaches a
  subprocess: the registry returns an honest ``unexecuted`` result.

The executor seam is a Protocol plus an allowlist registry (the
``core/platform/service_manager.py`` pattern). v1 ships a DryRun
executor: every decision journals, nothing actually blocks, and the
status payload reports the registry — the concrete nftables executor is
the parallel executors work item's deliverable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from core.edge.decision import LocalTriage, decide_local_action
from core.edge.envelope import budget_for
from core.edge.policy import AutonomyEnvelope, EdgeAction, EdgeRule, PolicyPack
from core.edge.target_guard import TargetGuard
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics
from services.warden.modes import ModeMachine, OperatingMode
from services.warden.sentinel import Sentinel
from services.warden.sync import PolicySync, SyncOutcome

logger = logging.getLogger(__name__)

__all__ = [
    "DecisionLoop",
    "DryRunExecutor",
    "ExecutionResult",
    "ExecutorRegistry",
    "LocalExecutor",
    "LoopDeps",
    "match_alerts",
]


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The executor seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    """What an executor did — or honestly did not do."""

    status: str  # "executed" | "dry_run" | "unexecuted" | "failed"
    executor: str
    detail: str = ""


class LocalExecutor(Protocol):
    """One local enforcement primitive, idempotent on retry.

    ``enforce`` and ``undo`` are synchronous on purpose: v1 executors are
    local subprocess/OS calls (nftables), not network I/O, and the loop
    treats a slow executor as an operator-visible problem (metrics), not
    a concurrency puzzle.
    """

    name: str
    action_type: str  # e.g. "block_ip"

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult: ...

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult: ...


class ExecutorRegistry:
    """The allowlist between decisions and subprocesses.

    An action type with no registered executor can never reach a
    subprocess — the registry answers with an honest ``unexecuted``
    result that the journal records. The registry also isolates the
    loop from executor exceptions: a raising executor reads as a failed
    execution, not a dead warden.
    """

    def __init__(self) -> None:
        self._executors: dict[str, LocalExecutor] = {}

    def register(self, executor: LocalExecutor) -> None:
        self._executors[executor.action_type] = executor

    def registered_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._executors))

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        return self._dispatch("enforce", action, target)

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult:
        return self._dispatch("undo", action, target)

    def _dispatch(
        self, operation: str, action: EdgeAction, target: str
    ) -> ExecutionResult:
        executor = self._executors.get(action.type)
        if executor is None:
            return ExecutionResult(
                status="unexecuted",
                executor="none",
                detail=f"no executor registered for {action.type}",
            )
        try:
            method = getattr(executor, operation)
            return method(action, target)
        except Exception as exc:  # noqa: BLE001 - executor isolation by design
            logger.exception("warden executor %s %s raised", executor.name, operation)
            return ExecutionResult(
                status="failed", executor=executor.name, detail=str(exc)
            )


class DryRunExecutor:
    """The v1 fallback executor: journals honestly, changes nothing.

    Default whenever no concrete executor is registered for a type —
    every decision still journals, nothing actually blocks, and the
    status payload reports the registry so the mode is never a lie.
    """

    name = "dry_run"
    action_type = "block_ip"

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        return ExecutionResult(
            status="dry_run",
            executor=self.name,
            detail="dry-run mode: no system change",
        )

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult:
        return ExecutionResult(
            status="dry_run",
            executor=self.name,
            detail="dry-run mode: nothing to undo",
        )


# ---------------------------------------------------------------------------
# Alert → rule matching (the runtime's half of triage)
# ---------------------------------------------------------------------------


def _alert_confidence(alert: dict[str, Any]) -> float:
    """The sensor confidence, or 0.0 when absent or unparseable.

    Junk reads as no confidence — the ladder's range gate then refuses
    it, which is the fail-closed direction. Out-of-range values (5.0,
    NaN) pass through and are refused by the ladder itself, which owns
    that precedent.
    """
    raw = alert.get("confidence", 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def match_alerts(
    pack: PolicyPack, alert: dict[str, Any]
) -> list[tuple[EdgeRule, str, LocalTriage]]:
    """The (rule, target, triage) candidates one alert matches.

    A rule matches when the alert's indicator kind equals the rule's
    (``"ip"``), the alert carries a non-empty value for it, and — when
    the rule names MITRE techniques — the alert carries at least one of
    them. Matching is the runtime's job because alerts are runtime
    input; the ladder stays a pure function of the candidates.
    """
    indicator = alert.get("indicator")
    value = alert.get("value")
    if not isinstance(indicator, str) or not isinstance(value, str) or not value:
        return []
    mitre_raw = alert.get("mitre") or ()
    mitre_tags = {tag for tag in mitre_raw if isinstance(tag, str)}
    confidence = _alert_confidence(alert)
    candidates: list[tuple[EdgeRule, str, LocalTriage]] = []
    for rule in pack.rules:
        if rule.indicator != indicator:
            continue
        if rule.mitre and not (set(rule.mitre) & mitre_tags):
            continue
        candidates.append(
            (rule, value, LocalTriage(confidence=confidence, source="sensor"))
        )
    return candidates


# ---------------------------------------------------------------------------
# The loop component
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopDeps:
    """Everything the loop drives — injected so tests can substitute."""

    sync: PolicySync
    sentinel: Sentinel
    journal: Journal
    registry: ExecutorRegistry
    guard_provider: Callable[[PolicyPack], TargetGuard]
    clock: Callable[[], datetime]
    metrics: WardenMetrics


#: A no-authority envelope for the pre-first-pack budget: a zero cap and
#: a floor of 1.0 mean even a bug cannot enforce before a pack installs.
_ZERO_ENVELOPE = AutonomyEnvelope(
    allowed_actions=(),
    max_actions_per_hour=0,
    max_action_ttl_minutes=0,
    require_reversible=True,
    confidence_floor=1.0,
    allow_slm_decisions=False,
)


class DecisionLoop:
    """One asyncio component: sync → mode → undo → enforce → journal.

    Registered into the process like any component (``run(shutdown)``
    signature); ``tick`` is its body, callable directly in tests.
    """

    def __init__(
        self,
        *,
        deps: LoopDeps,
        interval_seconds: float,
        max_alert_batch: int,
        grace_window_seconds: float,
        machine: ModeMachine | None = None,
        mode_observer: Callable[[str], None] | None = None,
    ) -> None:
        self._deps = deps
        self._interval = interval_seconds
        self._max_batch = max_alert_batch
        self.machine = machine or ModeMachine(grace_window_seconds=grace_window_seconds)
        self._mode_observer = mode_observer
        self._pack: PolicyPack | None = None
        self._budget = budget_for(_ZERO_ENVELOPE)
        self._live: dict[str, tuple[EdgeAction, str]] = {}
        self._halted = False

    # ------------------------------------------------------------------
    # Component protocol
    # ------------------------------------------------------------------

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """The component task: tick on the interval until shutdown."""
        while not shutdown_event.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - the loop survives to journal
                logger.exception("warden loop tick failed; continuing")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------
    # The tick
    # ------------------------------------------------------------------

    async def tick(self) -> None:
        """One cycle: sync, fold, expire, grace-check, enforce."""
        if self._halted:
            return
        outcome = await self._deps.sync.sync_once()
        self._deps.metrics.sync_attempts.labels(
            outcome=self._outcome_label(outcome)
        ).inc()
        now = self._deps.clock()
        self.machine.note_sync(outcome, now=now)
        self._publish_mode()
        if outcome.pack is not None:
            self._install_pack(outcome.pack)

        if self.machine.mode is OperatingMode.REVOKED:
            # Revocation can only tighten: undo what is live, then halt.
            self._undo_all("revoked", now=now)
            self._halted = True
            logger.error("warden: revocation observed — halting the loop")
            return

        if (
            self._pack is not None
            and now >= self._pack.not_after
            and self.machine.mode is not OperatingMode.PASSIVE
        ):
            # Authority lapsed: undo first, then PASSIVE. A crash between
            # the two retries the undo (idempotent) — never the reverse.
            self._undo_all("policy-expired", now=now)
            self.machine.note_pack_expiry(now=now)
            self._publish_mode()

        if self._pack is not None:
            self.machine.note_grace_check(
                now=now, pack_in_force=now < self._pack.not_after
            )
            self._publish_mode()

        if self.machine.can_enforce() and self._pack is not None:
            self._enforce_pass(now=now)

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------

    def _enforce_pass(self, *, now: datetime) -> None:
        pack = self._pack
        assert pack is not None  # tick gates on a pack in force
        alerts = self._deps.sentinel.drain(self._max_batch)
        for alert in alerts:
            candidates = match_alerts(pack, alert)
            if not candidates:
                self._deps.metrics.decisions.labels(result="unmatched").inc()
                continue
            for rule, target, triage in candidates:
                decision = decide_local_action(
                    pack,
                    rule,
                    triage,
                    target,
                    self._deps.guard_provider(pack),
                    self._budget,
                    now=now,
                )
                self._record_decision(decision, now=now)

    def _record_decision(self, decision: Any, *, now: datetime) -> None:
        """Journal one ladder outcome — allows and refusals alike."""
        metrics = self._deps.metrics
        if not decision.allowed:
            metrics.decisions.labels(result="refused").inc()
            self._journal(
                mode=self.machine.mode.value,
                idempotency_key="none",
                action_type="none",
                target="",
                decision_rule=decision.decision_rule,
                execution={
                    "status": "refused",
                    "reason": decision.code,
                    "at": _iso(now),
                },
                ts=_iso(now),
            )
            return
        assert decision.action is not None and decision.target is not None
        metrics.decisions.labels(result="allowed").inc()
        result = self._deps.registry.enforce(decision.action, decision.target)
        metrics.enforcements.labels(
            status=result.status, executor=result.executor
        ).inc()
        key = f"{decision.action.type}:{decision.target}"
        if result.status == "executed":
            # Only a real execution is live; dry-run has nothing to undo.
            self._live[key] = (decision.action, decision.target)
            self._deps.metrics.live_actions.set(len(self._live))
        self._journal(
            mode=self.machine.mode.value,
            idempotency_key=key,
            action_type=decision.action.type,
            target=decision.target,
            decision_rule=decision.decision_rule,
            execution={
                "status": result.status,
                "executor": result.executor,
                "detail": result.detail,
                "at": _iso(now),
            },
            ts=_iso(now),
        )

    def _undo_all(self, reason: str, *, now: datetime) -> None:
        """Undo every live action, journaling each undo."""
        for key, (action, target) in self._live.items():
            result = self._deps.registry.undo(action, target)
            self._deps.metrics.enforcements.labels(
                status=result.status, executor=result.executor
            ).inc()
            self._deps.metrics.undo_total.labels(reason=reason).inc()
            self._journal(
                mode=self.machine.mode.value,
                idempotency_key=f"{key}:undo",
                action_type=action.type,
                target=target,
                decision_rule=f"undo of {key} ({reason})",
                execution={
                    "status": "undone",
                    "executor": result.executor,
                    "detail": result.detail,
                    "reason": reason,
                    "at": _iso(now),
                },
                ts=_iso(now),
            )
        self._live.clear()
        self._deps.metrics.live_actions.set(0)

    # ------------------------------------------------------------------
    # State plumbing
    # ------------------------------------------------------------------

    def _install_pack(self, pack: PolicyPack) -> None:
        self._pack = pack
        # The budget is derived from the envelope — the only sanctioned
        # construction (budget_for), so the cap cannot drift from the pack.
        self._budget = budget_for(pack.autonomy_envelope)

    def _journal(self, **fields: Any) -> None:
        try:
            self._deps.journal.append(**fields)
            self._deps.metrics.journal_appends.labels(result="appended").inc()
        except Exception:  # noqa: BLE001 - a poisoned journal is surfaced, not fatal
            logger.exception("warden journal append failed")
            self._deps.metrics.journal_appends.labels(result="refused").inc()

    def _outcome_label(self, outcome: SyncOutcome) -> str:
        if outcome.ok:
            return "ok"
        if outcome.revoked:
            return "revoked"
        return "failed"

    def _publish_mode(self) -> None:
        if self._mode_observer is not None:
            self._mode_observer(self.machine.mode.value)

    # ------------------------------------------------------------------
    # Status surface (the process's status payload reads through these)
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Loop facts for the process status payload."""
        return {
            "mode": self.machine.mode.value,
            "missed_syncs": self.machine.missed_syncs,
            "policy_version": self._pack.policy_version if self._pack else None,
            "live_actions": len(self._live),
            "halted": self._halted,
        }
