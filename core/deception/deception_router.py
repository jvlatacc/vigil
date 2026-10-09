"""Deception API endpoints (feature 5).

The operator surface over the lease registry: posture status, the lease
list, an operator release, and the kill-switch toggle. Authenticated like
every router (``Auth.REQUIRED``); the ``deception.read``/``deception.manage``
permission keys arrive with the console work that uses them — until those
keys are seeded, an authenticated session is the gate, which matches the
spine's inert defaults (the posture is off and the backend is dry-run).

Kept unversioned (out of ``core/api/v1/``): the shape will churn as the
Deception screen lands, and the versioned contract snapshot would freeze it
prematurely — the v1 README's own tie-breaker.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth.current_user import get_current_user
from core.deception.config import KILL_SWITCH_CONFIG_KEY, DeceptionConfig
from core.deception.leases import DeceptionLeaseService
from core.routing import Auth, RouterMeta
from core.storage.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/deception",
    tags=["deception"],
    auth=Auth.REQUIRED,
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _lease_to_dict(row) -> Dict[str, Any]:
    """The JSON-safe lease record the console renders."""
    return {
        "lease_id": row.lease_id,
        "attacker_ip": row.attacker_ip,
        "action_id": row.action_id,
        "destination_ips": list(row.destination_ips or []),
        "ports": [int(p) for p in (row.ports or [])],
        "status": row.status,
        "backend": row.backend,
        "backend_ref": row.backend_ref,
        "ttl_seconds": row.ttl_seconds,
        "started_at": _iso(row.started_at),
        "expires_at": _iso(row.expires_at),
        "renewal_count": row.renewal_count,
        "released_at": _iso(row.released_at),
        "release_reason": row.release_reason,
        "rollback_result": row.rollback_result,
        "created_at": _iso(row.created_at),
    }


class KillSwitchToggle(BaseModel):
    """The console kill-switch toggle write."""

    enabled: bool
    reason: Optional[str] = None


class LeaseRelease(BaseModel):
    """An operator release."""

    reason: Optional[str] = None


@router.get("/status")
async def deception_status():
    """The posture summary: knobs, kill-switch state, lease counts."""
    config = DeceptionConfig.from_settings()
    counts: Dict[str, int] = {}
    backend_error: Optional[str] = None
    try:
        from core.deception.signals import DeceptionSignalService

        service = DeceptionLeaseService(config=config)
        for row in service.list_leases(limit=500):
            counts[row.status] = counts.get(row.status, 0) + 1
        switch_active = DeceptionSignalService(config=config).kill_switch_active()
    except NotImplementedError as e:
        # A controller backend configured before its service ships: the
        # status screen must still render, naming the problem.
        backend_error = str(e)
        switch_active = config.kill_switch
    except Exception as e:  # noqa: BLE001
        backend_error = f"lease registry unavailable: {e}"
        switch_active = True  # the switch's pessimistic answer on failure

    return {
        "enabled": config.enabled,
        "backend": config.backend,
        "backend_error": backend_error,
        "honey_route_floor": config.honey_route_floor,
        "ttl_seconds": config.ttl_seconds,
        "max_duration_seconds": config.max_duration_seconds,
        "min_observations": config.min_observations,
        "window_seconds": config.window_seconds,
        "kill_switch_active": switch_active,
        "lease_counts": counts,
    }


@router.get("/leases")
async def list_leases(status: Optional[str] = None, limit: int = 200):
    """Lease rows newest-first, optionally filtered by status."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    service = DeceptionLeaseService(config=DeceptionConfig.from_settings())
    statuses = [status.strip()] if status and status.strip() else None
    rows = service.list_leases(statuses=statuses, limit=limit)
    return {"leases": [_lease_to_dict(row) for row in rows], "count": len(rows)}


@router.post("/leases/{lease_id}/release")
async def release_lease(lease_id: str, body: Optional[LeaseRelease] = None):
    """Operator release: unsteer now, record the rollback and the reason."""
    service = DeceptionLeaseService(config=DeceptionConfig.from_settings())
    result = await service.release(
        lease_id, (body and body.reason) or "operator_released"
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/kill-switch")
async def set_kill_switch(
    toggle: KillSwitchToggle,
    current_user: User = Depends(get_current_user),
):
    """Set the stored kill-switch toggle.

    The env override (``DAEMON_DECEPTION_KILL_SWITCH``) trips the switch
    independently and cannot be cleared from here; either source alone
    stops steering.
    """
    from core.storage.config_service import get_config_service

    ok = get_config_service(user_id=str(current_user.user_id)).set_system_config(
        key=KILL_SWITCH_CONFIG_KEY,
        value={"enabled": bool(toggle.enabled)},
        description="Deception honey-routing kill switch",
        config_type="deception",
        change_reason=toggle.reason or "kill-switch toggle",
    )
    if not ok:
        raise HTTPException(
            status_code=500, detail="failed to store the kill-switch state"
        )
    return {"enabled": bool(toggle.enabled)}
