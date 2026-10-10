"""The Warden decision loop: sync cadence, mode transitions, enforcement.

The loop is the process's beating heart — one component task that, on an
interval: runs a policy-sync cycle, folds the outcome into the mode
machine, undoes live actions when their authority lapses (per-action TTL,
policy expiry, a policy version that no longer authorizes them, or
revocation), and — only in AUTONOMOUS, with a verified pack in force —
drains the Sentinel's queue through the decision ladder and the core
executor registry, journaling every decision either way.

Enforcement truth table (fail-closed by construction):

- Mode not AUTONOMOUS → no enforcement pass runs at all. Alerts stay
  queued (bounded) and are handled when — if — AUTONOMOUS arrives.
- AUTONOMOUS but no verified pack → no enforcement (nothing authorizes).
- AUTONOMOUS with a pack → the ladder decides; refusals journal, allows
  execute through the core registry and journal with the execution
  status.
- An action type with no registered executor never reaches a subprocess:
  the registry answers with an honest failed result the journal records.

The executor seam is ``core.edge.executors`` — the same Protocol,
allowlist registry, and DryRun fallback the executors work item ships
for every local caller. The loop dispatches only through
``executor_for``; an action type the registry does not name cannot reach
a subprocess.

Journal records are wire-exact by construction: they must survive the
frozen ``POST /api/v1/edge/journal`` contract unchanged, because the
server recomputes the hash over the record as parsed — any field it
drops, the chain would break at reconcile time. The shapes:

- **Enforcement** — ``action_type``/``target`` name what was acted on;
  ``idempotency_key = f"{type}:{target}"`` is the server's dedupe key;
  ``execution.status`` maps the executor result onto the wire
  vocabulary (a ``no-op`` enforcement reports ``executed``: the
  containment is in force either way — that is what the record commits
  to).
- **Refusals and undos** are non-enforcement records: ``action_type``
  is ``none`` — in no envelope, so the control plane's legality gate
  refuses them from the approval merge while the chain still advances
  and the record stays tamper-evidently journaled — and
  ``execution.status`` is ``failed``, the wire's only not-an-enforcement
  value. The class of refusal and the outcome of the undo ride
  ``decision_rule``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from core.edge.decision import EdgeDecision, decide_local_action
from core.edge.envelope import budget_for
from core.edge.executors import (
    BLOCKED,
    CLEAR,
    DRY_RUN,
    EXECUTED,
    FAILED,
    NO_OP,
    UNKNOWN,
    ExecutionResult,
    LocalExecutor,
    UnregisteredActionType,
    executor_for,
)
from core.edge.policy import AutonomyEnvelope, EdgeAction, EdgeRule, PolicyPack
from core.edge.target_guard import TargetGuard
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics
from services.warden.modes import ModeMachine, OperatingMode
from services.warden.sentinel import Sentinel
from services.warden.sync import PolicySync, SyncOutcome
from services.warden.triage import (
    FoldedTriage,
    LocalSlm,
    fold_triage,
    render_decision_rule,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DecisionLoop",
    "LiveAction",
    "LoopDeps",
    "MatchedCandidate",
    "match_alerts",
]

#: The wire contract's ceilings for free-text record fields. The journal
#: must carry every decision — the chain's contiguity is what makes
#: reconciliation credible — so an over-long alert-shaped value is clipped
#: to what the frozen wire can carry, never dropped.
_KEY_LIMIT = 200
_TARGET_LIMIT = 256
_RULE_LIMIT = 1000

#: Executor result status → the wire's execution.status vocabulary.
_WIRE_EXECUTION_STATUS = {
    EXECUTED: "executed",
    NO_OP: "executed",
    DRY_RUN: "dry_run",
    FAILED: "failed",
}


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text: str, limit: int) -> str:
    return text[:limit]


# ---------------------------------------------------------------------------
# Live actions — what is currently in force and must be undone when it lapses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveAction:
    """A reversible action in force: what, where, enforced until when."""

    action: EdgeAction
    target: str
    enforced_at: datetime
    expires_at: datetime


def _is_live_result(result: ExecutionResult) -> bool:
    """Whether an enforcement result leaves containment possibly in force.

    BLOCKED obviously; UNKNOWN deliberately — a probe that could not
    answer must not orphan a possibly-live block, so an unknown state
    reads as live and gets an undo attempt at expiry. Dry-run never
    changes the system and is never live.
    """
    return result.end_state in (BLOCKED, UNKNOWN)


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


@dataclass(frozen=True)
class MatchedCandidate:
    """One (rule, target) match with the triage the ladder will see.

    ``folded`` is the fold's verdict — sensor or SLM confidence — plus
    the advisory opinion that rides along for the journal and metrics.
    """

    rule: EdgeRule
    target: str
    folded: FoldedTriage


def match_alerts(
    pack: PolicyPack,
    alert: dict[str, Any],
    slm: LocalSlm | None = None,
) -> list[MatchedCandidate]:
    """The candidates one alert matches, each folded through the SLM channel.

    A rule matches when the alert's indicator kind equals the rule's
    (``"ip"``), the alert carries a non-empty value for it, and — when
    the rule names MITRE techniques — the alert carries at least one of
    them. Matching is the runtime's job because alerts are runtime
    input; the ladder stays a pure function of the candidates. The fold
    applies the envelope's SLM authority: advisory ranking rides along,
    and the sensor confidence decides unless the signed pack says
    otherwise.
    """
    indicator = alert.get("indicator")
    value = alert.get("value")
    if not isinstance(indicator, str) or not isinstance(value, str) or not value:
        return []
    mitre_raw = alert.get("mitre") or ()
    mitre_tags = {tag for tag in mitre_raw if isinstance(tag, str)}
    confidence = _alert_confidence(alert)
    candidates: list[MatchedCandidate] = []
    for rule in pack.rules:
        if rule.indicator != indicator:
            continue
        if rule.mitre and not (set(rule.mitre) & mitre_tags):
            continue
        opinion = slm.rank(alert, rule) if slm is not None else None
        folded = fold_triage(confidence, opinion, pack.autonomy_envelope)
        candidates.append(MatchedCandidate(rule=rule, target=value, folded=folded))
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
    registry: Mapping[str, LocalExecutor]
    guard_provider: Callable[[PolicyPack], TargetGuard]
    clock: Callable[[], datetime]
    metrics: WardenMetrics
    # The optional SLM triage channel; None means not configured, which
    # is itself honest — the status payload reports it as absent.
    slm: LocalSlm | None = None


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
        self._live: dict[str, LiveAction] = {}
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
        """One cycle: sync, fold, undo lapses, grace-check, enforce."""
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
            self._install_pack(outcome.pack, now=now)

        if self.machine.mode is OperatingMode.REVOKED:
            # Revocation can only tighten: undo what is live (one best-
            # effort pass — a lift that fails is journaled and logged, and
            # the halt leaves the journal for forensic pull), then halt.
            self._undo_all("revoked", now=now)
            self._halted = True
            logger.error("warden: revocation observed — halting the loop")
            return

        if self._pack is not None and now >= self._pack.not_after:
            # Authority lapsed: PASSIVE, and every PASSIVE tick below
            # lifts what is still live until the node is clean. A failed
            # lift retries — a block must not outlive its authority by
            # outliving one attempt.
            if self.machine.mode is not OperatingMode.PASSIVE:
                self.machine.note_pack_expiry(now=now)
                self._publish_mode()

        self._expire_live(now=now)

        if self.machine.mode is OperatingMode.PASSIVE and self._live:
            self._undo_all("policy-expired", now=now)

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
            candidates = match_alerts(pack, alert, self._deps.slm)
            if not candidates:
                self._deps.metrics.decisions.labels(result="unmatched").inc()
                continue
            for candidate in candidates:
                self._count_slm_outcome(candidate)
                decision = decide_local_action(
                    pack,
                    candidate.rule,
                    candidate.folded.triage,
                    candidate.target,
                    self._deps.guard_provider(pack),
                    self._budget,
                    now=now,
                )
                self._record_decision(
                    decision,
                    candidate.rule,
                    candidate.target,
                    now=now,
                    folded=candidate.folded,
                )

    def _count_slm_outcome(self, candidate: MatchedCandidate) -> None:
        """How the SLM channel contributed to this candidate — when configured.

        ``deciding`` is a signed opt-in; ``advisory`` ranked without
        deciding; ``unavailable`` is a disabled or failed channel. Not
        counted when no SLM is configured: the counter is about the
        channel, not about its absence.
        """
        if self._deps.slm is None:
            return
        folded = candidate.folded
        if folded.opinion is None:
            outcome = "unavailable"
        else:
            outcome = "deciding" if folded.deciding else "advisory"
        self._deps.metrics.slm_opinions.labels(outcome=outcome).inc()

    def _record_decision(
        self,
        decision: EdgeDecision,
        rule: EdgeRule,
        target: str,
        *,
        now: datetime,
        folded: FoldedTriage | None = None,
    ) -> None:
        """Journal one ladder outcome — allows and refusals alike.

        The decision_rule the journal records is the ladder's render plus
        the fold's advisory annotation: an operator reading the record
        sees both channels and which one decided. Refusals are
        non-enforcement records — action_type ``none``, wire-legal
        execution fields (the wire has no "refused" status, so the
        refusal code rides decision_rule) — the chain stays contiguous
        and the legality gate keeps them out of the approval merge.
        """
        metrics = self._deps.metrics
        rule_text = render_decision_rule(decision.decision_rule, folded)
        if not decision.allowed:
            metrics.decisions.labels(result="refused").inc()
            self._journal(
                mode=self.machine.mode.value,
                idempotency_key=_clip(
                    f"refused:{rule.action.type}:{target}", _KEY_LIMIT
                ),
                action_type="none",
                target=_clip(target, _TARGET_LIMIT),
                decision_rule=_clip(f"{decision.code}: {rule_text}", _RULE_LIMIT),
                execution={"status": "failed", "executor": "decision", "at": _iso(now)},
                ts=_iso(now),
            )
            return
        assert decision.action is not None and decision.target is not None
        metrics.decisions.labels(result="allowed").inc()
        result = self._enforce(decision.action, decision.target)
        metrics.enforcements.labels(
            status=result.status, executor=result.executor
        ).inc()
        key = f"{decision.action.type}:{decision.target}"
        if _is_live_result(result):
            self._live[key] = LiveAction(
                action=decision.action,
                target=decision.target,
                enforced_at=now,
                expires_at=now + timedelta(minutes=decision.action.ttl_minutes),
            )
            self._deps.metrics.live_actions.set(len(self._live))
        if not result.success:
            # The rule allowed the action; the execution failed. The wire
            # execution dict has no free-text field, so the reason rides
            # decision_rule — an auditor can see why nothing was blocked.
            rule_text = (
                f"{rule_text} — execution failed ({result.code}): {result.message}"
            )
        self._journal(
            mode=self.machine.mode.value,
            idempotency_key=_clip(key, _KEY_LIMIT),
            action_type=decision.action.type,
            target=_clip(decision.target, _TARGET_LIMIT),
            decision_rule=_clip(rule_text, _RULE_LIMIT),
            execution={
                "status": _WIRE_EXECUTION_STATUS[result.status],
                "executor": result.executor,
                "at": _iso(now),
            },
            ts=_iso(now),
        )

    def _enforce(self, action: EdgeAction, target: str) -> ExecutionResult:
        """One dispatch through the core registry — the allowlist's only door."""
        try:
            executor = executor_for(self._deps.registry, action.type)
        except UnregisteredActionType:
            return ExecutionResult(
                success=False,
                status=FAILED,
                executor="none",
                end_state=CLEAR,
                code="unregistered-action-type",
                message=f"no executor registered for {action.type}",
            )
        try:
            return executor.enforce(action, target)
        except Exception as exc:  # noqa: BLE001 - executor isolation by design
            logger.exception("warden executor %s enforce raised", executor.name)
            return ExecutionResult(
                success=False,
                status=FAILED,
                executor=executor.name,
                end_state=UNKNOWN,
                code="executor-raised",
                message=str(exc),
            )

    def _undo_dispatch(self, action: EdgeAction, target: str) -> ExecutionResult:
        try:
            executor = executor_for(self._deps.registry, action.type)
        except UnregisteredActionType:
            return ExecutionResult(
                success=False,
                status=FAILED,
                executor="none",
                end_state=UNKNOWN,
                code="unregistered-action-type",
                message=f"no executor registered for {action.type}",
            )
        try:
            return executor.undo(action, target)
        except Exception as exc:  # noqa: BLE001 - executor isolation by design
            logger.exception("warden executor %s undo raised", executor.name)
            return ExecutionResult(
                success=False,
                status=FAILED,
                executor=executor.name,
                end_state=UNKNOWN,
                code="executor-raised",
                message=str(exc),
            )

    # ------------------------------------------------------------------
    # Undo paths — journal-driven, so allowed in every mode
    # ------------------------------------------------------------------

    def _undo(self, key: str, live: LiveAction, reason: str, *, now: datetime) -> bool:
        """One lift attempt; True when the entry may leave the live set.

        A failed lift stays live — the next tick retries it. The record
        is a non-enforcement record (action_type ``none``; see module
        docstring), so the wire status is ``failed`` either way and the
        decision_rule carries the true outcome.
        """
        result = self._undo_dispatch(live.action, live.target)
        self._deps.metrics.enforcements.labels(
            status=result.status, executor=result.executor
        ).inc()
        self._deps.metrics.undo_total.labels(reason=reason).inc()
        if not result.success:
            logger.error(
                "warden undo failed (%s): %s -> %s: %s",
                reason,
                key,
                live.target,
                result.message,
            )
        self._journal(
            mode=self.machine.mode.value,
            idempotency_key=_clip(f"{key}:undo", _KEY_LIMIT),
            action_type="none",
            target=_clip(live.target, _TARGET_LIMIT),
            decision_rule=_clip(
                f"undo of {key} ({reason}): {result.status} {result.message}".rstrip(),
                _RULE_LIMIT,
            ),
            execution={
                "status": "failed",
                "executor": result.executor,
                "at": _iso(now),
            },
            ts=_iso(now),
        )
        return result.success

    def _undo_all(self, reason: str, *, now: datetime) -> None:
        """Undo every live action, journaling each lift; failures retry."""
        for key, live in list(self._live.items()):
            if self._undo(key, live, reason, now=now):
                del self._live[key]
        self._deps.metrics.live_actions.set(len(self._live))

    def _expire_live(self, *, now: datetime) -> None:
        """Undo live actions whose TTL lapsed — every mode, every tick."""
        for key, live in list(self._live.items()):
            if now >= live.expires_at:
                if self._undo(key, live, "ttl-expired", now=now):
                    del self._live[key]
        self._deps.metrics.live_actions.set(len(self._live))

    def _shed_unauthorized(self, *, now: datetime) -> None:
        """Lift live actions the pack in force no longer authorizes."""
        pack = self._pack
        if pack is None:
            return
        allowed = set(pack.autonomy_envelope.allowed_actions)
        for key, live in list(self._live.items()):
            if live.action.type not in allowed:
                if self._undo(key, live, "policy-version-change", now=now):
                    del self._live[key]
        self._deps.metrics.live_actions.set(len(self._live))

    # ------------------------------------------------------------------
    # State plumbing
    # ------------------------------------------------------------------

    def _install_pack(self, pack: PolicyPack, *, now: datetime) -> None:
        self._pack = pack
        # The budget is derived from the envelope — the only sanctioned
        # construction (budget_for), so the cap cannot drift from the pack.
        self._budget = budget_for(pack.autonomy_envelope)
        # The SLM channel is re-derived from the pack too: its model bytes
        # and authority both come from the signed manifest and envelope.
        # Idempotent on a same-manifest re-presentation; never raises.
        if self._deps.slm is not None:
            self._deps.slm.reload_for_pack(pack)
        self._shed_unauthorized(now=now)

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

    def current_policy_version(self) -> int | None:
        """The verified pack version the loop holds — the reconciler's citation."""
        return self._pack.policy_version if self._pack is not None else None

    def status(self) -> dict[str, Any]:
        """Loop facts for the process status payload."""
        return {
            "mode": self.machine.mode.value,
            "missed_syncs": self.machine.missed_syncs,
            "policy_version": self._pack.policy_version if self._pack else None,
            "live_actions": len(self._live),
            "halted": self._halted,
            "slm": self._slm_status(),
        }

    def _slm_status(self) -> dict[str, Any] | None:
        """The SLM channel's state, plus whether it may decide right now.

        ``deciding`` is derived from the pack in force — a signed grant,
        not a local knob — and is only true when a verified model is
        actually loaded under that pack.
        """
        slm = self._deps.slm
        if slm is None:
            return None
        deciding = (
            slm.ready
            and self._pack is not None
            and self._pack.autonomy_envelope.allow_slm_decisions
        )
        return {**slm.status(), "deciding": deciding}
