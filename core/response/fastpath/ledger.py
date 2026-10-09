"""The containment-lease state machine (speculative containment, PR-3).

The ledger owns ROW STATE; executors own EFFECTS. Every transition is a
compare-and-swap on the row's current status, so the two competitors for a
live lease — slow-path adjudication and the TTL sweeper — can both fire
without double-rolling-back: the loser's CAS refuses and its undo, being
idempotent, was harmless.

Ordering invariant (undo-then-mark): an effect is removed before its row
closes. A crash between the two leaves an ``applied`` row the sweeper
reconciles — never an effect without a row.

Transaction shape (write-behind): :meth:`ContainmentLedger.issue` is the
ONE synchronous insert on the millisecond path — a committed
``pending_apply`` intent — and the executor call happens strictly outside
any transaction, so the network round trip never holds a database session.

Transitions record their actor and the evidence version they decided on as
structured log lines. A durable per-transition audit table
(``containment_transitions``) is a noted follow-up: the schema is PR-1's
and is consumed as-is; ``rollback_reason`` and
``escalated_approval_action_id`` carry the reasons the row itself can hold.

Redis is deliberately absent: the partial unique index on
``containment_actions.idempotency_key`` is the dedup source of truth, so a
missing or degraded Redis (optional across Vigil) cannot cost a lease.

Shadow rows (``is_shadow=True``) are scored-and-recorded, never applied:
the drivers below never call an executor for one, and the reconciliation
sweep never retried-applies one. Closing expired shadow rows — freeing
their idempotency key for a live lease — is the adjudication slice's job
(PR-4), which owns the replay verdicts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import (
    Any,
    ContextManager,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from core.storage.connection import get_db_manager
from core.storage.models import ContainmentAction
from core.time import utcnow

logger = logging.getLogger(__name__)

# The lease lifecycle. Plain strings — the model stores a String(16) and the
# partial unique index predicates on exactly these two active states.
PENDING_APPLY = "pending_apply"
APPLIED = "applied"
ROLLED_BACK = "rolled_back"
ESCALATED = "escalated"
FAILED = "failed"

ACTIVE_STATUSES = (PENDING_APPLY, APPLIED)

# Rollback reasons. ``ttl_expired`` is the sweeper's; the others belong to
# slow-path adjudication (PR-4) and operator action.
TTL_EXPIRED = "ttl_expired"
DOWNGRADED = "downgraded"
FALSE_POSITIVE = "false_positive"
OPERATOR = "operator"

# Failed-reason vocabulary (String(30), terse by column width; detail rides
# the transition log).
REASON_APPLY_FAILED = "apply_failed"
REASON_APPLY_RETRY_FAILED = "apply_retry_failed"
REASON_TTL_EXPIRED_BEFORE_APPLY = "ttl_expired_before_apply"
REASON_NO_EXECUTOR = "no_executor_registered"

ACTOR_GATE = "fastpath-gate"
ACTOR_SWEEPER = "ttl-sweeper"
ACTOR_ADJUDICATOR = "slow-path-adjudicator"


class LeaseError(RuntimeError):
    """A lease transition the ledger refuses (unknown lease, stale CAS)."""


@runtime_checkable
class SessionScopeFactory(Protocol):
    """The one thing the ledger needs from the DB manager.

    ``get_db_manager().session_scope()`` — commit on success, rollback on
    exception. Narrowed so tests can hand in a scratch manager and the
    no_db seam can patch :func:`get_db_manager` in this module.
    """

    def session_scope(self) -> ContextManager[Any]: ...


@dataclass(frozen=True)
class LeaseIntent:
    """What the policy gate asks the ledger to record, before any effect.

    ``observed`` is the telemetry mirror frozen at fire time (severity,
    confidence, detector, decision inputs) — adjudication reads what the
    gate saw, not the finding triage later rewrote.
    """

    action_type: str
    entity_type: str
    entity_id: str
    ttl_seconds: int
    decision_rule: str
    observed: Dict[str, Any] = field(default_factory=dict)
    finding_id: Optional[str] = None
    is_shadow: bool = False

    @property
    def idempotency_key(self) -> str:
        """``{action_type}:{entity_type}:{entity_id}`` — one ACTIVE lease
        per principal per action; replays collapse into the live row."""
        return f"{self.action_type}:{self.entity_type}:{self.entity_id}"


@dataclass(frozen=True)
class LeaseView:
    """A lease row read out of the ledger, detached from any session."""

    id: str
    action_type: str
    entity_type: str
    entity_id: str
    status: str
    idempotency_key: str
    finding_id: Optional[str]
    decision_rule: str
    observed: Dict[str, Any]
    undo_payload: Optional[Dict[str, Any]]
    is_shadow: bool
    ttl_seconds: Optional[int]
    expires_at: Optional[datetime]
    created_at: datetime

    @classmethod
    def from_row(cls, row: ContainmentAction) -> "LeaseView":
        return cls(
            id=row.id,
            action_type=row.action_type,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            status=row.status,
            idempotency_key=row.idempotency_key,
            finding_id=row.finding_id,
            decision_rule=row.decision_rule,
            observed=dict(row.observed or {}),
            undo_payload=dict(row.undo_payload) if row.undo_payload else None,
            is_shadow=bool(row.is_shadow),
            ttl_seconds=row.ttl_seconds,
            expires_at=row.expires_at,
            created_at=row.created_at,
        )


@dataclass(frozen=True)
class Transition:
    """The record of one CAS transition: who moved what, on what evidence."""

    lease_id: str
    from_status: str
    to_status: str
    actor: str
    evidence_version: Optional[str]
    reason: Optional[str] = None


def lease_spec_of(lease: LeaseView) -> "Any":
    """Build the executor-facing spec for a lease row.

    Kept lazy (returns a lightweight namespace) so the ledger module does
    not import the executors module — the dependency runs the other way.
    Executors receive it as ``lease``; every field they need is here.
    """
    from core.response.fastpath.executors import LeaseSpec

    return LeaseSpec(
        lease_id=lease.id,
        action_type=lease.action_type,
        entity_type=lease.entity_type,
        entity_id=lease.entity_id,
        ttl_seconds=lease.ttl_seconds,
        expires_at=lease.expires_at,
        observed=dict(lease.observed),
    )


class ContainmentLedger:
    """CAS transitions over ``containment_actions``.

    Every mutator commits or refuses atomically; none ever runs an
    executor — effects are the drivers' business (below), which is what
    keeps the synchronous intent insert and the executor call in separate
    transactions.
    """

    def __init__(self, db_manager: Optional[SessionScopeFactory] = None):
        self._db_manager = db_manager

    def _manager(self) -> SessionScopeFactory:
        if self._db_manager is not None:
            return self._db_manager
        return get_db_manager()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, lease_id: str) -> Optional[LeaseView]:
        with self._manager().session_scope() as session:
            row = session.get(ContainmentAction, lease_id)
            return LeaseView.from_row(row) if row is not None else None

    def find_active_by_key(self, idempotency_key: str) -> Optional[LeaseView]:
        with self._manager().session_scope() as session:
            row = session.execute(
                select(ContainmentAction)
                .where(
                    ContainmentAction.idempotency_key == idempotency_key,
                    ContainmentAction.status.in_(ACTIVE_STATUSES),
                )
                .order_by(ContainmentAction.created_at)
                .limit(1)
            ).scalar_one_or_none()
            return LeaseView.from_row(row) if row is not None else None

    def list_expired(
        self, now: Optional[datetime] = None, batch_size: int = 100
    ) -> List[LeaseView]:
        """Live (``applied``) leases past ``expires_at`` — the sweeper's scan.

        Ordered by expiry so the oldest debt goes first, bounded by
        ``batch_size`` so one bloated backlog cannot make a sweep unbounded.
        """
        now = now or utcnow()
        with self._manager().session_scope() as session:
            rows = (
                session.execute(
                    select(ContainmentAction)
                    .where(
                        ContainmentAction.status == APPLIED,
                        ContainmentAction.expires_at.is_not(None),
                        ContainmentAction.expires_at <= now,
                    )
                    .order_by(ContainmentAction.expires_at)
                    .limit(batch_size)
                )
                .scalars()
                .all()
            )
            return [LeaseView.from_row(row) for row in rows]

    def list_stale_intents(
        self,
        apply_timeout_seconds: int,
        now: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> List[LeaseView]:
        """``pending_apply`` intents older than the apply timeout.

        Shadow rows are excluded: nothing was applied for them and nothing
        ever will be — retrying an apply for a shadow row would defeat the
        whole point of shadow mode.
        """
        now = now or utcnow()
        cutoff = now - timedelta(seconds=apply_timeout_seconds)
        with self._manager().session_scope() as session:
            rows = (
                session.execute(
                    select(ContainmentAction)
                    .where(
                        ContainmentAction.status == PENDING_APPLY,
                        ContainmentAction.is_shadow.is_(False),
                        ContainmentAction.created_at <= cutoff,
                    )
                    .order_by(ContainmentAction.created_at)
                    .limit(batch_size)
                )
                .scalars()
                .all()
            )
            return [LeaseView.from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Writes — every one a compare-and-swap on current status
    # ------------------------------------------------------------------

    def issue(
        self,
        intent: LeaseIntent,
        lease_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[LeaseView, bool]:
        """Record the intent: ONE synchronous ``pending_apply`` insert.

        The bool is True when this call inserted. A replay (same
        idempotency key, lease still active) returns the live row and
        inserts nothing — webhook replays and duplicate triggers collapse
        into one lease. The insert commits BEFORE any executor runs;
        a crash after this point leaves an intent the reconciler owns,
        never an effect without a row.
        """
        now = now or utcnow()
        expires_at = (
            now + timedelta(seconds=intent.ttl_seconds)
            if intent.ttl_seconds is not None
            else None
        )
        try:
            with self._manager().session_scope() as session:
                existing = session.execute(
                    select(ContainmentAction)
                    .where(
                        ContainmentAction.idempotency_key == intent.idempotency_key,
                        ContainmentAction.status.in_(ACTIVE_STATUSES),
                    )
                    .order_by(ContainmentAction.created_at)
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    return LeaseView.from_row(existing), False
                row = ContainmentAction(
                    id=lease_id,
                    action_type=intent.action_type,
                    entity_type=intent.entity_type,
                    entity_id=intent.entity_id,
                    status=PENDING_APPLY,
                    idempotency_key=intent.idempotency_key,
                    finding_id=intent.finding_id,
                    decision_rule=intent.decision_rule,
                    observed=dict(intent.observed),
                    is_shadow=intent.is_shadow,
                    ttl_seconds=intent.ttl_seconds,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                view = LeaseView.from_row(row)
            return view, True
        except IntegrityError:
            # Lost a race with a concurrent issue(): the partial index
            # admitted theirs. Read the winner in a fresh scope.
            existing = self.find_active_by_key(intent.idempotency_key)
            if existing is not None:
                return existing, False
            raise

    def mark_applied(
        self,
        lease_id: str,
        undo_payload: Optional[Dict[str, Any]],
        actor: str = ACTOR_GATE,
        evidence_version: Optional[str] = None,
        applied_at: Optional[datetime] = None,
    ) -> Optional[Transition]:
        """``pending_apply -> applied``, storing the executor's undo token.

        Returns None when the CAS refuses — a stale status means another
        actor (reconciler, adjudicator) already moved the row; the caller
        must treat its effect as suspect and undo it.
        """
        return self._cas(
            lease_id,
            expected=PENDING_APPLY,
            to_status=APPLIED,
            actor=actor,
            evidence_version=evidence_version,
            extra_values={
                "undo_payload": dict(undo_payload or {}),
                "applied_at": applied_at or utcnow(),
            },
        )

    def mark_rolled_back(
        self,
        lease_id: str,
        reason: str,
        actor: str = ACTOR_ADJUDICATOR,
        evidence_version: Optional[str] = None,
    ) -> Optional[Transition]:
        """``applied -> rolled_back``. Call ONLY after the undo completed —
        the effect is removed first, then the row closes."""
        return self._cas(
            lease_id,
            expected=APPLIED,
            to_status=ROLLED_BACK,
            actor=actor,
            evidence_version=evidence_version,
            reason=reason,
            extra_values={
                "rolled_back_at": utcnow(),
                "rollback_reason": reason,
            },
        )

    def mark_escalated(
        self,
        lease_id: str,
        approval_action_id: str,
        actor: str = ACTOR_ADJUDICATOR,
        evidence_version: Optional[str] = None,
    ) -> Optional[Transition]:
        """``applied -> escalated``, pointing at the approval row.

        Terminal for the lease: the stronger containment lives in
        ``approval_actions`` under its own human gate, and this column only
        points back at it. The approval pipeline never writes here.
        """
        return self._cas(
            lease_id,
            expected=APPLIED,
            to_status=ESCALATED,
            actor=actor,
            evidence_version=evidence_version,
            extra_values={"escalated_approval_action_id": approval_action_id},
        )

    def mark_failed(
        self,
        lease_id: str,
        reason: str,
        actor: str = ACTOR_SWEEPER,
        evidence_version: Optional[str] = None,
    ) -> Optional[Transition]:
        """Either active state -> ``failed``.

        Callers that cannot prove no effect landed (a timed-out or raised
        apply) must attempt the idempotent undo FIRST — see the drivers
        below, which own that ordering.
        """
        with self._manager().session_scope() as session:
            result = session.execute(
                update(ContainmentAction)
                .where(
                    ContainmentAction.id == lease_id,
                    ContainmentAction.status.in_(ACTIVE_STATUSES),
                )
                .values(
                    status=FAILED,
                    rollback_reason=reason,
                    updated_at=utcnow(),
                )
            )
            if result.rowcount == 0:
                return self._refused(lease_id, "failed", actor)
            transition = Transition(
                lease_id=lease_id,
                from_status="active",
                to_status=FAILED,
                actor=actor,
                evidence_version=evidence_version,
                reason=reason,
            )
            self._log_transition(transition)
            return transition

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cas(
        self,
        lease_id: str,
        expected: str,
        to_status: str,
        actor: str,
        evidence_version: Optional[str],
        reason: Optional[str] = None,
        extra_values: Optional[Dict[str, Any]] = None,
    ) -> Optional[Transition]:
        values: Dict[str, Any] = {"status": to_status, "updated_at": utcnow()}
        if reason is not None:
            values["rollback_reason"] = reason
        if extra_values:
            values.update(extra_values)
        with self._manager().session_scope() as session:
            result = session.execute(
                update(ContainmentAction)
                .where(
                    ContainmentAction.id == lease_id,
                    ContainmentAction.status == expected,
                )
                .values(**values)
            )
            if result.rowcount == 0:
                return self._refused(lease_id, to_status, actor)
            transition = Transition(
                lease_id=lease_id,
                from_status=expected,
                to_status=to_status,
                actor=actor,
                evidence_version=evidence_version,
                reason=reason,
            )
            self._log_transition(transition)
            return transition

    @staticmethod
    def _refused(lease_id: str, to_status: str, actor: str) -> None:
        logger.info(
            "containment_lease_transition_refused lease=%s to=%s actor=%s — "
            "the row moved under us; the CAS refuses the loser",
            lease_id,
            to_status,
            actor,
        )
        return None

    @staticmethod
    def _log_transition(transition: Transition) -> None:
        # Structured transition record: actor + evidence version, per the
        # lease state machine. The durable audit table is the noted
        # follow-up (module docstring) — the schema is consumed as-is.
        logger.info(
            "containment_lease_transition lease=%s from=%s to=%s actor=%s "
            "evidence_version=%s reason=%s",
            transition.lease_id,
            transition.from_status,
            transition.to_status,
            transition.actor,
            transition.evidence_version,
            transition.reason,
        )


# ----------------------------------------------------------------------
# Async drivers — the only places executors meet the ledger
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyOutcome:
    lease: LeaseView
    applied: bool
    replay: bool = False
    shadow: bool = False
    error: Optional[str] = None


async def issue_and_apply(
    ledger: ContainmentLedger,
    intent: LeaseIntent,
    executor: Any,
    actor: str = ACTOR_GATE,
    evidence_version: Optional[str] = None,
) -> ApplyOutcome:
    """Issue the intent, then apply the effect OUTSIDE any transaction.

    Write-behind shape: one synchronous intent insert (committed), then
    the executor call with no session open, then the CAS to ``applied``
    with the undo payload. A replay returns the live row without calling
    the executor; a shadow row records without ever applying.
    """
    lease, inserted = await asyncio.to_thread(ledger.issue, intent)
    if not inserted:
        return ApplyOutcome(lease=lease, applied=False, replay=True)
    if lease.is_shadow:
        return ApplyOutcome(lease=lease, applied=False, shadow=True)
    try:
        undo_payload = await executor.apply(lease_spec_of(lease))
    except Exception as exc:  # noqa: BLE001 — any failure becomes a lease state
        # Uncertain outcome: the apply may have landed. Undo is idempotent
        # and token-reconstructable, so attempting it is always safe — and
        # it runs BEFORE the row closes (undo-then-mark, even on failure).
        try:
            await executor.undo(lease.id, {})
        except Exception:  # noqa: BLE001
            logger.exception(
                "containment lease %s: uncertainty undo after apply failure "
                "also failed; the sweeper will retry the idempotent undo",
                lease.id,
            )
        await asyncio.to_thread(
            ledger.mark_failed,
            lease.id,
            REASON_APPLY_FAILED,
            actor,
            evidence_version,
        )
        return ApplyOutcome(lease=lease, applied=False, error=str(exc))
    transition = await asyncio.to_thread(
        ledger.mark_applied,
        lease.id,
        undo_payload,
        actor,
        evidence_version,
    )
    if transition is None:
        # The row moved while the apply was in flight (the reconciler
        # aborted it, or adjudication closed it). The effect must not
        # outlive the row: undo it now, idempotently.
        logger.warning(
            "containment lease %s: apply landed after the row moved; "
            "compensating undo",
            lease.id,
        )
        try:
            await executor.undo(lease.id, undo_payload)
        except Exception:  # noqa: BLE001
            logger.exception(
                "containment lease %s: compensating undo failed; the "
                "sweeper will retry the idempotent undo",
                lease.id,
            )
        return ApplyOutcome(lease=lease, applied=False)
    return ApplyOutcome(lease=lease, applied=True)


async def rollback_lease(
    ledger: ContainmentLedger,
    executor: Any,
    lease_id: str,
    reason: str,
    actor: str = ACTOR_ADJUDICATOR,
    evidence_version: Optional[str] = None,
) -> Optional[Transition]:
    """Undo the effect, then close the row: undo-then-mark, in order.

    Returns None when there was nothing live to roll back (unknown lease,
    not ``applied``) or when the CAS lost a race — adjudication and the
    sweeper may both fire, the loser is refused, and both undos are
    idempotent so the double-fire is harmless by construction.
    """
    lease = await asyncio.to_thread(ledger.get, lease_id)
    if lease is None or lease.status != APPLIED:
        logger.info(
            "containment rollback skipped lease=%s status=%s — nothing live",
            lease_id,
            lease.status if lease else "unknown",
        )
        return None
    await executor.undo(lease_id, lease.undo_payload or {})
    return await asyncio.to_thread(
        ledger.mark_rolled_back,
        lease_id,
        reason,
        actor,
        evidence_version,
    )


async def sweep_expired(
    ledger: ContainmentLedger,
    registry: Any,
    now: Optional[datetime] = None,
    batch_size: int = 100,
    actor: str = ACTOR_SWEEPER,
) -> Dict[str, int]:
    """Roll back every ``applied`` lease past ``expires_at``.

    Datastore-enforced expiry: the scan reads rows, not memory, so a
    crashed or restarted daemon never leaves a lease alive. A lease whose
    action type has no registered executor is left for its owner — a
    missing executor must never be mistaken for a rollback.
    """
    now = now or utcnow()
    expired = await asyncio.to_thread(ledger.list_expired, now, batch_size)
    summary = {
        "expired": len(expired),
        "rolled_back": 0,
        "skipped_no_executor": 0,
        "errors": 0,
    }
    for lease in expired:
        executor = registry.get(lease.action_type)
        if executor is None:
            summary["skipped_no_executor"] += 1
            continue
        try:
            await executor.undo(lease.id, lease.undo_payload or {})
            transition = await asyncio.to_thread(
                ledger.mark_rolled_back,
                lease.id,
                TTL_EXPIRED,
                actor,
                None,
            )
            if transition is not None:
                summary["rolled_back"] += 1
        except Exception:  # noqa: BLE001 — one bad lease must not stop the sweep
            summary["errors"] += 1
            logger.exception("containment sweep: undo failed for lease %s", lease.id)
    return summary


async def reconcile_stale_intents(
    ledger: ContainmentLedger,
    registry: Any,
    apply_timeout_seconds: int,
    now: Optional[datetime] = None,
    batch_size: int = 100,
    actor: str = ACTOR_SWEEPER,
) -> Dict[str, int]:
    """Reconcile ``pending_apply`` intents stuck past the apply timeout.

    A stuck intent means a crash or a lost reply between the intent insert
    and the CAS to ``applied``. The executor call is idempotent — a retry
    with the same lease id either finds its object or creates it — so the
    reconciler retries the apply exactly once and otherwise aborts to
    ``failed``. An intent already past its own ``expires_at`` is never
    applied: the idempotent undo cleans up any orphan first.
    """
    now = now or utcnow()
    stale = await asyncio.to_thread(
        ledger.list_stale_intents, apply_timeout_seconds, now, batch_size
    )
    summary = {
        "stale": len(stale),
        "retried_applied": 0,
        "aborted_failed": 0,
        "errors": 0,
    }
    for lease in stale:
        executor = registry.get(lease.action_type)
        if lease.expires_at is not None and lease.expires_at <= now:
            # Never apply something already past its own expiry.
            if executor is not None:
                try:
                    await executor.undo(lease.id, lease.undo_payload or {})
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "containment reconcile: orphan undo failed for %s",
                        lease.id,
                    )
            await asyncio.to_thread(
                ledger.mark_failed,
                lease.id,
                REASON_TTL_EXPIRED_BEFORE_APPLY,
                actor,
                None,
            )
            summary["aborted_failed"] += 1
            continue
        if executor is None:
            # No executor: no apply ever ran for this type, so nothing to
            # undo — but the intent must not sit stale forever, re-scanned
            # on every tick.
            await asyncio.to_thread(
                ledger.mark_failed, lease.id, REASON_NO_EXECUTOR, actor, None
            )
            summary["aborted_failed"] += 1
            continue
        try:
            undo_payload = await executor.apply(lease_spec_of(lease))
        except Exception as exc:  # noqa: BLE001
            try:
                await executor.undo(lease.id, {})
            except Exception:  # noqa: BLE001
                logger.exception(
                    "containment reconcile: uncertainty undo failed for %s",
                    lease.id,
                )
            await asyncio.to_thread(
                ledger.mark_failed,
                lease.id,
                REASON_APPLY_RETRY_FAILED,
                actor,
                None,
            )
            logger.warning(
                "containment reconcile: apply retry failed for lease %s: %s",
                lease.id,
                exc,
            )
            summary["aborted_failed"] += 1
            continue
        transition = await asyncio.to_thread(
            ledger.mark_applied, lease.id, undo_payload, actor, None
        )
        if transition is None:
            try:
                await executor.undo(lease.id, undo_payload)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "containment reconcile: compensating undo failed for %s",
                    lease.id,
                )
            continue
        summary["retried_applied"] += 1
    return summary
