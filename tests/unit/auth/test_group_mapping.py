"""Directory groups resolve to roles, and tool calls answer to the map.

Two seams, one guarantee: a federated user's groups land them on exactly one
role — highest priority wins, no match means none — and a role's permission
map decides tool calls through the ``tools.execute`` baseline with a
per-server ``tools.server.<name>`` override. The mapping admin's own guards
(the ``users.write`` gate is checked statically by the route-permission
ratchet; what a unit test can prove is the escalation guard behind it) are
exercised by calling the router functions directly over SQLite, the same way
``test_mcp_credentials.py`` grounds its storage tests.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from core.auth.group_mapping import resolve_role_for_groups
from core.auth.permissions import (
    TOOL_EXECUTE_PERMISSION,
    role_allows_tool_call,
    tools_server_permission,
)
from core.storage.models import Role, RoleGroupMapping, User
from core.storage.models.base import Base
from services.api.routers import role_group_mappings as mapping_router

pytestmark = pytest.mark.unit

ADMIN_PERMS = {
    "findings.read": True,
    "findings.write": True,
    "findings.delete": True,
    "cases.read": True,
    "cases.write": True,
    "cases.delete": True,
    "cases.assign": True,
    "integrations.read": True,
    "integrations.write": True,
    "users.read": True,
    "users.write": True,
    "users.delete": True,
    "settings.read": True,
    "settings.write": True,
    "ai_chat.use": True,
    "ai_decisions.approve": True,
    TOOL_EXECUTE_PERMISSION: True,
}

ANALYST_PERMS = {
    "findings.read": True,
    "findings.write": True,
    "cases.read": True,
    "cases.write": True,
    "integrations.read": True,
    "settings.read": True,
    "ai_chat.use": True,
    TOOL_EXECUTE_PERMISSION: True,
}

VIEWER_PERMS = {
    "findings.read": True,
    "cases.read": True,
}


# `roles` and `users` carry JSONB columns SQLite cannot render at all.
# Registered for the SQLite dialect only.
@compiles(JSONB, "sqlite")
def _jsonb_is_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


# SQLite auto-increments only an exactly-INTEGER primary key; BIGSERIAL-style
# BIGINT ids (what Postgres gets) would insert NULL. Same dialect-shim
# pattern as the JSONB renderer above.
@compiles(BigInteger, "sqlite")
def _bigint_is_integer_on_sqlite(type_, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Role.__table__, User.__table__, RoleGroupMapping.__table__]
    )
    maker = sessionmaker(bind=engine)
    s = maker()
    s.add(
        Role(
            role_id="role-admin",
            name="Admin",
            description="",
            permissions=dict(ADMIN_PERMS),
        )
    )
    s.add(
        Role(
            role_id="role-analyst",
            name="Analyst",
            description="",
            permissions=dict(ANALYST_PERMS),
        )
    )
    s.add(
        Role(
            role_id="role-viewer",
            name="Viewer",
            description="",
            permissions=dict(VIEWER_PERMS),
        )
    )
    s.add(
        User(
            user_id="u-admin",
            username="ada",
            email="ada@example.com",
            password_hash="x",
            full_name="Ada",
            role_id="role-admin",
            is_active=True,
        )
    )
    s.add(
        User(
            user_id="u-analyst",
            username="rory",
            email="rory@example.com",
            password_hash="x",
            full_name="Rory",
            role_id="role-analyst",
            is_active=True,
        )
    )
    s.commit()
    yield s
    s.close()


def admin_user(session):
    return session.query(User).filter(User.user_id == "u-admin").one()


def analyst_user(session):
    return session.query(User).filter(User.user_id == "u-analyst").one()


def add_mapping(session, role_id, idp_group, priority=100):
    mapping = RoleGroupMapping(role_id=role_id, idp_group=idp_group, priority=priority)
    session.add(mapping)
    session.commit()
    return mapping


# --- resolution ----------------------------------------------------------


def test_no_groups_resolve_to_no_role(session):
    add_mapping(session, "role-analyst", "vigil-analysts")
    assert resolve_role_for_groups([]) is None


def test_unmatched_groups_resolve_to_no_role(session):
    add_mapping(session, "role-analyst", "vigil-analysts")
    assert resolve_role_for_groups(["docker-users", "vpn"], session) is None


def test_a_mapped_group_lands_its_role(session):
    add_mapping(session, "role-analyst", "vigil-analysts")
    role = resolve_role_for_groups(["docker-users", "vigil-analysts"], session)
    assert role is not None and role.role_id == "role-analyst"


def test_the_highest_priority_mapping_wins(session):
    add_mapping(session, "role-analyst", "vigil-analysts", priority=50)
    add_mapping(session, "role-admin", "vigil-admins", priority=10)
    role = resolve_role_for_groups(["vigil-analysts", "vigil-admins"], session)
    assert role is not None and role.role_id == "role-analyst"


def test_equal_priorities_tie_break_deterministically(session):
    # Equal priority: the earliest-created row wins, so re-running the same
    # login against the same mappings always lands the same role.
    add_mapping(session, "role-viewer", "vigil-viewers", priority=100)
    add_mapping(session, "role-analyst", "vigil-analysts", priority=100)
    role = resolve_role_for_groups(["vigil-analysts", "vigil-viewers"], session)
    assert role is not None and role.role_id == "role-viewer"


def test_a_mapping_to_a_missing_role_resolves_to_no_role(session):
    # The FK is enforced by Postgres; such a row could only exist there
    # through drift (a role deleted outside the cascade). The contract is
    # deny-by-default: no fallback to the second-best mapping — a login that
    # cannot be resolved signs in with nothing.
    add_mapping(session, "role-gone", "ghost-group")
    assert resolve_role_for_groups(["ghost-group"], session) is None


def test_resolution_joins_the_mapping_table_not_the_argument(session):
    # Only rows in role_group_mappings count: a group that resembles nothing
    # and a mapping pointing the other way resolve to nothing.
    add_mapping(session, "role-analyst", "vigil-analysts")
    assert resolve_role_for_groups(["vigil-admins"], session) is None


# --- tool-call permission semantics --------------------------------------


def test_a_map_without_tool_keys_denies_tool_calls():
    assert role_allows_tool_call({"findings.read": True}, "crowdstrike") is False


def test_the_baseline_grant_allows_tool_calls():
    assert role_allows_tool_call({TOOL_EXECUTE_PERMISSION: True}, "crowdstrike")


def test_the_baseline_refusal_denies_tool_calls():
    assert (
        role_allows_tool_call({TOOL_EXECUTE_PERMISSION: False}, "crowdstrike") is False
    )


def test_a_server_override_wins_over_the_baseline():
    perms = {TOOL_EXECUTE_PERMISSION: False, tools_server_permission("vstrike"): True}
    assert role_allows_tool_call(perms, "vstrike") is True


def test_a_server_deny_wins_over_the_baseline():
    perms = {TOOL_EXECUTE_PERMISSION: True, tools_server_permission("vstrike"): False}
    assert role_allows_tool_call(perms, "vstrike") is False


def test_another_servers_override_does_not_leak():
    perms = {TOOL_EXECUTE_PERMISSION: False, tools_server_permission("other"): True}
    assert role_allows_tool_call(perms, "vstrike") is False


# --- mapping admin: the escalation guard behind the users.write gate ------


def test_an_admin_creates_a_mapping(session):
    payload = mapping_router.create_mapping(
        mapping_router.CreateMappingRequest(
            role_id="role-analyst", idp_group="vigil-analysts"
        ),
        current_user=admin_user(session),
        session=session,
    )
    assert payload["idp_group"] == "vigil-analysts"
    assert payload["role_id"] == "role-analyst"
    assert payload["priority"] == 100
    row = session.query(RoleGroupMapping).one()
    assert row.role_id == "role-analyst"


def test_creating_a_mapping_onto_an_unknown_role_is_a_bad_request(session):
    with pytest.raises(HTTPException) as exc:
        mapping_router.create_mapping(
            mapping_router.CreateMappingRequest(role_id="role-nope", idp_group="g"),
            current_user=admin_user(session),
            session=session,
        )
    assert exc.value.status_code == 400


def test_the_escalation_guard_fires_on_a_self_mapping_attempt(session):
    # An analyst with users.write may not map their own directory group onto
    # a role carrying more permissions than they hold.
    with pytest.raises(HTTPException) as exc:
        mapping_router.create_mapping(
            mapping_router.CreateMappingRequest(
                role_id="role-admin", idp_group="vigil-analysts"
            ),
            current_user=analyst_user(session),
            session=session,
        )
    assert exc.value.status_code == 403
    assert session.query(RoleGroupMapping).count() == 0


def test_the_guard_limits_who_may_keep_which_mapping_alive(session):
    # Updating a mapping onto a role the actor could not hold is the same
    # escalation through a different door.
    add_mapping(session, "role-viewer", "vigil-viewers")
    with pytest.raises(HTTPException) as exc:
        mapping_router.update_mapping(
            1,
            mapping_router.UpdateMappingRequest(role_id="role-admin"),
            current_user=analyst_user(session),
            session=session,
        )
    assert exc.value.status_code == 403
    row = session.query(RoleGroupMapping).one()
    assert row.role_id == "role-viewer"


def test_a_duplicate_group_role_pair_conflicts(session):
    add_mapping(session, "role-analyst", "vigil-analysts")
    with pytest.raises(HTTPException) as exc:
        mapping_router.create_mapping(
            mapping_router.CreateMappingRequest(
                role_id="role-analyst", idp_group="vigil-analysts"
            ),
            current_user=admin_user(session),
            session=session,
        )
    assert exc.value.status_code == 409


def test_updates_change_the_mapped_fields(session):
    add_mapping(session, "role-viewer", "vigil-viewers", priority=10)
    payload = mapping_router.update_mapping(
        1,
        mapping_router.UpdateMappingRequest(priority=500),
        current_user=admin_user(session),
        session=session,
    )
    assert payload["priority"] == 500
    assert payload["role_id"] == "role-viewer"


def test_listing_orders_by_priority_descending(session):
    add_mapping(session, "role-viewer", "vigil-viewers", priority=10)
    add_mapping(session, "role-admin", "vigil-admins", priority=90)
    payload = mapping_router.list_mappings(session)
    assert [m["idp_group"] for m in payload["mappings"]] == [
        "vigil-admins",
        "vigil-viewers",
    ]


def test_deleting_a_mapping_removes_only_that_row(session):
    add_mapping(session, "role-viewer", "vigil-viewers")
    add_mapping(session, "role-analyst", "vigil-analysts")
    mapping_router.delete_mapping(1, current_user=admin_user(session), session=session)
    remaining = session.query(RoleGroupMapping).one()
    assert remaining.idp_group == "vigil-analysts"


def test_deleting_a_missing_mapping_is_a_not_found(session):
    with pytest.raises(HTTPException) as exc:
        mapping_router.delete_mapping(
            99, current_user=admin_user(session), session=session
        )
    assert exc.value.status_code == 404
