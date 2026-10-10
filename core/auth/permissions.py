"""Role-permission gates for routes and tools.

``Auth.REQUIRED`` only proves a login. What the login's role may do is the
``roles.permissions`` grant, checked here. Lives in ``core`` beside
``current_user`` so contract routers under ``core.api.v1`` can use it without a
``core -> services`` import.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.auth.auth_service import AuthService
from core.auth.current_user import get_current_user
from core.storage.models import Role, User
from core.storage.unit_of_work import unit_of_work

APPROVE_PERMISSION = "ai_decisions.approve"
CASES_WRITE_PERMISSION = "cases.write"

# Tool-call authorization. ``tools.execute`` is the baseline grant; a role's
# map may also carry a per-server ``tools.server.<name>`` key whose value
# overrides the baseline for that one server (see role_allows_tool_call).
TOOL_EXECUTE_PERMISSION = "tools.execute"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_permission(
    *permissions: str, unsafe_only: bool = False
) -> Callable[..., User]:
    """Dependency that answers 403 unless the signed-in user holds the permission.

    Several names mean any-of: holding one of them is enough, and a caller
    holding none is refused. (A route that needs every name should check in
    its handler.) ``unsafe_only`` skips GET/HEAD/OPTIONS, for a router-level
    gate that guards the writes of a router whose reads stay open to every role.
    """

    def _check(request: Request, user: User = Depends(get_current_user)) -> User:
        if unsafe_only and request.method in _SAFE_METHODS:
            return user
        if not any(
            AuthService.check_permission(user.user_id, permission)
            for permission in permissions
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {' or '.join(permissions)} required",
            )
        return user

    return _check


def permission_gate(*permissions: str, unsafe_only: bool = False) -> Depends:
    """``Depends(require_permission(...))``, ready for ``dependencies=[...]``."""
    return Depends(require_permission(*permissions, unsafe_only=unsafe_only))


def username_has_permission(username: str, permission: str) -> bool:
    """Whether the account named ``username`` holds ``permission``.

    For paths that carry only a username (chat and MCP tool calls).
    """
    with unit_of_work() as session:
        user = session.query(User).filter(User.username == username).first()
        user_id = user.user_id if user else ""
    # An unknown id holds nothing, except under DEV_MODE, which grants all.
    return AuthService.check_permission(user_id, permission)


def tools_server_permission(server_name: str) -> str:
    """The per-server override key for tools on ``server_name``."""
    return f"tools.server.{server_name}"


def role_allows_tool_call(perms: Mapping[str, bool], server_name: str) -> bool:
    """Whether a role's permission map allows a tool call on ``server_name``.

    ``tools.server.<name>`` is a scoped override: when the map carries the
    key its value decides for that server; when absent the ``tools.execute``
    baseline decides; when neither is present the answer is no.
    """
    scoped = perms.get(tools_server_permission(server_name))
    if scoped is not None:
        return bool(scoped)
    return bool(perms.get(TOOL_EXECUTE_PERMISSION, False))


def username_has_tool_permission(username: str, server_name: str) -> bool:
    """Whether the account named ``username`` may call a tool on ``server_name``.

    For paths that carry only a username (chat and MCP tool calls), through
    the same override rule :func:`role_allows_tool_call` applies to a role.
    """
    with unit_of_work() as session:
        user = session.query(User).filter(User.username == username).first()
        user_id = user.user_id if user else ""
    # get_user_permissions is DEV_MODE-aware the same way check_permission is.
    return role_allows_tool_call(AuthService.get_user_permissions(user_id), server_name)


def can_assign_role(
    current_user: User, target_role: Role, session: Optional[Session] = None
) -> bool:
    """True only if ``current_user`` holds every permission ``target_role`` grants.

    One escalation guard for every path that hands out privileges — user role
    assignment and group→role mapping writes alike: a user with ``users.write``
    may not grant, directly or through a directory-group mapping, a role
    carrying more privileges than they themselves hold.
    """
    current_perms = AuthService.get_user_permissions(current_user.user_id, session)
    for perm, granted in (target_role.permissions or {}).items():
        if granted and not current_perms.get(perm, False):
            return False
    return True
