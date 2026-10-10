"""Slow-path adjudication of fast-path containment leases (PR-4).

A lease's fate is decided here, in the deliberation loop's own lane — never
inside it. When a finding reaches the responder, every live lease on its
principals (or on the finding itself) is re-read against the evidence the
finding NOW carries, while the comparison baseline is the lease's
``observed`` snapshot — the telemetry frozen at gate-fire time. LLM triage
rewrites severity minutes after the gate fired (``_update_finding``'s
partial update), so adjudication compares what the gate SAW with what the
slow path now CLAIMS, never with a record that may already have been
mutated twice.

Three verdicts, in the order they are checked:

1. **rollback** — an autonomy demotion, needing no human: the finding was
   closed, or the current evidence fell below the band the lease was
   issued on (severity below the observed severity, out of the band
   entirely, or confidence under the current severity's floor). The
   rollback driver undoes the effect first and closes the row second; the
   CAS refuses a loser when the TTL sweeper raced us.
2. **escalate** — a promotion REQUEST, minted through the EXISTING
   approval pipeline (``ApprovalService.create_action`` with
   ``human_only=True`` — the caller's confidence is its own claim, so the
   row waits for a person; tools/mcp/vigil.py's ``create_approval_action``
   is the same semantics). It fires when the slow path's evidence is at
   least as strong as the lease's premise (severity holds or raises,
   confidence at or above the observed confidence) or the entity is
   churning. The lease itself is left untouched and applied: until the
   pipeline resolves, the milder lease remains the state of the world,
   still TTL-bounded, still sweeper-owned.
   ``ledger.mark_escalated`` (the applied→escalated CAS) is deliberately
   not called here — it belongs to the pipeline-resolution integration,
   and the approvals flow is frozen this PR. The mint is idempotent per
   lease (``fastpath-escalate:{lease_id}``), so replayed findings cannot
   queue duplicate approvals.
3. **hold** — the evidence weakened within the band: still above the
   severity's floor, but below the confidence the lease was issued on.
   Nothing to roll back, nothing to promote — the lease runs out its TTL.

Also here, because PR-3's ledger deferred it to this slice: closing
expired SHADOW rows. A shadow row is scored-but-never-applied, so the
sweeper — which scans ``applied`` rows — never sees it; left open it would
pin the entity's idempotency key forever and block every future live lease
for that principal. Closing is a ``failed`` transition with reason
``ttl_expired_before_apply``: honest — nothing was ever applied, and the
observation window closed.

This module is also the fastpath package's one DB-facing read surface,
shared by the daemon (counters for the gate, candidate leases) and by the
API router and MCP tools (the read-only lease list). It imports nothing
from services, the API surface, or the LLM stack — lint-imports holds for
the whole package.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select

from core.response.approval_service import ActionType, ApprovalService
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.gate import GateCounters
from core.response.fastpath.ledger import (
    ACTIVE_STATUSES,
    ACTOR_ADJUDICATOR,
    DOWNGRADED,
    FALSE_POSITIVE,
    PENDING_APPLY,
    REASON_TTL_EXPIRED_BEFORE_APPLY,
    ROLLED_BACK,
    ContainmentLedger,
    LeaseView,
    rollback_lease,
)
from core.storage.connection import get_db_manager
from core.storage.models import ContainmentAction
from core.time import utcnow

logger = logging.getLogger(__name__)

# The principal keys the gate reads (gate._PRINCIPAL_KEYS), in the gate's own
# selection order, paired with the entity_type each becomes in the ledger.
# The gate is a frozen PR-2 module that keeps its tuple private; walking the
# same order here recovers which key a target came from without the gate
# exposing internals. Parity is pinned by test — if the gate ever reorders or
# extends its keys, that test fails and this table must follow it.
PRINCIPAL_ENTITY_TYPES: Tuple[Tuple[str, str], ...] = (
    ("src_ips", "ip"),
    ("usernames", "user"),
    ("hostnames", "host"),
    ("domains", "domain"),
)

# The finding status that retires a containment's premise. Findings link to
# cases and a closed case closes the book on its findings
# (core.findings.alert_outcomes reads case.status == "closed"); a finding
# dict that arrives at the responder already carrying that disposition is a
# retraction of the evidence the lease was issued on.
CLOSED_FINDING_STATUSES = frozenset({"closed"})

# Escalation: repeated lease churn on one entity. Each rollback frees the
# entity's idempotency key, so churn — apply, roll back, apply again — is the
# one pattern the per-entity cap cannot see. Three completed cycles within
# the window is the v1 line; the threshold is a module constant (FastPathConfig
# is a frozen PR-2 file) and the escalation it mints is a human's call anyway.
CHURN_ESCALATION_THRESHOLD = 3

# How the escalation bridge maps a lease's entity class onto the approval
# pipeline's action vocabulary: the request asks for the DURABLE version of
# the same containment. Whether it is ever released is the human gate's
# decision, not ours — human_only=True holds the row whatever confidence says.
_ESCALATION_ACTION_BY_ENTITY_TYPE = {
    "ip": ActionType.WAF_BLOCK,
    "host": ActionType.WAF_BLOCK,
    "domain": ActionType.BLOCK_DOMAIN,
    "user": ActionType.DISABLE_USER,
}


def _adjudication_summary() -> Dict[str, Any]:
    """The zeroed per-finding adjudication summary (the caller's stats surface)."""
    return {
        "examined": 0,
        "rolled_back": 0,
        "escalated": 0,
        "held": 0,
        "contested": 0,
        "skipped_no_executor": 0,
    }


def _first_str(value: Any) -> Optional[str]:
    """First usable string of an entity_context field, else None — the
    gate's own tolerance for vendors that send a bare string for a list."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _confidence_of(finding: Dict[str, Any]) -> Optional[float]:
    """The confidence as the gate reads it: triage_confidence, 0.5 when a
    finding has not been triaged, None when the value is not a probability."""
    return _confidence_value(finding.get("triage_confidence", 0.5))


def _confidence_value(value: Any) -> Optional[float]:
    """``value`` as a probability in [0, 1], or None when it is not one."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if 0.0 <= confidence <= 1.0 else None


def principals_of(finding: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Every containable principal of a finding as ``(entity_type, id)``.

    The gate acts on the first of these; adjudication looks for leases on
    ALL of them — a finding that returns with its IP rewritten still
    reaches the lease issued on its username.
    """
    entities = finding.get("entity_context") or {}
    if not isinstance(entities, dict):
        return []
    pairs: List[Tuple[str, str]] = []
    for key, entity_type in PRINCIPAL_ENTITY_TYPES:
        value = _first_str(entities.get(key))
        if value is not None:
            pairs.append((entity_type, value))
    return pairs


def first_principal(finding: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """The principal the gate would target — the first in its selection order."""
    pairs = principals_of(finding)
    return pairs[0] if pairs else (None, None)


def entity_type_for_target(
    finding: Dict[str, Any], target: Optional[str]
) -> Optional[str]:
    """The entity_type of the principal key the gate selected ``target`` from.

    The gate picks the first non-empty string across its principal keys;
    re-walking that order for the value recovers the key. None when the
    target is absent from the finding — a lease cannot be keyed without its
    entity type, and inventing one would break the idempotency key.
    """
    if target is None:
        return None
    for key, entity_type in PRINCIPAL_ENTITY_TYPES:
        entities = finding.get("entity_context") or {}
        if _first_str(entities.get(key) if isinstance(entities, dict) else None) == (
            target
        ):
            return entity_type
    return None


# ----------------------------------------------------------------------
# The pure verdict
# ----------------------------------------------------------------------


class AdjudicationAction(str, Enum):
    """What the slow path does with a live lease on this evidence."""

    ROLLBACK = "rollback"
    ESCALATE = "escalate"
    HOLD = "hold"


@dataclass(frozen=True)
class AdjudicationVerdict:
    """One adjudication verdict: the action, the rule that decided it, and —
    for rollbacks — the reason from the ledger's rollback vocabulary."""

    action: AdjudicationAction
    rule: str
    reason: Optional[str] = None


def adjudicate(
    lease: LeaseView,
    finding: Dict[str, Any],
    config: FastPathConfig,
    rolled_back_in_window: int = 0,
    churn_threshold: int = CHURN_ESCALATION_THRESHOLD,
) -> AdjudicationVerdict:
    """Compare a live lease against the finding's current evidence.

    Pure: no clock, no database, no model. The baseline is the lease's
    observed snapshot (what the gate saw); the compared values are the
    finding's current severity and confidence — read exactly the way the
    gate reads them, so the two never disagree about what a field means.
    """
    observed = dict(lease.observed or {})
    observed_severity = str(observed.get("severity") or "").strip().lower()
    current_severity = str(finding.get("severity") or "").strip().lower()
    current_confidence = _confidence_of(finding)

    # (1) Closure. The disposition retired the premise; there is nothing to
    # keep containing and nothing to escalate toward.
    if str(finding.get("status") or "").strip().lower() in CLOSED_FINDING_STATUSES:
        return AdjudicationVerdict(
            action=AdjudicationAction.ROLLBACK,
            rule="fastpath.adjudication.finding_status=closed",
            reason=FALSE_POSITIVE,
        )

    # (2) Downgrade — the current evidence would no longer earn this lease.
    # A severity below the observed one is a demotion even when it is still
    # in the band: the critical mapping's rate_limit outruns what high
    # severity earns, and the milder mapping requires fresh evidence anyway
    # (the anti-flap floor).
    severity_rank = {"critical": 2, "high": 1}
    if severity_rank.get(current_severity, 0) < severity_rank.get(observed_severity, 0):
        return AdjudicationVerdict(
            action=AdjudicationAction.ROLLBACK,
            rule=(
                f"fastpath.adjudication.severity={current_severity or 'unset'}"
                f" below observed={observed_severity or 'unset'}"
            ),
            reason=DOWNGRADED,
        )
    if current_severity not in config.allowed_severities:
        return AdjudicationVerdict(
            action=AdjudicationAction.ROLLBACK,
            rule=(
                f"fastpath.adjudication.severity={current_severity or 'unset'}"
                " not in allowed_severities"
            ),
            reason=DOWNGRADED,
        )
    floor = {
        "critical": config.critical_action_floor,
        "high": config.high_action_floor,
    }.get(current_severity)
    if floor is not None and (current_confidence is None or current_confidence < floor):
        return AdjudicationVerdict(
            action=AdjudicationAction.ROLLBACK,
            rule=(
                f"fastpath.adjudication.confidence={current_confidence}"
                f" below {current_severity}_floor={floor}"
            ),
            reason=DOWNGRADED,
        )

    # (3) Escalation. Churn outranks the plain holds-condition: repeated
    # apply/rollback cycles mean the lease keeps coming back, and the
    # durable question belongs to a human either way.
    if rolled_back_in_window >= churn_threshold:
        return AdjudicationVerdict(
            action=AdjudicationAction.ESCALATE,
            rule=(
                f"fastpath.adjudication.churn={rolled_back_in_window}"
                f">={churn_threshold} rollbacks in window"
            ),
        )
    # "Severity holds or raises": the slow path's evidence is at least as
    # strong as the lease's premise — same or higher severity rank, at or
    # above the observed confidence. That is a promotion question, and
    # promotion is a person's call. An unknown observed confidence cannot
    # claim this, so it holds (no promotion on an incomplete snapshot).
    observed_confidence = _confidence_value(observed.get("confidence"))
    if (
        severity_rank.get(current_severity, 0)
        >= severity_rank.get(observed_severity, 0)
        and current_confidence is not None
        and observed_confidence is not None
        and current_confidence >= observed_confidence
    ):
        return AdjudicationVerdict(
            action=AdjudicationAction.ESCALATE,
            rule=(
                f"fastpath.adjudication.evidence_holds severity={current_severity}"
                f" confidence={current_confidence}>=observed={observed_confidence}"
            ),
        )

    # (4) Hold. Weakened within the band — above the floor, below the
    # premise. The lease runs out its TTL; the sweeper is the backstop.
    return AdjudicationVerdict(
        action=AdjudicationAction.HOLD,
        rule="fastpath.adjudication.evidence_between_bands",
    )


# ----------------------------------------------------------------------
# The DB-facing read surface (daemon wiring, router, MCP tools)
# ----------------------------------------------------------------------


def gate_counters(
    finding: Dict[str, Any],
    config: FastPathConfig,
    db_manager: Optional[Any] = None,
    now: Optional[datetime] = None,
) -> GateCounters:
    """The live lease state the gate's caps compare against.

    One read, three numbers, all scoped to what the finding can move: the
    active leases on its target principal (the per-entity cap), the leases
    its detector triggered inside the rolling window (the per-window cap),
    and the seconds since that principal last rolled back (the anti-flap
    floor). A finding with no principal gets an empty slate — the gate
    refuses it on entity class before any cap could matter.
    """
    entity_type, entity_id = first_principal(finding)
    if entity_id is None:
        return GateCounters()
    detector = str(finding.get("detector") or finding.get("data_source") or "")
    now = now or utcnow()
    window_start = now - timedelta(seconds=config.window_seconds)
    manager = db_manager or get_db_manager()
    with manager.session_scope() as session:
        active_for_entity = session.execute(
            select(func.count())
            .select_from(ContainmentAction)
            .where(
                ContainmentAction.entity_type == entity_type,
                ContainmentAction.entity_id == entity_id,
                ContainmentAction.status.in_(ACTIVE_STATUSES),
            )
        ).scalar_one()
        in_window = session.execute(
            select(func.count())
            .select_from(ContainmentAction)
            .where(
                ContainmentAction.created_at >= window_start,
                ContainmentAction.observed["detector"].astext == detector,
            )
        ).scalar_one()
        last_rollback_at = session.execute(
            select(func.max(ContainmentAction.rolled_back_at)).where(
                ContainmentAction.entity_type == entity_type,
                ContainmentAction.entity_id == entity_id,
                ContainmentAction.status == ROLLED_BACK,
            )
        ).scalar_one()
    seconds_since = (
        (now - last_rollback_at).total_seconds() if last_rollback_at else None
    )
    return GateCounters(
        active_leases_for_entity=active_for_entity,
        leases_in_window=in_window,
        seconds_since_last_rollback=seconds_since,
    )


def get_lease_by_id(
    lease_id: str,
    db_manager: Optional[Any] = None,
) -> Optional[LeaseView]:
    """One lease by id, any state — the router's and MCP tool's single-lease read."""
    manager = db_manager or get_db_manager()
    with manager.session_scope() as session:
        row = session.get(ContainmentAction, lease_id)
        if row is None:
            return None
        return LeaseView.from_row(row)


def read_leases(
    status: str = "active",
    limit: int = 50,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    db_manager: Optional[Any] = None,
) -> List[LeaseView]:
    """The read-only lease list — the one implementation behind the router
    and the MCP ``lease_list`` tool.

    ``status`` is ``"active"`` (pending_apply or applied, the default) or
    ``"all"`` (every row, newest first, terminal states included — the
    recent view). Terminal states free an entity's idempotency key, which
    is exactly what the recent view exists to show.
    """
    if status not in ("active", "all"):
        raise ValueError(f"status must be 'active' or 'all', got {status!r}")
    manager = db_manager or get_db_manager()
    stmt = select(ContainmentAction)
    if status == "active":
        stmt = stmt.where(ContainmentAction.status.in_(ACTIVE_STATUSES))
    if entity_type is not None:
        stmt = stmt.where(ContainmentAction.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ContainmentAction.entity_id == entity_id)
    stmt = stmt.order_by(ContainmentAction.created_at.desc()).limit(max(1, limit))
    with manager.session_scope() as session:
        rows = session.execute(stmt).scalars().all()
        return [LeaseView.from_row(row) for row in rows]


# ----------------------------------------------------------------------
# The adjudicator — the responder lane's collaborator
# ----------------------------------------------------------------------


class FastPathAdjudicator:
    """Finds the leases a finding touches and carries out their verdicts.

    Rollbacks run through the ledger's driver (undo first, CAS second);
    escalations mint into the SAME ``ApprovalService`` the responder already
    holds — one pipeline, one queue, one human gate. Nothing here ever
    promotes: the strongest thing this class can do alone is stop.
    """

    def __init__(
        self,
        approvals: ApprovalService,
        ledger: Optional[ContainmentLedger] = None,
        registry: Optional[Any] = None,
        config: Optional[FastPathConfig] = None,
        churn_threshold: int = CHURN_ESCALATION_THRESHOLD,
        churn_window_seconds: int = 3600,
        db_manager: Optional[Any] = None,
    ):
        self._approvals = approvals
        self._ledger = ledger or ContainmentLedger(
            db_manager=db_manager if db_manager is not None else None
        )
        if registry is None:
            from core.response.fastpath.executors import default_registry

            registry = default_registry()
        self._registry = registry
        self._config = config or FastPathConfig.from_settings()
        self._churn_threshold = churn_threshold
        self._churn_window_seconds = churn_window_seconds
        self._db_manager = db_manager

    async def on_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """Adjudicate every live lease this finding touches.

        Runs on the responder's worker — the deliberation loop's cadence,
        not the millisecond path's. The summary it returns is the caller's
        stats surface; failures propagate (the responder contains them), so
        an adjudication bug is visible rather than silently absorbed.

        A disabled Fast-Path has no leases to adjudicate, so the skip keeps
        the disabled path DB-free; the TTL sweep remains the backstop for
        any lease that outlived the switch — expiry is datastore-enforced
        and the sweeper runs unconditionally.
        """
        if not self._config.enabled:
            return _adjudication_summary()
        leases = await asyncio.to_thread(self._candidate_leases, finding)
        summary = _adjudication_summary()
        summary["examined"] = len(leases)
        for lease in leases:
            churn = await asyncio.to_thread(
                self._rolled_back_in_window, lease.entity_type, lease.entity_id
            )
            verdict = adjudicate(
                lease,
                finding,
                self._config,
                rolled_back_in_window=churn,
                churn_threshold=self._churn_threshold,
            )
            if verdict.action is AdjudicationAction.ROLLBACK:
                executor = self._registry.get(lease.action_type)
                if executor is None:
                    # The sweeper skips these too: a missing executor is
                    # never a rollback, and undoing nothing must not be
                    # recorded as one.
                    summary["skipped_no_executor"] += 1
                    continue
                transition = await rollback_lease(
                    self._ledger, executor, lease.id, verdict.reason or DOWNGRADED
                )
                if transition is None:
                    # The sweeper's CAS won the race; its undo was
                    # idempotent, so the double-fire was harmless.
                    summary["contested"] += 1
                else:
                    summary["rolled_back"] += 1
                    logger.info(
                        "fast-path adjudication: lease %s rolled back (%s)",
                        lease.id,
                        verdict.rule,
                    )
            elif verdict.action is AdjudicationAction.ESCALATE:
                await asyncio.to_thread(self._mint_escalation, lease, verdict)
                summary["escalated"] += 1
            else:
                summary["held"] += 1
        return summary

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _manager(self) -> Any:
        return self._db_manager or get_db_manager()

    def _candidate_leases(self, finding: Dict[str, Any]) -> List[LeaseView]:
        """Live leases on the finding's principals, or minted by the finding."""
        conditions: List[Any] = []
        finding_id = finding.get("finding_id")
        if finding_id:
            conditions.append(ContainmentAction.finding_id == str(finding_id))
        for entity_type, entity_id in principals_of(finding):
            conditions.append(
                and_(
                    ContainmentAction.entity_type == entity_type,
                    ContainmentAction.entity_id == entity_id,
                )
            )
        if not conditions:
            return []
        with self._manager().session_scope() as session:
            rows = (
                session.execute(
                    select(ContainmentAction)
                    .where(
                        ContainmentAction.status.in_(ACTIVE_STATUSES),
                        or_(*conditions),
                    )
                    .order_by(ContainmentAction.created_at)
                    .limit(50)
                )
                .scalars()
                .all()
            )
        seen: Dict[str, LeaseView] = {}
        for row in rows:
            view = LeaseView.from_row(row)
            seen.setdefault(view.id, view)
        return list(seen.values())

    def _rolled_back_in_window(self, entity_type: str, entity_id: str) -> int:
        """Completed rollback cycles for this principal inside the churn window."""
        cutoff = utcnow() - timedelta(seconds=self._churn_window_seconds)
        with self._manager().session_scope() as session:
            return session.execute(
                select(func.count())
                .select_from(ContainmentAction)
                .where(
                    ContainmentAction.entity_type == entity_type,
                    ContainmentAction.entity_id == entity_id,
                    ContainmentAction.status == ROLLED_BACK,
                    ContainmentAction.rolled_back_at >= cutoff,
                )
            ).scalar_one()

    def _mint_escalation(self, lease: LeaseView, verdict: AdjudicationVerdict) -> None:
        """Mint the promotion request into the existing approval pipeline.

        ``human_only=True`` is the point: the adjudicator's confidence is
        its own claim, so the row waits for a person whatever it says. The
        lease stays applied and TTL-bounded until the pipeline resolves;
        ``mark_escalated`` is the pipeline-resolution integration's call,
        not this slice's.
        """
        action_type = _ESCALATION_ACTION_BY_ENTITY_TYPE.get(
            lease.entity_type, ActionType.CUSTOM
        )
        observed_confidence = lease.observed.get("confidence")
        try:
            observed_confidence = (
                float(observed_confidence) if observed_confidence is not None else 0.0
            )
        except (TypeError, ValueError):
            observed_confidence = 0.0
        approval = self._approvals.create_action(
            action_type=action_type,
            title=(
                f"Fast-Path escalation: durable {action_type.value} for"
                f" {lease.entity_type} {lease.entity_id}"
            ),
            description=(
                f"Containment lease {lease.id} ({lease.action_type}) is live and"
                f" the slow path's evidence supports it. A person decides whether"
                f" to promote to a durable block; the lease itself stays applied"
                f" and expires on its own TTL meanwhile."
            ),
            target=lease.entity_id,
            confidence=max(0.0, min(1.0, observed_confidence)),
            reason=verdict.rule,
            evidence=[
                f"lease:{lease.id}",
                f"lease_action:{lease.action_type}",
                f"lease_rule:{lease.decision_rule}",
            ]
            + ([f"finding:{lease.finding_id}"] if lease.finding_id else []),
            created_by=ACTOR_ADJUDICATOR,
            human_only=True,
            idempotency_key=f"fastpath-escalate:{lease.id}",
            parameters={
                "lease_id": lease.id,
                "lease_action_type": lease.action_type,
                "entity_type": lease.entity_type,
                "entity_id": lease.entity_id,
                "rule": verdict.rule,
            },
        )
        logger.info(
            "fast-path adjudication: escalation minted lease=%s approval=%s (%s)",
            lease.id,
            approval.action_id,
            verdict.rule,
        )


# ----------------------------------------------------------------------
# Shadow-row closing — the slice PR-3 deferred to PR-4
# ----------------------------------------------------------------------


def close_expired_shadow_rows(
    now: Optional[datetime] = None,
    batch_size: int = 100,
    ledger: Optional[ContainmentLedger] = None,
    db_manager: Optional[Any] = None,
) -> int:
    """Close shadow rows whose observation window has ended.

    Shadow rows never apply, so the sweeper never sees them — but each open
    one holds its entity's idempotency key, and a key pinned by a stale
    shadow row would quietly block every future live lease for that
    principal. Closing is a ``failed`` transition with
    ``ttl_expired_before_apply``: nothing was ever applied, and the window
    closed. Returns the number of rows closed.
    """
    now = now or utcnow()
    ledger = ledger or ContainmentLedger(
        db_manager=db_manager if db_manager is not None else None
    )
    manager = db_manager or get_db_manager()
    with manager.session_scope() as session:
        rows = (
            session.execute(
                select(ContainmentAction)
                .where(
                    ContainmentAction.status == PENDING_APPLY,
                    ContainmentAction.is_shadow.is_(True),
                    ContainmentAction.expires_at.is_not(None),
                    ContainmentAction.expires_at <= now,
                )
                .order_by(ContainmentAction.expires_at)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        expired = [LeaseView.from_row(row) for row in rows]
    closed = 0
    for lease in expired:
        transition = ledger.mark_failed(
            lease.id, REASON_TTL_EXPIRED_BEFORE_APPLY, ACTOR_ADJUDICATOR
        )
        if transition is not None:
            closed += 1
    return closed
