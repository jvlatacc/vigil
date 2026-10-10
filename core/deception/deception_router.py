"""Deception API endpoints (feature 5).

The operator surface over the lease registry: posture status, the lease
list, an operator release, the kill-switch toggle, the Settings ›
Deception knobs, and the captured-probe log. Authenticated like every
router (``Auth.REQUIRED``); reads demand ``deception.read`` and writes
``deception.manage`` — the keys the role seed grants (06_auth_tables.sql).

Kept unversioned (out of ``core/api/v1/``): the shape will churn as the
Deception screen matures, and the versioned contract snapshot would freeze
it prematurely — the v1 README's own tie-breaker.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth.current_user import get_current_user
from core.auth.permissions import permission_gate
from core.deception.config import (
    KILL_SWITCH_CONFIG_KEY,
    SETTINGS_CONFIG_KEY,
    VALID_BACKENDS,
    DeceptionConfig,
    allowlist_errors,
    clear_settings_cache,
)
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


@router.get("/status", dependencies=[permission_gate("deception.read")])
async def deception_status():
    """The posture summary: knobs, kill-switch state, lease counts."""
    config = DeceptionConfig.resolved()
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
        "allowlist": config.allowlist,
        "lease_counts": counts,
    }


@router.get("/leases", dependencies=[permission_gate("deception.read")])
async def list_leases(status: Optional[str] = None, limit: int = 200):
    """Lease rows newest-first, optionally filtered by status."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    service = DeceptionLeaseService(config=DeceptionConfig.resolved())
    statuses = [status.strip()] if status and status.strip() else None
    rows = service.list_leases(statuses=statuses, limit=limit)
    return {"leases": [_lease_to_dict(row) for row in rows], "count": len(rows)}


@router.post(
    "/leases/{lease_id}/release",
    dependencies=[permission_gate("deception.manage")],
)
async def release_lease(lease_id: str, body: Optional[LeaseRelease] = None):
    """Operator release: unsteer now, record the rollback and the reason."""
    service = DeceptionLeaseService(config=DeceptionConfig.resolved())
    result = await service.release(
        lease_id, (body and body.reason) or "operator_released"
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/kill-switch", dependencies=[permission_gate("deception.manage")])
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


class DeceptionSettingsWrite(BaseModel):
    """The Settings › Deception form, stored as one system_config row.

    Bounds mirror the steering semantics: a lease TTL a renewal can reach
    within the max duration, a corroboration window at least a minute wide,
    a floor anywhere in the confidence range. The backend ships as dry_run;
    ``controller`` is selectable here but build_backend refuses it until the
    decoy-controller service is configured — the status names that.
    """

    enabled: bool
    backend: str
    honey_route_floor: float = Field(ge=0.0, le=1.0)
    ttl_seconds: int = Field(ge=30, le=86400)
    max_duration_seconds: int = Field(ge=300, le=604800)
    min_observations: int = Field(ge=1, le=100)
    window_seconds: int = Field(ge=60, le=86400)
    allowlist: str = ""


@router.post("/settings", dependencies=[permission_gate("deception.manage")])
async def update_settings(
    body: DeceptionSettingsWrite,
    current_user: User = Depends(get_current_user),
):
    """Store the honey-routing knobs; they apply without a daemon restart."""
    if body.backend not in VALID_BACKENDS:
        raise HTTPException(
            status_code=422,
            detail=f"backend must be one of: {', '.join(VALID_BACKENDS)}",
        )
    if body.max_duration_seconds < body.ttl_seconds:
        raise HTTPException(
            status_code=422,
            detail="max_duration_seconds must be at least ttl_seconds",
        )
    bad = allowlist_errors(body.allowlist)
    if bad:
        raise HTTPException(
            status_code=422,
            detail=(
                "unparseable allowlist entries (IPs or CIDRs expected): "
                + ", ".join(bad)
            ),
        )

    from core.storage.config_service import get_config_service

    value = {
        "enabled": body.enabled,
        "backend": body.backend,
        "honey_route_floor": body.honey_route_floor,
        "ttl_seconds": body.ttl_seconds,
        "max_duration_seconds": body.max_duration_seconds,
        "min_observations": body.min_observations,
        "window_seconds": body.window_seconds,
        "allowlist": body.allowlist,
    }
    ok = get_config_service(user_id=str(current_user.user_id)).set_system_config(
        key=SETTINGS_CONFIG_KEY,
        value=value,
        description="Deception honey-routing settings",
        config_type="deception",
        change_reason="Updated via Settings UI",
    )
    if not ok:
        raise HTTPException(status_code=500, detail="failed to store the settings")
    clear_settings_cache()
    merged = DeceptionConfig.resolved()
    return {
        "enabled": merged.enabled,
        "backend": merged.backend,
        "honey_route_floor": merged.honey_route_floor,
        "ttl_seconds": merged.ttl_seconds,
        "max_duration_seconds": merged.max_duration_seconds,
        "min_observations": merged.min_observations,
        "window_seconds": merged.window_seconds,
        "allowlist": merged.allowlist,
    }


@router.get("/probes", dependencies=[permission_gate("deception.read")])
async def list_probes(source_ip: Optional[str] = None, limit: int = 200):
    """Recent recon observations newest-first — the captured-intel panel."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    from core.deception.signals import DeceptionSignalService

    service = DeceptionSignalService(config=DeceptionConfig.resolved())
    rows = service.list_probes(source_ip=source_ip, limit=limit)
    probes = [
        {
            "probe_id": row.probe_id,
            "source_ip": row.source_ip,
            "finding_id": row.finding_id,
            "evidence": row.evidence,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]
    return {"probes": probes, "count": len(probes)}
