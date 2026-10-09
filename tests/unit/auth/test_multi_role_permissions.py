"""Multi-role authorization: the union of a user's roles decides.

``role_assignments`` adds grants on top of the primary role (``users.role_id``,
kept for the first-admin bootstrap). These tests prove the engine resolves the
union — primary and assignments together — and that the users router's
escalation guard compares unions too: two roles an actor holds separately may
be granted together, but any role combination containing a permission the actor
lacks is refused.

Runs against the throwaway PostgreSQL the ``external_service`` marker
provisions (see ``tests/unit/conftest.py``) — permission resolution reads
through SQLAlchemy, so a fake session would test nothing.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from core.auth.auth_service import AuthService
from core.auth.permissions import username_has_permission
from core.storage.models import Role, RoleAssignment, User
from core.storage.unit_of_work import unit_of_work
from services.api.routers.users import _can_assign_roles

pytestmark = pytest.mark.external_service

ANALYST = Role(
    role_id="role-analyst",
    name="Analyst",
    description="",
    permissions={"findings.read": True, "findings.write": True, "cases.read": True},
    is_system_role=True,
)
SENIOR = Role(
    role_id="role-senior",
    name="Senior Analyst",
    description="",
    permissions={
        "findings.read": True,
        "cases.assign": True,
        "ai_decisions.approve": True,
    },
    is_system_role=True,
)
ADMIN = Role(
    role_id="role-admin",
    name="Admin",
    description="",
    permissions={
        "findings.read": True,
        "findings.write": True,
        "cases.read": True,
        "cases.assign": True,
        "ai_decisions.approve": True,
        "users.write": True,
    },
    is_system_role=True,
)
ROLES = (ANALYST, SENIOR, ADMIN)


def _seed_roles() -> None:
    with unit_of_work() as session:
        for role in ROLES:
            session.merge(role)


def _user_with_roles(username: str, primary: str, extra: tuple[str, ...] = ()):
    """A user with a primary role and the given additional assignments."""
    with unit_of_work() as session:
        user = AuthService.create_user(
            username=f"{username}",
            email=f"{username}@example.com",
            password="harbour-lantern-quartz-91",
            full_name=username,
            role_id=primary,
            session=session,
        )
        assert user is not None
        for role_id in extra:
            session.add(
                RoleAssignment(user_id=user.user_id, role_id=role_id, granted_by="test")
            )
        user_id = user.user_id
    return user_id


def test_effective_roles_primary_first_then_assignments():
    _seed_roles()
    user_id = _user_with_roles("union-order", ANALYST.role_id, (SENIOR.role_id,))

    with unit_of_work() as session:
        user = session.query(User).filter_by(user_id=user_id).one()
        roles = AuthService.effective_roles(user, session)

    assert [r.role_id for r in roles] == ["role-analyst", "role-senior"]


def test_check_permission_resolves_the_union():
    _seed_roles()
    # Primary analyst has no approval right; the senior assignment grants one.
    user_id = _user_with_roles("union-grants", ANALYST.role_id, (SENIOR.role_id,))

    assert AuthService.check_permission(user_id, "ai_decisions.approve") is True
    assert AuthService.check_permission(user_id, "findings.write") is True
    # Held by neither role: still denied.
    assert AuthService.check_permission(user_id, "users.write") is False


def test_fk_refuses_an_assignment_to_a_missing_role():
    """A dangling grant cannot exist: role_assignments.role_id is a real FK.

    The union walk still filters roles that vanish mid-flight (a row deleted
    out from under a live session), but storage itself refuses the state —
    the integrity of ``permissions = union(roles)`` starts here.
    """
    _seed_roles()
    user_id = _user_with_roles("union-ghost", ANALYST.role_id)

    with pytest.raises(IntegrityError):
        with unit_of_work() as session:
            session.add(
                RoleAssignment(user_id=user_id, role_id="role-ghost", granted_by="test")
            )

    # The refused row left nothing behind.
    assert AuthService.check_permission(user_id, "ai_decisions.approve") is False


def test_get_user_permissions_is_the_union_map():
    _seed_roles()
    user_id = _user_with_roles("union-map", ANALYST.role_id, (SENIOR.role_id,))

    permissions = AuthService.get_user_permissions(user_id)

    assert permissions["findings.write"] is True  # primary role
    assert permissions["ai_decisions.approve"] is True  # assignment
    assert "users.write" not in permissions


def test_username_has_permission_resolves_the_union():
    _seed_roles()
    _user_with_roles("union-by-name", ANALYST.role_id, (SENIOR.role_id,))

    assert username_has_permission("union-by-name", "ai_decisions.approve") is True
    assert username_has_permission("union-by-name", "users.write") is False


def test_guard_allows_a_union_the_actor_holds():
    _seed_roles()
    actor_id = _user_with_roles("guard-admin", ADMIN.role_id)

    with unit_of_work() as session:
        actor = session.query(User).filter_by(user_id=actor_id).one()
        roles = [
            session.query(Role).filter_by(role_id=r).one()
            for r in (ANALYST.role_id, SENIOR.role_id)
        ]
        assert _can_assign_roles(actor, roles, session) is True


def test_guard_refuses_a_union_the_actor_lacks():
    _seed_roles()
    # Senior holds approvals but not findings.write, which analyst grants.
    actor_id = _user_with_roles("guard-senior", SENIOR.role_id)

    with unit_of_work() as session:
        actor = session.query(User).filter_by(user_id=actor_id).one()
        analyst = session.query(Role).filter_by(role_id=ANALYST.role_id).one()
        assert _can_assign_roles(actor, [analyst], session) is False


def test_guard_allows_two_grants_the_actor_holds_separately():
    _seed_roles()
    # The case that motivated union comparison: the actor holds analyst and
    # senior as separate rows; granting both in one request must not fail
    # because no single role contains the other's permissions.
    actor_id = _user_with_roles("guard-combo", ANALYST.role_id, (SENIOR.role_id,))

    with unit_of_work() as session:
        actor = session.query(User).filter_by(user_id=actor_id).one()
        roles = [
            session.query(Role).filter_by(role_id=r).one()
            for r in (ANALYST.role_id, SENIOR.role_id)
        ]
        assert _can_assign_roles(actor, roles, session) is True
