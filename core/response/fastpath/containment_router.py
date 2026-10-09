"""Read-only containment lease visibility (``/api/containment``) — v1.

Console-only, deliberately outside ``/api/v1``: leases are operational state
while speculative containment settles, and the console decision surface is an
open question the spec defers to product. Freezing shapes now is the regret
the v1 README warns about.

Read-only on purpose — v1 exposes no mutation verb over HTTP. A lease's fate
is decided by the daemon: rollback and expiry are autonomy demotions (the TTL
sweeper and the responder's adjudication lane run on their own), and anything
stronger mints a request through the human-gated approvals pipeline, which
already has its own API (``core/api/v1/approvals_router.py``). The one
implementation behind these endpoints is ``adjudication.read_leases`` — the
same function the agent's ``lease_list`` tool reads.

Auth posture: ``Auth.REQUIRED`` — an authenticated user, the same posture as
the approvals read endpoints. Reads carry no ``undo_payload`` deliberately:
undo tokens are daemon-internal capability, and a visibility surface does not
hand them out.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.current_user import get_current_user
from core.response.fastpath.adjudication import get_lease_by_id, read_leases
from core.routing import Auth, RouterMeta
from core.storage.models import User

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/containment",
    tags=["containment"],
    auth=Auth.REQUIRED,
)


class ContainmentLeaseOut(BaseModel):
    """Read-only view of one containment lease (mirrors ``LeaseView`` minus
    the undo payload, which stays daemon-internal)."""

    lease_id: str
    action_type: str
    entity_type: str
    entity_id: str
    status: str = Field(
        ..., description="pending_apply | applied | rolled_back | escalated | failed"
    )
    idempotency_key: str
    finding_id: Optional[str] = None
    decision_rule: str
    observed: Dict[str, Any] = Field(
        default_factory=dict,
        description="Gate-time telemetry snapshot (severity, confidence, detector).",
    )
    is_shadow: bool
    ttl_seconds: Optional[int] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


class ContainmentLeaseListResponse(BaseModel):
    count: int
    leases: List[ContainmentLeaseOut] = Field(default_factory=list)


def _lease_to_dict(lease) -> Dict[str, Any]:
    """Normalise a ``LeaseView`` to a response dict (naive-UTC ISO strings)."""
    return {
        "lease_id": lease.id,
        "action_type": lease.action_type,
        "entity_type": lease.entity_type,
        "entity_id": lease.entity_id,
        "status": lease.status,
        "idempotency_key": lease.idempotency_key,
        "finding_id": lease.finding_id,
        "decision_rule": lease.decision_rule,
        "observed": dict(lease.observed or {}),
        "is_shadow": lease.is_shadow,
        "ttl_seconds": lease.ttl_seconds,
        "created_at": lease.created_at.isoformat() if lease.created_at else None,
        "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
    }


@router.get("/leases", response_model=ContainmentLeaseListResponse)
def list_leases(
    status: str = Query(
        default="active",
        description=(
            "active (pending_apply or applied, the default) or all "
            "(every row, newest first, terminal states included — the recent view)."
        ),
    ),
    entity_type: Optional[str] = Query(
        default=None, description="Filter by entity class: ip | user | host | domain."
    ),
    entity_id: Optional[str] = Query(
        default=None, description="Filter by the contained principal's id."
    ),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    """List containment leases, newest first. Read-only — the Fast-Path's
    fates are decided by the daemon; humans act through the approvals API."""
    try:
        leases = read_leases(
            status=status,
            limit=limit,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "count": len(leases),
        "leases": [_lease_to_dict(lease) for lease in leases],
    }


@router.get("/leases/{lease_id}", response_model=ContainmentLeaseOut)
def get_lease(
    lease_id: str,
    current_user: User = Depends(get_current_user),
):
    """One lease by id, terminal states included."""
    lease = get_lease_by_id(lease_id)
    if lease is None:
        raise HTTPException(status_code=404, detail=f"Lease not found: {lease_id}")
    return _lease_to_dict(lease)
