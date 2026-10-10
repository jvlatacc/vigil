"""The fast path's own API surface: list speculative actions, release one.

Unversioned by design — these routes are console plumbing for the
speculative lifecycle, not a durable external contract, so they stay out
of ``core/api/v1/`` (the frozen snapshots do not cover them). The list
endpoint is the decisions screen's data source: every row the fast path
created, with its expiry, its deciding rule, and what happened to it.
The release endpoint is a person's "release now" — the rollback service's
release verb with the session user named as the resolver, gated on
``ai_decisions.approve`` like every other decision a person makes.

Both handlers are plain ``def``: neither awaits anything, and the
rollback verb is synchronous adapter I/O plus a guarded transaction.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from core.auth.current_user import get_current_user
from core.auth.permissions import APPROVE_PERMISSION, permission_gate
from core.deps import provide_rollback
from core.response.approval_service import ActionStatus
from core.response.fastpath.rollback import RELEASE_REASON_HUMAN, RollbackService
from core.response.fastpath.speculative_service import FAST_PATH_ACTOR
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import ApprovalAction, User

router = APIRouter()

# Releasing a live restriction is a decision on a response action: the same
# permission the approve/reject endpoints demand.
_DECIDE = [permission_gate(APPROVE_PERMISSION)]

ROUTER_META = RouterMeta(
    # Console surface, deliberately unversioned — see the module docstring.
    prefix="/api/fast-path",
    tags=["fast-path"],
    auth=Auth.REQUIRED,
)

logger = logging.getLogger(__name__)


class FastPathAction(BaseModel):
    """One speculative-era ledger row as the console renders it."""

    action_id: str
    action_type: str
    title: Optional[str] = None
    target: Optional[str] = None
    status: str
    confidence: Optional[float] = None
    # The deciding rule at creation, annotated with the resolution when the
    # row left its live state — one field, the #917 string shape.
    reason: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    expires_at: Optional[str] = None
    # True when the enforcement adapter touched nothing external; surfaces
    # label these rows so a simulated restriction is never read as enforced.
    simulated: bool = False
    outcome: Optional[Dict[str, Any]] = None
    escalation: Optional[Dict[str, Any]] = None
    evidence: Optional[List[Any]] = None
    parameters: Optional[Dict[str, Any]] = None


class FastPathListResponse(BaseModel):
    count: int
    counts: Dict[str, int] = Field(default_factory=dict)
    actions: List[FastPathAction] = Field(default_factory=list)


class FastPathReleaseResponse(BaseModel):
    released: bool
    detail: str
    action: Optional[FastPathAction] = None


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _fast_path_action(row: ApprovalAction) -> FastPathAction:
    """Serialise one ledger row inside its session (nothing lazy, nothing detached)."""
    parameters = row.parameters if isinstance(row.parameters, dict) else {}
    outcome = row.execution_result if isinstance(row.execution_result, dict) else None
    escalation = parameters.get("escalation")
    return FastPathAction(
        action_id=row.action_id,
        action_type=row.action_type,
        title=row.title,
        target=row.target,
        status=row.status or "",
        confidence=float(row.confidence) if row.confidence is not None else None,
        reason=row.reason,
        created_at=_iso(row.created_at),
        created_by=row.created_by,
        expires_at=_iso(row.expires_at),
        simulated=bool(parameters.get("simulation")),
        outcome=outcome,
        escalation=escalation if isinstance(escalation, dict) else None,
        evidence=list(row.evidence) if row.evidence else None,
        parameters=parameters or None,
    )


@router.get("/actions", response_model=FastPathListResponse)
def list_fast_path_actions(
    session: UnitOfWorkSession,
    status: Optional[str] = Query(
        default=None,
        description=(
            "Filter by status: speculative | rolled_back | escalated | failed."
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List every speculative-era action the fast path created, newest first."""
    status_enum: Optional[ActionStatus] = None
    if status:
        try:
            status_enum = ActionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    query = session.query(ApprovalAction).filter(
        ApprovalAction.created_by == FAST_PATH_ACTOR
    )
    if status_enum is not None:
        query = query.filter(ApprovalAction.status == status_enum.value)
    rows = (
        query.order_by(
            ApprovalAction.created_at.desc(), ApprovalAction.action_id.desc()
        )
        .limit(limit)
        .all()
    )
    status_counts = dict(
        session.query(ApprovalAction.status, func.count())
        .filter(ApprovalAction.created_by == FAST_PATH_ACTOR)
        .group_by(ApprovalAction.status)
        .all()
    )
    return {
        "count": len(rows),
        "counts": status_counts,
        "actions": [_fast_path_action(r) for r in rows],
    }


@router.post(
    "/actions/{action_id}/release",
    response_model=FastPathReleaseResponse,
    dependencies=_DECIDE,
)
def release_fast_path_action(
    action_id: str,
    rollback: RollbackService = Depends(provide_rollback),
    current_user: User = Depends(get_current_user),
):
    """Release a live speculative restriction now, as a person's decision.

    Rides the rollback service's release verb unchanged — the same guarded
    claim the adjudicator and the TTL sweep race through — and records the
    session user as the resolver. The restriction is lifted through the
    enforcement adapter before the row is marked; a lifted-something-else
    is never reported as a release.
    """
    service = rollback.approvals
    existing = service.get_action(action_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Action not found: {action_id}")
    if existing.status != ActionStatus.SPECULATIVE.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Action is {existing.status}, not speculative; " "nothing to release"
            ),
        )

    outcome = rollback.release(
        action_id, RELEASE_REASON_HUMAN, actor=current_user.username
    )
    if outcome.released:
        return {
            "released": True,
            "detail": outcome.detail,
            "action": _released_row(action_id),
        }

    # Refused. A row left speculative means the enforcement point could not
    # lift the restriction (it stays live for the sweep's next tick); a row
    # resolved in between lost the release race. The state after the attempt
    # tells the two apart — the detail is the same refusal text either way.
    current = service.get_action(action_id)
    if current is not None and current.status == ActionStatus.SPECULATIVE.value:
        logger.warning("manual release refused for %s: %s", action_id, outcome.detail)
        raise HTTPException(status_code=502, detail=outcome.detail)
    raise HTTPException(status_code=409, detail=outcome.detail)


def _released_row(action_id: str) -> Optional[FastPathAction]:
    """The row just released, re-read for the response."""
    from core.storage.connection import get_db_manager

    db = get_db_manager()
    with db.session_scope() as session:
        row = session.get(ApprovalAction, action_id)
        return _fast_path_action(row) if row else None
