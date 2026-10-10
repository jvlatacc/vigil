"""Protected-assets admin API — the never-quarantine invariant's operator
surface (#944).

Operators declare and retire the assets the Responder may not auto-contain
against. Reads are `settings.read`; any change to the invariant set is
`settings.write` and lands in ``config_audit_log`` in the same transaction
as the row, so the audit cannot drift from the state it describes.

Routes are versioned-but-beta: the surface is API + audit for now (no admin
UI ships in this feature), and the shape stays out of the frozen contract
snapshot until it settles.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.current_user import get_current_user
from core.auth.permissions import permission_gate
from core.response.protected_assets import (
    ProtectedAssetConflict,
    ProtectedAssetError,
    create_protected_asset,
    invalidate_cache,
    list_protected_assets,
    remove_protected_asset,
)
from core.routing import Auth, RouterMeta
from core.storage.models import ConfigAuditLog, User
from core.storage.unit_of_work import unit_of_work

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/v1/response/protected-assets",
    tags=["protected-assets"],
    auth=Auth.REQUIRED,
    legacy_prefixes=("/api/response/protected-assets",),
)
logger = logging.getLogger(__name__)

_READ = [permission_gate("settings.read")]
_WRITE = [permission_gate("settings.write")]

_BETA = {"openapi_extra": {"x-vigil-beta": True}}

# config_audit_log.config_type for every change this router makes, so the
# invariant's history is one indexed query away.
AUDIT_CONFIG_TYPE = "protected_assets"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProtectedAssetResponse(BaseModel):
    """Frozen key set of one protected-asset row (beta: shape may settle)."""

    asset_id: str
    match_kind: str
    match_value: str
    asset_class: str
    label: str
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    removed_at: Optional[str] = None
    removed_by: Optional[str] = None
    removal_reason: Optional[str] = None
    active: bool = True


class ProtectedAssetListResponse(BaseModel):
    count: int
    assets: List[ProtectedAssetResponse] = Field(default_factory=list)


class CreateProtectedAssetRequest(BaseModel):
    match_kind: str = Field(
        ...,
        description="How to match the asset: 'ip', 'cidr', or 'hostname'.",
    )
    match_value: str = Field(
        ...,
        description=(
            "The asset to protect — one address (10.0.0.53), one network in"
            " CIDR notation (10.0.0.0/24), or one exact hostname"
            " (dc.corp.example.com)."
        ),
    )
    asset_class: str = Field(
        ...,
        description="dns | domain_controller | gateway | dhcp | database | other.",
    )
    label: str = Field(
        ...,
        description="Why it is protected — shown on every held action.",
        max_length=200,
    )


class RemoveProtectedAssetRequest(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        description="Why the asset's protection is being retired.",
        max_length=2000,
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit(
    session: Any,
    *,
    action: str,
    config_key: str,
    old_value: Optional[Dict[str, Any]],
    new_value: Optional[Dict[str, Any]],
    changed_by: str,
    change_reason: Optional[str],
) -> None:
    session.add(
        ConfigAuditLog(
            config_type=AUDIT_CONFIG_TYPE,
            config_key=config_key,
            action=action,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            change_reason=change_reason,
        )
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ProtectedAssetListResponse,
    dependencies=_READ,
    **_BETA,
)
def list_assets(
    include_removed: bool = Query(False, description="Include soft-removed rows."),
    current_user: User = Depends(get_current_user),
) -> ProtectedAssetListResponse:
    """List protected assets, newest first (active only by default)."""
    with unit_of_work() as session:
        assets = list_protected_assets(session, include_removed=include_removed)
    return ProtectedAssetListResponse(
        count=len(assets),
        assets=[ProtectedAssetResponse(**asset) for asset in assets],
    )


@router.post(
    "",
    response_model=ProtectedAssetResponse,
    status_code=201,
    dependencies=_WRITE,
    **_BETA,
)
def create_asset(
    request: CreateProtectedAssetRequest,
    current_user: User = Depends(get_current_user),
) -> ProtectedAssetResponse:
    """Declare an asset the Responder may never auto-contain against.

    The row is active immediately: the in-memory index drops its cache and
    the next evaluated action sees the invariant.
    """
    try:
        with unit_of_work() as session:
            asset = create_protected_asset(
                session,
                match_kind=request.match_kind,
                match_value=request.match_value,
                asset_class=request.asset_class,
                label=request.label,
                created_by=current_user.username,
            )
            _audit(
                session,
                action="create",
                config_key=asset["match_value"],
                old_value=None,
                new_value=asset,
                changed_by=current_user.username,
                change_reason=request.label,
            )
    except ProtectedAssetConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProtectedAssetError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return ProtectedAssetResponse(**asset)


@router.delete(
    "/{asset_id}",
    response_model=ProtectedAssetResponse,
    dependencies=_WRITE,
    **_BETA,
)
def remove_asset(
    asset_id: str,
    request: Optional[RemoveProtectedAssetRequest] = None,
    current_user: User = Depends(get_current_user),
) -> ProtectedAssetResponse:
    """Retire an asset's protection (soft delete; the row's history stays)."""
    reason = request.reason if request is not None else None
    try:
        with unit_of_work() as session:
            previous: Optional[Dict[str, Any]] = next(
                (
                    a
                    for a in list_protected_assets(session, include_removed=True)
                    if a["asset_id"] == asset_id
                ),
                None,
            )
            asset = remove_protected_asset(
                session,
                asset_id,
                removed_by=current_user.username,
                reason=reason,
            )
            if asset is None:
                raise HTTPException(
                    status_code=404, detail=f"No protected asset {asset_id}"
                )
            _audit(
                session,
                action="delete",
                config_key=asset["match_value"],
                old_value=previous,
                new_value=asset,
                changed_by=current_user.username,
                change_reason=reason,
            )
    except ProtectedAssetError as e:
        raise HTTPException(status_code=422, detail=str(e))
    invalidate_cache()
    return ProtectedAssetResponse(**asset)
