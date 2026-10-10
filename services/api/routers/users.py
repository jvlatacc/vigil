"""
User Management API - Admin endpoints for managing users.

Handles user CRUD operations, role assignment, and user administration.
"""

import asyncio
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.auth.auth_service import AuthService, union_permission_maps
from core.auth.password_validator import PasswordPolicyError, validate_password_strength
from core.auth.permissions import permission_gate
from core.auth.token_blacklist import revoke_all_for_user
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import Role, RoleAssignment, User
from core.storage.schemas import RoleSchema, UserSchema
from services.api.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/users",
    tags=["users"],
    auth=Auth.REQUIRED,
)


# Request/Response Models
class CreateUserRequest(BaseModel):
    """Create user request."""

    username: str
    email: EmailStr
    password: str
    full_name: str
    role_id: str


class UpdateUserRequest(BaseModel):
    """Update user request."""

    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_id: Optional[str] = None
    is_active: Optional[bool] = None
    # The subject an external identity provider names for this person, and the
    # only way an IdP token on the MCP surface becomes a Vigil account
    # (core/auth/idp_jwt.py). An admin sets it deliberately or leaves it empty;
    # nothing derives it from a token. None here means "leave it alone";
    # an empty string clears the mapping.
    external_subject: Optional[str] = None


class ChangeUserRoleRequest(BaseModel):
    """Change user role request."""

    role_id: str


class SetUserRolesRequest(BaseModel):
    """Replace a user's additional role assignments (the primary role is untouched)."""

    role_ids: List[str]


def _can_assign_roles(current_user: User, roles: List[Role], session: Session) -> bool:
    """Return True only if current_user holds every permission in the union of roles.

    Prevents a user with users.write from assigning — as a primary role or as
    additional assignments — a combination that grants more privileges than
    they themselves have. Multi-role makes the union the thing to compare:
    analyst+senior jointly can grant what either alone cannot.
    """
    current_perms = AuthService.get_user_permissions(current_user.user_id, session)
    granted = union_permission_maps(role.permissions for role in roles)
    for perm, ok in granted.items():
        if ok and not current_perms.get(perm, False):
            return False
    return True


@router.get("/", dependencies=[permission_gate("users.read")])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    *,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    List all users (requires users.read permission).

    Args:
        skip: Number of users to skip
        limit: Maximum number of users to return
        role_id: Filter by role ID
        is_active: Filter by active status
        search: Search in username, email, or full name
        current_user: Current authenticated user
        session: Database session

    Returns:
        List of users
    """
    try:
        query = session.query(User)

        # Apply filters
        if role_id:
            query = query.filter(User.role_id == role_id)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (User.username.ilike(search_pattern))
                | (User.email.ilike(search_pattern))
                | (User.full_name.ilike(search_pattern))
            )

        # Get total count
        total = query.count()

        # Apply pagination
        users = query.offset(skip).limit(limit).all()

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "users": UserSchema.dump_many(users),
        }

    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users",
        )


@router.get("/{user_id}")
def get_user(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Get user by ID (requires users.read permission).

    Args:
        user_id: User ID
        current_user: Current authenticated user
        session: Database session

    Returns:
        User information
    """
    # Viewing another user's record asks users.read, but a profile stays
    # viewable to itself — a conditional a static route gate cannot express,
    # so this one check stays in the handler.
    if user_id != current_user.user_id:
        if not AuthService.check_permission(current_user.user_id, "users.read"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: users.read required",
            )

    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user_dict = UserSchema.dump(user)

    # Add role information
    role = session.query(Role).filter(Role.role_id == user.role_id).first()
    if role:
        user_dict["role"] = RoleSchema.dump(role)

    # Add permissions
    user_dict["permissions"] = AuthService.get_user_permissions(user_id)

    return user_dict


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[permission_gate("users.write")],
)
def create_user(
    request: CreateUserRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Create a new user (requires users.write permission).

    Args:
        request: User creation details
        current_user: Current authenticated user
        session: Database session

    Returns:
        Created user information
    """
    # _can_assign_role below is the escalation guard — a different question
    # from the route's users.write, which the gate already answered.

    # Validate password against the full strength policy. Penalize passwords
    # built from the new account's own identifiers.
    try:
        validate_password_strength(
            request.password,
            user_inputs=[request.username, request.email],
        )
    except PasswordPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.as_detail(),
        )

    # Verify role exists
    role = session.query(Role).filter(Role.role_id == request.role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role ID"
        )

    if not _can_assign_roles(current_user, [role], session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot assign a role with more privileges than your own",
        )

    # Create user
    user = AuthService.create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        role_id=request.role_id,
        session=session,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )

    logger.info(f"User created by {current_user.username}: {user.username}")
    return UserSchema.dump(user)


def _apply_user_update(
    session: Session, current_user: User, user_id: str, request: UpdateUserRequest
) -> tuple[User, bool, dict]:
    """Sync half of update_user. Returns the user, whether its email changed, and the payload."""
    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    email_changed = False
    if request.full_name is not None:
        user.full_name = request.full_name

    if request.email is not None:
        existing = (
            session.query(User)
            .filter(User.email == request.email, User.user_id != user_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            )
        user.email = request.email
        user.is_verified = False
        email_changed = True

    if request.role_id is not None:
        role = session.query(Role).filter(Role.role_id == request.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role ID"
            )
        if not _can_assign_roles(current_user, [role], session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign a role with more privileges than your own",
            )
        user.role_id = request.role_id

    if request.is_active is not None:
        user.is_active = request.is_active

    if request.external_subject is not None:
        # A blank box clears the mapping: un-mapping an IdP subject is a
        # deliberate act too, and the UI has one field for both directions.
        subject = request.external_subject.strip() or None
        if subject is not None:
            if len(subject) > 255:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="External subject must be at most 255 characters",
                )
            existing = (
                session.query(User)
                .filter(User.external_subject == subject, User.user_id != user_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="External subject already in use",
                )
        user.external_subject = subject

    # Flush so the read-back sees server defaults; the request's unit
    # of work commits.
    session.flush()
    session.refresh(user)
    return user, email_changed, UserSchema.dump(user)


@router.put("/{user_id}", dependencies=[permission_gate("users.write")])
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Update user information (requires users.write permission).

    Args:
        user_id: User ID to update
        request: Update details
        current_user: Current authenticated user
        session: Database session

    Returns:
        Updated user information
    """
    try:
        user, email_changed, payload = await asyncio.to_thread(
            _apply_user_update, session, current_user, user_id, request
        )

        if email_changed:
            try:
                await revoke_all_for_user(user.user_id)
            except Exception as exc:
                logger.error(
                    "Email changed for %s but revoke_all_for_user failed: %s",
                    user.username,
                    exc,
                )

        logger.info(f"User updated by {current_user.username}: {user.username}")
        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )


@router.delete("/{user_id}", dependencies=[permission_gate("users.delete")])
def delete_user(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Delete a user (requires users.delete permission).

    Args:
        user_id: User ID to delete
        current_user: Current authenticated user
        session: Database session

    Returns:
        Success message
    """
    # Prevent self-deletion
    if user_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    # Get user
    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        username = user.username
        session.delete(user)

        logger.info(f"User deleted by {current_user.username}: {username}")
        return {"message": "User deleted successfully"}

    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user",
        )


def _apply_role_change(
    session: Session, current_user: User, user_id: str, role_id: str
) -> tuple[User, str, dict]:
    """Sync half of change_user_role. Returns the user, its previous role id, and the payload."""
    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    role = session.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role ID"
        )

    if not _can_assign_roles(current_user, [role], session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot assign a role with more privileges than your own",
        )

    old_role_id = user.role_id
    user.role_id = role_id
    # Flush so the read-back sees server defaults; the request's unit
    # of work commits.
    session.flush()
    session.refresh(user)
    return user, old_role_id, UserSchema.dump(user)


@router.put("/{user_id}/role", dependencies=[permission_gate("users.write")])
async def change_user_role(
    user_id: str,
    request: ChangeUserRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Change user role (requires users.write permission).

    Args:
        user_id: User ID
        request: New role ID
        current_user: Current authenticated user
        session: Database session

    Returns:
        Updated user information
    """
    try:
        user, old_role_id, payload = await asyncio.to_thread(
            _apply_role_change, session, current_user, user_id, request.role_id
        )

        # Invalidate the target user's existing tokens so the new
        # permissions take effect on their next request, not whenever their
        # cached token happens to expire.
        try:
            await revoke_all_for_user(user.user_id)
        except Exception as exc:
            logger.error(
                "Role changed for %s but revoke_all_for_user failed: %s. "
                "Old tokens may remain valid until natural expiry.",
                user.username,
                exc,
            )

        logger.info(
            f"User role changed by {current_user.username}: {user.username} from {old_role_id} to {request.role_id}"
        )
        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change role error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change user role",
        )


def _user_roles_payload(session: Session, user: User) -> dict:
    """The union view of what a user holds: primary role first, then assignments."""
    roles = AuthService.effective_roles(user, session)
    return {
        "user_id": user.user_id,
        "primary_role_id": user.role_id,
        "roles": RoleSchema.dump_many(roles),
        "permissions": AuthService.get_user_permissions(user.user_id, session),
    }


def _apply_role_assignments(
    session: Session, current_user: User, user_id: str, role_ids: List[str]
) -> tuple[User, dict]:
    """Sync half of set_user_roles. Returns the user and the union-view payload."""
    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # De-duplicate and drop the primary role: granting what the user already
    # holds as primary is a no-op, not a second row saying it twice.
    requested: List[str] = []
    for role_id in role_ids:
        if role_id != user.role_id and role_id not in requested:
            requested.append(role_id)

    roles: List[Role] = []
    for role_id in requested:
        role = session.query(Role).filter(Role.role_id == role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role ID"
            )
        roles.append(role)

    # The escalation guard reads the union of everything being granted —
    # the same rule a primary-role change obeys. Two grants the actor holds
    # separately are one grant the actor may make together.
    if not _can_assign_roles(current_user, roles, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot assign a role with more privileges than your own",
        )

    # Replace, not merge: the PUT is the whole additional set, so removing a
    # role is omitting it — the same contract the primary-role PUT keeps.
    session.query(RoleAssignment).filter(
        RoleAssignment.user_id == user.user_id
    ).delete()
    for role in roles:
        session.add(
            RoleAssignment(
                user_id=user.user_id,
                role_id=role.role_id,
                granted_by=current_user.username,
            )
        )

    # Flush so the read-back sees the new rows; the request's unit of work
    # commits.
    session.flush()
    return user, _user_roles_payload(session, user)


@router.get("/{user_id}/roles")
def list_user_roles(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    List every role a user holds (requires users.read, or the user themself).

    The union view: the primary role first, additional assignments after.
    What the user may do is the union of these — the same list authorization
    resolves, so the screen and the engine cannot disagree.
    """
    if user_id != current_user.user_id and not AuthService.check_permission(
        current_user.user_id, "users.read"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: users.read required",
        )

    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return _user_roles_payload(session, user)


@router.put("/{user_id}/roles", dependencies=[permission_gate("users.write")])
async def set_user_roles(
    user_id: str,
    request: SetUserRolesRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    Replace a user's additional role assignments (requires users.write).

    The primary role is ``users.role_id`` and changes through PUT /{user_id};
    this manages the grants on top of it. A permission change, so the target's
    tokens are revoked the way a primary-role change revokes them.
    """
    try:
        user, payload = await asyncio.to_thread(
            _apply_role_assignments, session, current_user, user_id, request.role_ids
        )

        try:
            await revoke_all_for_user(user.user_id)
        except Exception as exc:
            logger.error(
                "Roles changed for %s but revoke_all_for_user failed: %s. "
                "Old tokens may remain valid until natural expiry.",
                user.username,
                exc,
            )

        logger.info(
            "User roles set by %s: %s -> %s",
            current_user.username,
            user.username,
            request.role_ids,
        )
        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Set user roles error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set user roles",
        )


@router.get("/roles/list", dependencies=[permission_gate("users.read")])
def list_roles(
    current_user: Annotated[User, Depends(get_current_user)],
    session: UnitOfWorkSession,
):
    """
    List all available roles.

    Args:
        current_user: Current authenticated user
        session: Database session

    Returns:
        List of roles
    """
    try:
        roles = session.query(Role).all()
        return {"roles": RoleSchema.dump_many(roles)}

    except Exception as e:
        logger.error(f"List roles error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list roles",
        )
