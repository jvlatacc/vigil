"""Directory-group → role mapping admin (Settings → Roles).

A mapping row grants its role's permissions to every holder of that directory
group at their next login, so every route demands ``users.write`` — reads
included, the same bar the users router applies to its writes — and every
write re-proves the actor could hold the mapped role (the shared
privilege-escalation guard, ``core.auth.permissions.can_assign_role``): no
one may grant privileges beyond their own. Deleting a mapping only removes
access, so it needs no guard.
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from core.auth.permissions import can_assign_role, permission_gate
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import Role, RoleGroupMapping, User
from services.api.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/role-group-mappings",
    tags=["users"],
    auth=Auth.REQUIRED,
    # Router-level, not per-route: a mapping route added later inherits the
    # gate instead of forgetting it.
    extra_dependencies=[permission_gate("users.write")],
)


class CreateMappingRequest(BaseModel):
    """Create-mapping request."""

    role_id: str
    idp_group: str
    priority: int = 100

    @field_validator("idp_group")
    @classmethod
    def _idp_group_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("idp_group must not be empty")
        return value


class UpdateMappingRequest(BaseModel):
    """Update-mapping request."""

    role_id: Optional[str] = None
    idp_group: Optional[str] = None
    priority: Optional[int] = None

    @field_validator("idp_group")
    @classmethod
    def _idp_group_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("idp_group must not be empty")
        return value


def _payload(mapping: RoleGroupMapping, role_name: str) -> dict:
    return {
        "id": mapping.id,
        "role_id": mapping.role_id,
        "role_name": role_name,
        "idp_group": mapping.idp_group,
        "priority": mapping.priority,
        "created_at": (mapping.created_at.isoformat() if mapping.created_at else None),
    }


def _get_mapping(session: Session, mapping_id: int) -> RoleGroupMapping:
    mapping = (
        session.query(RoleGroupMapping)
        .filter(RoleGroupMapping.id == mapping_id)
        .first()
    )
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found"
        )
    return mapping


def _authorize_mapped_role(current_user: User, role_id: str, session: Session) -> Role:
    """The role a write targets, after the escalation guard passes.

    Same semantics as user role assignment: an actor with ``users.write`` may
    not hand out — or keep alive — a mapping onto a role whose permissions
    outrank their own.
    """
    role = session.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role ID"
        )
    if not can_assign_role(current_user, role, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot map a group to a role with more privileges than your own",
        )
    return role


@router.get("/")
def list_mappings(session: UnitOfWorkSession):
    """List group→role mappings, highest priority first."""
    mappings = (
        session.query(RoleGroupMapping)
        .order_by(RoleGroupMapping.priority.desc(), RoleGroupMapping.id.asc())
        .all()
    )
    names = {r.role_id: r.name for r in session.query(Role).all()}
    return {
        "total": len(mappings),
        "mappings": [_payload(m, names.get(m.role_id, "")) for m in mappings],
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_mapping(
    request: CreateMappingRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """Map one directory group onto one role."""
    role = _authorize_mapped_role(current_user, request.role_id, session)

    duplicate = (
        session.query(RoleGroupMapping)
        .filter(
            RoleGroupMapping.idp_group == request.idp_group,
            RoleGroupMapping.role_id == request.role_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This group is already mapped to this role",
        )

    mapping = RoleGroupMapping(
        role_id=request.role_id,
        idp_group=request.idp_group,
        priority=request.priority,
    )
    session.add(mapping)
    # Flush so the read-back sees the server defaults; the request's unit
    # of work commits.
    session.flush()
    session.refresh(mapping)

    logger.info(
        "Group→role mapping created by %s: %s -> %s",
        current_user.username,
        request.idp_group,
        request.role_id,
    )
    return _payload(mapping, role.name)


@router.put("/{mapping_id}")
def update_mapping(
    mapping_id: int,
    request: UpdateMappingRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """Update a mapping's group, role, or priority."""
    mapping = _get_mapping(session, mapping_id)

    target_role_id = request.role_id if request.role_id is not None else mapping.role_id
    role = _authorize_mapped_role(current_user, target_role_id, session)

    if request.idp_group is not None:
        mapping.idp_group = request.idp_group
    if request.role_id is not None:
        mapping.role_id = request.role_id
    if request.priority is not None:
        mapping.priority = request.priority

    duplicate = (
        session.query(RoleGroupMapping)
        .filter(
            RoleGroupMapping.idp_group == mapping.idp_group,
            RoleGroupMapping.role_id == mapping.role_id,
            RoleGroupMapping.id != mapping.id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This group is already mapped to this role",
        )

    # Flush so the read-back sees the changes; the request's unit of work
    # commits.
    session.flush()
    session.refresh(mapping)

    logger.info(
        "Group→role mapping updated by %s: id %s -> %s",
        current_user.username,
        mapping_id,
        mapping.role_id,
    )
    return _payload(mapping, role.name)


@router.delete("/{mapping_id}")
def delete_mapping(
    mapping_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """Delete a mapping. Removes access; grants nothing."""
    mapping = _get_mapping(session, mapping_id)

    idp_group = mapping.idp_group
    session.delete(mapping)

    logger.info(
        "Group→role mapping deleted by %s: %s (%s)",
        current_user.username,
        idp_group,
        mapping.role_id,
    )
    return {"message": "Mapping deleted successfully"}
