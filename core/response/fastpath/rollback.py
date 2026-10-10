"""The rollback verbs: release, escalate, retain, expire.

Four ways a speculative row's live state changes, three of them terminal.
``release`` drives the enforcement adapter's release verb and marks the row
``rolled_back`` — the widened idempotency index (seed 40) then frees the
key, so the target can be restricted again. ``escalate`` creates the full
containment action through the unmodified approval pipeline — a person
still decides, whatever confidence says — and links it from the
speculative row, which becomes ``escalated``. ``retain`` extends the row's
expiry once, bounded by the ceiling — the row stays speculative, and no
second retain is possible. ``expire`` is the fail-safe: a sweep that
releases every speculative row past ``expires_at`` regardless of what
adjudication is doing.

Two invariants shape the order of operations. The adapter I/O happens
before any status write: a row only says ``rolled_back`` once the
restriction is actually lifted, never before. And every status write is a
guarded claim — a ``SELECT ... FOR UPDATE`` that re-checks ``status =
'speculative'`` — so a sweep, a manual release and an escalation can race
without double-resolving a row or resurrecting a resolved one. Adapter
``release`` is idempotent by contract, so a racer that loses the claim has
still done no harm at the vendor.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select

from core.response.approval_service import (
    ActionStatus,
    ActionType,
    ApprovalService,
    PendingAction,
    _row_to_pending,
)
from core.response.config import decision_rule
from core.response.fastpath.adapters import (
    EnforcementAdapter,
    EnforcementRegistry,
    EnforceResult,
    build_registry,
)
from core.response.fastpath.config import FastPathConfig
from core.storage.connection import get_db_manager
from core.storage.models import ApprovalAction

logger = logging.getLogger(__name__)

# Why a restriction stopped being live — the lifecycle table's vocabulary.
# Recorded on the row (reason annotation and ``execution_result.reason``) so
# the record says who released it and why.
RELEASE_REASON_ADJUDICATED = "adjudicated_release"
RELEASE_REASON_TTL_EXPIRED = "ttl_expired"
RELEASE_REASON_HUMAN = "human_release"
RELEASE_REASONS = frozenset(
    {RELEASE_REASON_ADJUDICATED, RELEASE_REASON_TTL_EXPIRED, RELEASE_REASON_HUMAN}
)

# Who resolved the row. An escalation's source picks what happens to the
# created full action: an adjudicator's confidence is its own claim, so its
# escalation stays pending for a person; a person's escalation is approved
# by that person on the spot.
SOURCE_ADJUDICATOR = "adjudicator"
SOURCE_HUMAN = "human"
ESCALATION_SOURCES = frozenset({SOURCE_ADJUDICATOR, SOURCE_HUMAN})

# The sweep's declared actor — distinct from the fast path (which creates
# rows) and from ``system`` (which the stale-approval expiry uses): the
# reason on the row distinguishes the fail-safe from every other resolver.
TTL_SWEEP_ACTOR = "ttl-sweep"

# The #917 field names — one string shape, everywhere, for later parsing.
RELEASE_REASON_FIELD = "fast_path.release_reason"
ESCALATION_LINK_FIELD = "fast_path.escalation"
RETENTION_RULE_FIELD = "fast_path.retention"

# The once-per-action retention marker, inside ``parameters["adjudication"]``.
# The retain claim reads it under the row lock, so a second retain — a racing
# adjudicator or a replayed scan — reads its own write and refuses.
RETENTION_FIELD = "retention"

# Rows released per sweep tick. The rest wait for the next one — the sweep
# runs every minute, and a bounded batch keeps a pile-up of expiries from
# holding the daemon's event loop hostage on adapter I/O.
SWEEP_BATCH = 100

# Escalation must name a full containment action, never another speculative
# micro-action — escalating to a micro-action is a loop, not an escalation.
# The four are pinned from the ActionType enum, not the config allowlist: an
# operator-narrowed allowlist must not widen what escalation accepts.
_SPECULATIVE_ACTION_TYPES = frozenset(
    {
        ActionType.RATE_LIMIT.value,
        ActionType.TARPIT.value,
        ActionType.SESSION_PIN.value,
        ActionType.LATENCY_INJECT.value,
    }
)


@dataclass(frozen=True)
class ReleaseOutcome:
    """What one release attempt did.

    ``released=False`` is always a refusal or a lost race, said in
    ``detail``; the row is left exactly as it was found, so a TTL sweep
    retries it next minute.
    """

    action_id: str
    released: bool
    detail: str


@dataclass(frozen=True)
class EscalationRequest:
    """The full containment action an escalation asks for.

    ``confidence`` is provenance — what the requesting side claimed — and
    is recorded on the full action, but never releases it: the escalation
    always creates the action requiring approval (locked decision 5).
    """

    action_type: str
    target: str
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class EscalationOutcome:
    """What one escalation did: the linked full action, if one was created.

    ``escalated=False`` with a ``full_action`` means the full action was
    created but the speculative row was resolved by another actor before it
    could be marked — the fail-safe direction (a lifted restriction, a
    pending full action), said plainly in ``detail``.
    """

    action_id: str
    escalated: bool
    full_action: Optional[PendingAction]
    detail: str


@dataclass(frozen=True)
class RetainOutcome:
    """What one retain attempt did.

    ``extended=False`` is a refusal (not speculative, or already retained
    once) or a lost race, said in ``detail``; the row is left exactly as
    it was found, and the TTL sweep keeps its appointment either way.
    """

    action_id: str
    extended: bool
    detail: str
    expires_at: Optional[datetime] = None
    extension_seconds: Optional[int] = None


@dataclass(frozen=True)
class SweepOutcome:
    """One sweep tick: rows found past expiry, and how many released."""

    examined: int
    released: int


class RollbackService:
    """Release, escalate, and expire speculative actions.

    Shares the enforcement registry with the speculative service — the same
    adapter that applied a restriction releases it — and the same approval
    service for the escalation's route through the unmodified pipeline.
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

    # ------------------------------------------------------------------
    # release
    # ------------------------------------------------------------------

    def release(self, action_id: str, reason: str, actor: str) -> ReleaseOutcome:
        """Lift a live speculative restriction and mark the row rolled back.

        ``reason`` is one of the lifecycle's release reasons and ``actor``
        names the resolver (an adjudicate run, a person, the sweep). A row
        that is not speculative is refused without touching the adapter —
        a resolved row must not be released a second time.
        """
        if reason not in RELEASE_REASONS:
            raise ValueError(
                f"unknown release reason {reason!r}; "
                f"expected one of {sorted(RELEASE_REASONS)}"
            )
        row = self._load(action_id)
        if row is None:
            return ReleaseOutcome(action_id, False, "unknown action")
        if row.status != ActionStatus.SPECULATIVE.value:
            return ReleaseOutcome(
                action_id,
                False,
                f"action is {row.status}, not speculative; refusing to release",
            )
        adapter, result = self._release_via_adapter(row)
        if not result.applied:
            logger.warning(
                "release refused for %s: %s",
                action_id,
                result.detail,
            )
            return ReleaseOutcome(action_id, False, result.detail)
        claimed = self._resolve(
            action_id,
            status_to=ActionStatus.ROLLED_BACK,
            annotation=decision_rule(RELEASE_REASON_FIELD, reason),
            record=lambda r: self._release_record(r, reason, actor, adapter, result),
        )
        if not claimed:
            return ReleaseOutcome(
                action_id,
                False,
                "already resolved by another actor while releasing",
            )
        return ReleaseOutcome(action_id, True, result.detail)

    def _load(self, action_id: str) -> Optional[PendingAction]:
        db = get_db_manager()
        with db.session_scope() as session:
            row = session.get(ApprovalAction, action_id)
            return _row_to_pending(row) if row else None

    def _release_via_adapter(
        self, row: PendingAction
    ) -> tuple[EnforcementAdapter, EnforceResult]:
        """The adapter's release verb, outside any transaction."""
        adapter = self.registry.adapter_for(row.action_type)
        result = adapter.release(row)
        return adapter, result

    def _release_record(
        self,
        row: ApprovalAction,
        reason: str,
        actor: str,
        adapter: EnforcementAdapter,
        result: EnforceResult,
    ) -> None:
        now = datetime.now(timezone.utc)
        row.execution_result = {
            "released": True,
            "reason": reason,
            "actor": actor,
            "adapter": adapter.name,
            "external_ref": result.external_ref,
            "detail": result.detail,
            "at": now.isoformat(),
        }

    def _resolve(
        self,
        action_id: str,
        *,
        status_to: ActionStatus,
        annotation: str,
        record: Callable[[ApprovalAction], None],
    ) -> bool:
        """Claim a speculative row and move it to ``status_to``.

        The ``SELECT ... FOR UPDATE`` re-checks ``status = 'speculative'``,
        so exactly one racer claims the row: the loser reads nothing and
        reports the loss. The ``record`` callback writes the outcome fields
        onto the row inside the claim's transaction.
        """
        db = get_db_manager()
        with db.session_scope() as session:
            row = session.execute(
                select(ApprovalAction)
                .where(ApprovalAction.action_id == action_id)
                .where(ApprovalAction.status == ActionStatus.SPECULATIVE.value)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return False
            row.status = status_to.value
            base_reason = row.reason or ""
            row.reason = f"{base_reason}; {annotation}" if base_reason else annotation
            record(row)
        return True

    # ------------------------------------------------------------------
    # escalate
    # ------------------------------------------------------------------

    def escalate(
        self,
        action_id: str,
        request: EscalationRequest,
        *,
        decided_by: str,
        source: str,
    ) -> EscalationOutcome:
        """Escalate a live speculative action to full containment.

        The full action is created through the approval pipeline unmodified
        and always requires a person — an adjudicator's confidence is its
        own claim, so its escalation stays pending; a person's escalation
        is approved on the spot by that person. The speculative row becomes
        ``escalated`` and links the full action. The restriction itself
        stays in force until the full action is decided or the enforcement
        point's own expiry lifts it (the Cloudflare rule's
        ``mitigation_timeout`` is set from the TTL at apply time).
        """
        if source not in ESCALATION_SOURCES:
            raise ValueError(
                f"unknown escalation source {source!r}; "
                f"expected one of {sorted(ESCALATION_SOURCES)}"
            )
        try:
            full_type = ActionType(request.action_type)
        except ValueError:
            return EscalationOutcome(
                action_id,
                False,
                None,
                f"unknown action type {request.action_type!r}",
            )
        if full_type.value in _SPECULATIVE_ACTION_TYPES:
            return EscalationOutcome(
                action_id,
                False,
                None,
                (
                    f"{full_type.value} is a speculative micro-action; "
                    "escalation must name a full containment type"
                ),
            )
        row = self._load(action_id)
        if row is None:
            return EscalationOutcome(action_id, False, None, "unknown action")
        if row.status != ActionStatus.SPECULATIVE.value:
            return EscalationOutcome(
                action_id,
                False,
                None,
                f"action is {row.status}, not speculative; refusing to escalate",
            )
        full = self.approvals.create_action(
            action_type=full_type,
            title=f"{full_type.value}: {request.target}",
            description=(
                "Full containment requested by the "
                f"{source} escalation of speculative action {action_id}. The "
                "speculative restriction stays in force until this action is "
                "decided or the enforcement point's own expiry lifts it."
            ),
            target=request.target,
            confidence=request.confidence,
            reason=request.reasoning,
            evidence=[f"speculative:{action_id}"],
            created_by=decided_by,
            human_only=True,
        )
        if source == SOURCE_HUMAN:
            # The person's decision is the release; record it on the full
            # action. A pending row approves; an auto-approved one (nothing
            # to do) is returned as is.
            approved = self.approvals.approve_action(
                full.action_id, approved_by=decided_by
            )
            full = approved or full
        now = datetime.now(timezone.utc)

        def link(row: ApprovalAction) -> None:
            parameters = dict(row.parameters or {})
            parameters["escalation"] = {
                "action_id": full.action_id,
                "action_type": full.action_type,
                "target": full.target,
                "source": source,
                "decided_by": decided_by,
                "at": now.isoformat(),
            }
            row.parameters = parameters

        claimed = self._resolve(
            action_id,
            status_to=ActionStatus.ESCALATED,
            annotation=decision_rule(ESCALATION_LINK_FIELD, full.action_id),
            record=link,
        )
        if not claimed:
            return EscalationOutcome(
                action_id,
                False,
                full,
                (
                    "the speculative row was resolved during escalation; the "
                    f"full action {full.action_id} stands in the normal pipeline"
                ),
            )
        return EscalationOutcome(
            action_id,
            True,
            full,
            f"escalated to {full.action_id} ({full.action_type})",
        )

    # ------------------------------------------------------------------
    # retain — the adjudicator's one bounded extension
    # ------------------------------------------------------------------

    def retain(
        self, action_id: str, extension_seconds: Optional[int], *, actor: str
    ) -> RetainOutcome:
        """Extend a live speculative row's expiry — once, and bounded.

        The adjudicator's ``retain`` verdict: one more window on the same
        restriction, asked while the row is still live. The ask is clamped
        to ``max_ttl_seconds`` — an adjudicator's retain may never hold a
        restriction past the hard ceiling — and applies at most once per
        action: the claim reads the retention marker inside the row lock,
        so a second retain refuses without touching the row. The extension
        runs from the current expiry, not from now: a retain says "keep it
        longer", not "restart the clock". A row another actor resolved
        first is refused — the fail-safe always wins.
        """
        ask = (
            extension_seconds
            if extension_seconds is not None
            else self.config.default_ttl_seconds
        )
        if ask <= 0:
            return RetainOutcome(action_id, False, f"non-positive retention ask {ask}")
        extension = min(ask, self.config.max_ttl_seconds)
        now = datetime.now(timezone.utc)
        db = get_db_manager()
        with db.session_scope() as session:
            row = session.execute(
                select(ApprovalAction)
                .where(ApprovalAction.action_id == action_id)
                .where(ApprovalAction.status == ActionStatus.SPECULATIVE.value)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                return RetainOutcome(
                    action_id,
                    False,
                    "action is not speculative (unknown or already resolved)",
                )
            parameters = dict(row.parameters or {})
            adjudication = dict(parameters.get("adjudication") or {})
            if adjudication.get(RETENTION_FIELD):
                previous = adjudication[RETENTION_FIELD]
                return RetainOutcome(
                    action_id,
                    False,
                    f"already retained once by {previous.get('actor')!r}",
                )
            base = row.expires_at or now
            current = base if base > now else now
            new_expiry = current + timedelta(seconds=extension)
            adjudication[RETENTION_FIELD] = {
                "asked_seconds": ask,
                "extension_seconds": extension,
                "actor": actor,
                "from": current.isoformat(),
                "to": new_expiry.isoformat(),
                "at": now.isoformat(),
            }
            parameters["adjudication"] = adjudication
            row.expires_at = new_expiry
            row.parameters = parameters
            base_reason = row.reason or ""
            annotation = decision_rule(RETENTION_RULE_FIELD, str(extension))
            row.reason = f"{base_reason}; {annotation}" if base_reason else annotation
        return RetainOutcome(
            action_id, True, f"retained {extension}s", new_expiry, extension
        )

    # ------------------------------------------------------------------
    # expire — the fail-safe sweep
    # ------------------------------------------------------------------

    def expire(self, batch: int = SWEEP_BATCH) -> SweepOutcome:
        """Release every speculative row past its expiry, oldest first.

        Reads only ``status`` and ``expires_at`` — no adjudication state,
        no run table — so an adjudication that is slow, stuck or down can
        never hold a restriction past its TTL. Each row goes through the
        same ``release`` verb as a manual release; a row released by a
        racer in between is refused and left alone. A row whose release
        fails stays speculative and is retried next tick.
        """
        cutoff = datetime.now(timezone.utc)
        db = get_db_manager()
        with db.session_scope() as session:
            rows = (
                session.execute(
                    select(ApprovalAction)
                    .where(ApprovalAction.status == ActionStatus.SPECULATIVE.value)
                    .where(ApprovalAction.expires_at.is_not(None))
                    .where(ApprovalAction.expires_at < cutoff)
                    .order_by(ApprovalAction.expires_at)
                    .limit(batch)
                )
                .scalars()
                .all()
            )
            expired = [row.action_id for row in rows]
        released = 0
        for action_id in expired:
            try:
                outcome = self.release(
                    action_id, RELEASE_REASON_TTL_EXPIRED, TTL_SWEEP_ACTOR
                )
            except Exception:
                # A row whose adapter is unreachable stays speculative; the
                # next sweep retries it. One bad row must not stop the
                # rest of the batch.
                logger.exception("TTL release failed for %s", action_id)
                continue
            if outcome.released:
                released += 1
        return SweepOutcome(examined=len(expired), released=released)


def expire_speculative_actions(batch: int = SWEEP_BATCH) -> SweepOutcome:
    """The scheduler's entry: the fail-safe sweep on a default service."""
    return RollbackService().expire(batch)
