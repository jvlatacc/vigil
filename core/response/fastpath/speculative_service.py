"""The speculative service: a fast-path decision becomes a ledger row, now.

One method does the work: validate the decision, take the row on the
existing ``approval_actions`` ledger (a ``speculative`` status row created
by the declared ``fast-path`` actor — the ORCHESTRATOR_ACTOR precedent),
and dispatch it through the enforcement adapter registry before returning.
Idempotency is the substrate's partial unique index on
``idempotency_key`` — while one speculative row for a key is live, a second
pass returns that row instead of dispatching again; once it is rolled back
or failed, a fresh row fires.

The row is committed before any adapter I/O. A dispatch that fails leaves a
``failed`` row that says so — never a live row claiming a restriction that
does not exist.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.response.approval_service import (
    ActionStatus,
    ApprovalService,
    PendingAction,
    Reversibility,
    _live_by_key,
    _row_to_pending,
)
from core.response.fastpath.adapters import (
    EnforcementAdapter,
    EnforcementRegistry,
    build_registry,
)
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import FastPathDecision, actionable_ip
from core.storage.connection import get_db_manager
from core.storage.models import ApprovalAction
from core.time import utcnow

logger = logging.getLogger(__name__)

# A declared non-agent actor, following the ORCHESTRATOR_ACTOR precedent: it
# has no prompt, no BUILTIN_AGENTS record, and never appears in GET /agents.
# Every row it creates carries the rendered deciding rule, so the record
# says what released the restriction.
FAST_PATH_ACTOR = "fast-path"


def speculative_key(action_type: str, target: str) -> str:
    """The row's idempotency key: one live restriction per type and target."""
    return f"spec:{action_type}:{target}"


@dataclass(frozen=True)
class SpeculativeOutcome:
    """What one fast-path pass did: a row, and whether this call inserted it.

    ``inserted=False`` is a dedupe: a live speculative row already answers
    for the idempotency key, and no second dispatch happened. Enforcement
    outcomes ride on the row's ``execution_result`` and
    ``parameters.rollback`` — the outcome does not shadow them.
    """

    action: PendingAction
    inserted: bool


def _clamped_ttl(seconds: int, config: FastPathConfig) -> int:
    """The decision's TTL bounded by the configuration ceiling.

    The ceiling is the invariant an adjudicator's ``retain`` may not exceed
    either; a decision that carries a larger TTL is clamped, not rejected —
    the ceiling, not the caller, is the promise.
    """
    if seconds > config.max_ttl_seconds:
        return config.max_ttl_seconds
    if seconds < 1:
        return config.default_ttl_seconds
    return seconds


def _row_confidence(decision: FastPathDecision) -> float:
    """The confidence on the row: the triage confidence when the tier has one.

    A pre-triage (T0) decision acts on source-native signals before any
    model call, so nothing model-scored exists to record — 0.0, not a made-up
    number. The deciding rule on the row says what fired either way.
    """
    value = decision.signals.get("confidence")
    if isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0:
        return float(value)
    return 0.0


def _evidence(decision: FastPathDecision) -> list:
    """The triggering finding, where the signals carry one."""
    finding_id = decision.signals.get("finding_id")
    return [f"finding:{finding_id}"] if finding_id else []


def _new_action_id() -> str:
    return f"action-{utcnow().strftime('%Y%m%d-%H%M%S-%f')}"


class SpeculativeActionService:
    """Turns fast-path decisions into speculative rows and immediate dispatch.

    Guard order is fixed: master switch, action-type allowlist, routable
    unicast target, then per-target cap, then idempotency. A None return is
    always a refusal, logged with its reason; the caller's next step is to
    move on, not to retry.
    """

    def __init__(
        self,
        config: Optional[FastPathConfig] = None,
        approvals: Optional[ApprovalService] = None,
        registry: Optional[EnforcementRegistry] = None,
    ):
        self.config = config or FastPathConfig()
        self.approvals = approvals or ApprovalService()
        self.registry = (
            registry if registry is not None else build_registry(self.config)
        )

    def create_speculative_action(
        self, decision: FastPathDecision
    ) -> Optional[SpeculativeOutcome]:
        """Validate, insert the speculative row, and dispatch it immediately.

        Returns None as a refusal: the master switch off, an action type
        outside the allowlist, a target that is not a routable unicast
        address, or the per-target cap already held. Returns the live row
        with ``inserted=False`` when the idempotency key is already answered.
        """
        if not self.config.enabled:
            return None
        if decision.action_type not in self.config.allowed_action_types:
            logger.warning(
                "fast path refused action type %s: not in the allowlist",
                decision.action_type,
            )
            return None
        target = actionable_ip(decision.target)
        if target is None or target != decision.target:
            logger.warning(
                "fast path refused target %r: not a routable unicast address",
                decision.target,
            )
            return None
        adapter = self.registry.adapter_for(decision.action_type)
        key = speculative_key(decision.action_type, target)
        ttl = _clamped_ttl(decision.ttl_seconds, self.config)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        try:
            db = get_db_manager()
            with db.session_scope() as session:
                existing = _live_by_key(session, key)
                if existing is not None:
                    return SpeculativeOutcome(
                        action=_row_to_pending(existing), inserted=False
                    )
                live_for_target = session.execute(
                    select(func.count())
                    .select_from(ApprovalAction)
                    .where(ApprovalAction.target == target)
                    .where(ApprovalAction.status == ActionStatus.SPECULATIVE.value)
                ).scalar_one()
                if live_for_target >= self.config.max_speculative_per_target:
                    logger.info(
                        "fast path refused %s on %s: %s live speculative rows "
                        "already hold the target cap",
                        decision.action_type,
                        target,
                        live_for_target,
                    )
                    return None
                row = ApprovalAction(
                    action_id=_new_action_id(),
                    action_type=decision.action_type,
                    title=f"Speculative {decision.action_type}: {target}",
                    description=(
                        "Speculative containment applied by the fast path (no model "
                        "call, no person in the loop). An adjudicate run, a human "
                        "decision, or the TTL sweep resolves it by "
                        f"{expires_at.isoformat()}."
                    ),
                    target=target,
                    confidence=_row_confidence(decision),
                    reason=decision.rule,
                    evidence=_evidence(decision),
                    created_by=FAST_PATH_ACTOR,
                    requires_approval=False,
                    status=ActionStatus.SPECULATIVE.value,
                    parameters=self._parameters(decision, adapter, ttl, expires_at),
                    reversibility=Reversibility.REVERSIBLE.value,
                    idempotency_key=key,
                    expires_at=expires_at,
                )
                session.add(row)
                session.flush()
                pending = _row_to_pending(row)
        except IntegrityError:
            # A concurrent processor inserted the same key between our read
            # and our insert: that row is the live one now. No live row on
            # the re-read means something else failed — surface it.
            db = get_db_manager()
            with db.session_scope() as session:
                existing = _live_by_key(session, key)
            if existing is None:
                raise
            return SpeculativeOutcome(action=_row_to_pending(existing), inserted=False)
        # The row is committed (session_scope exited with a commit) before
        # any adapter I/O: the ledger records the attempt even when dispatch
        # fails, and a dispatch can never race its own row into existence.
        self._dispatch(pending, adapter)
        refreshed = self.approvals.get_action(pending.action_id)
        return SpeculativeOutcome(action=refreshed or pending, inserted=True)

    def _parameters(
        self,
        decision: FastPathDecision,
        adapter: EnforcementAdapter,
        ttl: int,
        expires_at: datetime,
    ) -> dict:
        """The row's parameters: TTL, rollback recipe, signals, deciding rule.

        The rollback recipe is written at creation — the release verb needs
        the adapter's name and the action type before any enforcement exists
        to reference — and the external reference is attached to it after
        dispatch. ``simulation`` marks rows whose enforcement records intent
        only; surfaces label them.
        """
        return {
            "speculative": True,
            "simulation": adapter.simulates,
            "ttl_seconds": ttl,
            "expires_at": expires_at.isoformat(),
            "rule": decision.rule,
            "signals": dict(decision.signals),
            "rollback": {
                "adapter": adapter.name,
                "action_type": decision.action_type,
                "target": decision.target,
                "external_ref": None,
            },
        }

    def _dispatch(self, action: PendingAction, adapter: EnforcementAdapter) -> None:
        """Apply through the adapter and record the outcome on the row.

        A refusal or vendor rejection marks the row failed: an unenforced
        live row would record a containment that never happened. Failure
        frees the idempotency key, so the next finding re-fires fresh.
        """
        try:
            result = adapter.apply(action)
        except Exception:
            # Exception text never lands on the row (execution_result is
            # API-visible); the full traceback is in the server log.
            logger.exception("speculative dispatch failed for %s", action.action_id)
            self.approvals.mark_failed(action.action_id, "adapter apply failed")
            return
        if not result.applied:
            logger.warning(
                "speculative dispatch refused for %s: %s",
                action.action_id,
                result.detail,
            )
            self.approvals.mark_failed(action.action_id, result.detail)
            return
        self._record_dispatch(action.action_id, adapter, result)

    def _record_dispatch(
        self, action_id: str, adapter: EnforcementAdapter, result
    ) -> None:
        """Record an applied dispatch: ``execution_result`` and the recipe ref."""
        db = get_db_manager()
        with db.session_scope() as session:
            row = session.get(ApprovalAction, action_id)
            if row is None:
                logger.error(
                    "speculative row %s vanished before dispatch recording", action_id
                )
                return
            row.execution_result = {
                "applied": result.applied,
                "external_ref": result.external_ref,
                "detail": result.detail,
                "simulated": adapter.simulates,
                "adapter": adapter.name,
            }
            parameters = dict(row.parameters or {})
            rollback = dict(parameters.get("rollback") or {})
            rollback["external_ref"] = result.external_ref
            parameters["rollback"] = rollback
            row.parameters = parameters
