"""Each state-changing route demands the role permission that matches its effect.

``Auth.REQUIRED`` only proves a login: the seeded Viewer is read-only, and the
Analyst may not change settings or release response actions. A request from a
user who holds nothing must be refused with the permission named, before the
handler (and so before any database or integration) is reached.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")

from core.storage.models import User  # noqa: E402
from services.api import main as backend_main  # noqa: E402
from services.api.middleware import auth as auth_module  # noqa: E402

pytestmark = pytest.mark.unit

RUN_ID = "9c1c2d3e-0000-4000-8000-000000000592"

# (method, path, body, permission the route must ask for)
GATED_ROUTES = [
    ("POST", "/api/config/postgresql", {"connection_string": "x"}, "settings.write"),
    ("POST", "/api/config/github", {"token": "x"}, "settings.write"),
    ("POST", "/api/config/claude", {"api_key": "x"}, "settings.write"),
    ("POST", "/api/config/secrets/reinit", {}, "settings.write"),
    ("POST", "/api/config/secrets/migrate-to-encrypted", None, "settings.write"),
    ("POST", "/api/config/force-manual-approval", {"enabled": True}, "settings.write"),
    ("POST", "/api/config/integrations", {"integrations": {}}, "integrations.write"),
    ("POST", "/api/config/darktrace", {}, "integrations.write"),
    ("POST", "/api/orchestrator/enable", None, "settings.write"),
    ("POST", "/api/orchestrator/disable", None, "settings.write"),
    ("POST", "/api/orchestrator/kill", None, "settings.write"),
    ("POST", "/api/orchestrator/investigations/purge", None, "settings.write"),
    ("DELETE", "/api/findings/all", None, "findings.delete"),
    ("PUT", "/api/analytics/budget", {}, "settings.write"),
    ("POST", "/api/v1/cases", {"title": "t"}, "cases.write"),
    ("PATCH", "/api/v1/cases/c-1", {"status": "closed"}, "cases.write"),
    ("POST", "/api/v1/cases/c-1/close", {}, "cases.write"),
    ("POST", "/api/v1/cases/c-1/merge", {"source_case_id": "c-2"}, "cases.write"),
    ("POST", "/api/cases", {"title": "t"}, "cases.write"),
    ("POST", "/api/cases/c-1/comments", {"content": "x"}, "cases.write"),
    ("DELETE", "/api/cases/c-1", None, "cases.delete"),
    ("PATCH", "/api/v1/findings/f-1", {"severity": "low"}, "findings.write"),
    ("POST", "/api/v1/approvals/a-1/approve", {}, "ai_decisions.approve"),
    ("POST", "/api/v1/approvals/a-1/reject", {"reason": "no"}, "ai_decisions.approve"),
    ("POST", "/api/workflows/runs/r-1/resume", {}, "ai_decisions.approve"),
    (
        "POST",
        "/api/workflows/runs/r-1/cancel",
        {"reason": "no"},
        "ai_decisions.approve",
    ),
    (
        "POST",
        "/api/v1/agent-runs",
        {"run_kind": "hunt", "playbook": "p", "config": "c"},
        "ai_chat.use",
    ),
    (
        "POST",
        f"/api/v1/agent-runs/{RUN_ID}/directives",
        {"kind": "note", "text": "x"},
        "ai_chat.use",
    ),
    ("POST", "/api/workflows/w-1/execute", {}, "ai_chat.use"),
    ("POST", "/api/claude/chat/stream", {"messages": []}, "ai_chat.use"),
    # --- Route-coverage sweep: the eight formerly authn-only routers --------
    # conversations — chat-surface data, ai_chat.use end to end.
    ("GET", "/api/conversations/", None, "ai_chat.use"),
    ("PATCH", "/api/conversations/{conversation_id}", {"title": "t"}, "ai_chat.use"),
    ("DELETE", "/api/conversations/{conversation_id}", None, "ai_chat.use"),
    ("POST", "/api/conversations/import", None, "ai_chat.use"),
    # detection rules — detections.read on reads, detections.write on writes.
    ("GET", "/api/detection-rules/sources", None, "detections.read"),
    ("GET", "/api/detection-rules/sources/{source_id}", None, "detections.read"),
    ("GET", "/api/detection-rules/stats", None, "detections.read"),
    ("GET", "/api/detection-rules/mcp-env", None, "detections.read"),
    ("POST", "/api/detection-rules/sources", {}, "detections.write"),
    ("DELETE", "/api/detection-rules/sources/{source_id}", None, "detections.write"),
    (
        "POST",
        "/api/detection-rules/sources/{source_id}/update",
        None,
        "detections.write",
    ),
    ("POST", "/api/detection-rules/update-all", None, "detections.write"),
    ("POST", "/api/detection-rules/reload", None, "detections.write"),
    # agents — the chat cast: reads ask ai_chat.use, the global toggle
    # (which changes what every chat offers) asks settings.write.
    ("GET", "/api/agents/agents", None, "ai_chat.use"),
    ("GET", "/api/agents/agents/{agent_id}", None, "ai_chat.use"),
    (
        "PUT",
        "/api/agents/agents/{agent_id}/enabled",
        {"enabled": False},
        "settings.write",
    ),
    # overview / triage / timeline — findings surfaces, findings.read.
    ("GET", "/api/overview", None, "findings.read"),
    ("GET", "/api/overview/alerts/{finding_id}", None, "findings.read"),
    ("GET", "/api/triage", None, "findings.read"),
    ("GET", "/api/timeline/range", None, "findings.read"),
    ("GET", "/api/timeline/case/{case_id}", None, "findings.read"),
    ("GET", "/api/timeline/finding/{finding_id}/context", None, "findings.read"),
    ("GET", "/api/timeline/cluster/{cluster_id}", None, "findings.read"),
    # analytics — each route asks the permission its effect implies.
    ("GET", "/api/analytics", None, "findings.read"),
    ("GET", "/api/analytics/insights", None, "findings.read"),
    ("POST", "/api/analytics/insights/refresh", None, "ai_chat.use"),
    ("GET", "/api/analytics/cost", None, "settings.read"),
    ("POST", "/api/analytics/estimate-cost", {}, "ai_chat.use"),
    ("POST", "/api/analytics/recalculate-cost", None, "settings.write"),
    # ingestion — findings.read for the job pipeline, findings.write for
    # actions that create findings; the S3 picker rides with the writes.
    ("GET", "/api/ingest/jobs", None, "findings.read"),
    ("GET", "/api/ingest/jobs/{job_id}", None, "findings.read"),
    ("GET", "/api/ingest/formats", None, "findings.read"),
    ("GET", "/api/ingest/csv-template/{data_type}", None, "findings.read"),
    ("POST", "/api/ingest/upload", None, "findings.write"),
    ("POST", "/api/ingest/ingest-string", None, "findings.write"),
    ("POST", "/api/ingest/sync-s3-folder", None, "findings.write"),
    ("GET", "/api/ingest/s3-files", None, "findings.write"),
    ("POST", "/api/ingest/s3-file", {"key": "k"}, "findings.write"),
    # users — inline handler checks migrated to declarative gates (the
    # self-profile view on GET /{user_id} keeps its conditional handler check:
    # a profile is always viewable to itself, and being in-handler it cannot
    # appear here as a static row).
    ("GET", "/api/users/", None, "users.read"),
    ("POST", "/api/users/", {}, "users.write"),
    ("PUT", "/api/users/{user_id}", {}, "users.write"),
    ("DELETE", "/api/users/{user_id}", None, "users.delete"),
    ("PUT", "/api/users/{user_id}/role", {"role_id": "role-viewer"}, "users.write"),
    ("PUT", "/api/users/{user_id}/roles", {"role_ids": ["role-viewer"]}, "users.write"),
    ("GET", "/api/users/roles/list", None, "users.read"),
    # llm providers — writes behind settings.write; reads stay open, like the
    # config router's documented reads-open posture.
    ("POST", "/api/llm/providers", {}, "settings.write"),
    ("PUT", "/api/llm/providers/{provider_id}", {}, "settings.write"),
    ("DELETE", "/api/llm/providers/{provider_id}", None, "settings.write"),
    ("POST", "/api/llm/providers/{provider_id}/set-default", None, "settings.write"),
    ("POST", "/api/llm/providers/{provider_id}/test", None, "settings.write"),
    ("POST", "/api/llm/providers/discover-models", {}, "settings.write"),
    ("POST", "/api/llm/providers/test-connection", {}, "settings.write"),
    (
        "POST",
        "/api/llm/providers/{provider_id}/refresh-models",
        None,
        "settings.write",
    ),
    ("POST", "/api/llm/providers/refresh-models", None, "settings.write"),
    # bifrost — the whole router sits behind settings.write.
    ("GET", "/api/bifrost/routability", None, "settings.write"),
    ("POST", "/api/bifrost/status", None, "settings.write"),
    # jira export — cases.read, the right the case routes themselves ask.
    ("POST", "/api/cases/{case_id}/export/jira", {}, "cases.read"),
    ("POST", "/api/cases/{case_id}/remediation/jira", {}, "cases.read"),
]


@pytest.mark.parametrize("method,path,body,permission", GATED_ROUTES)
def test_a_route_refuses_a_user_who_lacks_its_permission(
    method, path, body, permission, monkeypatch
):
    viewer = User(
        user_id="viewer",
        username="vera_viewer",
        email="v@test.local",
        password_hash="",
        role_id="role-viewer",
        is_active=True,
        mfa_enabled=False,
    )

    # Holds everything except the one permission under test.
    def _check(user_id, perm, session=None):
        return perm != permission

    monkeypatch.setattr("core.auth.auth_service.AuthService.check_permission", _check)
    app = backend_main.app
    app.dependency_overrides[auth_module.get_current_active_user] = lambda: viewer
    app.dependency_overrides[auth_module.get_current_user] = lambda: viewer
    try:
        response = TestClient(app).request(method, path, json=body)
    finally:
        app.dependency_overrides.pop(auth_module.get_current_active_user, None)
        app.dependency_overrides.pop(auth_module.get_current_user, None)

    assert response.status_code == 403, (method, path, response.text[:200])


def test_every_config_write_asks_for_a_permission():
    """A new POST on /api/config cannot be added without a gate."""
    from services.api.routers.config import router

    def gated(route) -> bool:
        return any(
            getattr(dep.call, "__qualname__", "").startswith("require_permission.")
            for dep in route.dependant.dependencies
        )

    # The integration test route checks inside its handler.
    handler_checked = {"/integrations/{integration_id}/test"}
    ungated = [
        route.path
        for route in router.routes
        if route.methods - {"GET", "HEAD", "OPTIONS"}
        and route.path not in handler_checked
        and not gated(route)
    ]
    assert ungated == []


# --- Every write route makes a permission decision --------------------------

AUTH_ONLY_ROUTES = Path(__file__).with_name("auth_only_write_routes.txt")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Calls a handler makes when it checks the role itself rather than via Depends.
_INLINE_GUARDS = (
    "require_settings_admin",
    "require_integrations_admin",
    "_require_permission",
    "check_permission",
    "username_has_permission",
    "require_permission",
)


def _dependencies(dependant):
    for dep in dependant.dependencies:
        yield dep
        yield from _dependencies(dep)


def _write_routes_without_a_guard() -> set[str]:
    """``METHOD path`` for each state-changing /api route with no visible guard."""
    app = backend_main.app
    found: set[str] = set()

    def visit(obj) -> None:
        # Lazy included-router entries on FastAPI >= 0.137; see test_route_auth_coverage.
        if type(obj).__name__ == "_IncludedRouter":
            for candidate in obj.effective_candidates():
                visit(candidate)
            return
        path = getattr(obj, "path", None)
        writes = set(getattr(obj, "methods", None) or ()) - _SAFE_METHODS
        if not isinstance(path, str) or not path.startswith("/api/") or not writes:
            return
        if any(
            getattr(dep.call, "__qualname__", "").startswith("require_permission.")
            for dep in _dependencies(obj.dependant)
        ):
            return
        try:
            source = inspect.getsource(obj.endpoint)
        except (OSError, TypeError):
            source = ""
        if any(guard in source for guard in _INLINE_GUARDS):
            return
        for method in writes:
            found.add(f"{method} {getattr(obj, 'path_format', None) or path}")

    for route in app.routes:
        visit(route)
    return found


# --- The swept routers: every route asks for a permission -------------------

SWEPT_ROUTERS = (
    "conversations",
    "detection_rules",
    "agents",
    "overview",
    "triage",
    "timeline",
    "analytics",
    "ingestion",
)


def _has_permission_gate(dependencies) -> bool:
    """True if any dependency is a ``permission_gate`` — accepts both the
    ``Depends`` objects routers and routes carry (``.dependency``) and the
    resolved ``Dependant`` objects the route tree carries (``.call``)."""
    for dep in dependencies:
        fn = getattr(dep, "dependency", None) or getattr(dep, "call", None)
        if getattr(fn, "__qualname__", "").startswith("require_permission."):
            return True
    return False


def test_every_route_on_the_swept_routers_declares_a_permission():
    """Route-coverage sweep ratchet: no route on the eight routers this
    refactor swept may exist without a permission gate — a router-level gate
    covers every route on it, and a router listed here without one fails.

    A new route on a gated router inherits the gate automatically; a new
    router that wants to stay authn-only must simply not be listed here.
    """
    import importlib

    ungated = []
    for name in SWEPT_ROUTERS:
        module = importlib.import_module(f"services.api.routers.{name}")
        router = module.router
        router_gated = _has_permission_gate(router.dependencies)
        if router_gated:
            continue
        for route in router.routes:
            if not _has_permission_gate(getattr(route, "dependencies", [])):
                methods = sorted(getattr(route, "methods", ()) or ())
                ungated.append(f"{name}: {'/'.join(methods)} {route.path}")

    assert ungated == [], (
        "Routers swept by the route-coverage work must gate every route "
        "(router-level or per-route):\n  - " + "\n  - ".join(ungated)
    )


def test_a_write_route_without_a_permission_guard_is_on_the_reviewed_list():
    """A new write route must ask for a permission or be listed as auth-only.

    ``test_route_auth_coverage`` proves a login; this proves someone decided what
    the login's role may do. The list is the set of routes that had no visible
    guard when this test was added (some check inside a helper the handler calls,
    some are login-only on purpose). Adding a line is a decision to review.
    """
    listed = {
        line.strip()
        for line in AUTH_ONLY_ROUTES.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    unguarded = _write_routes_without_a_guard()

    assert not unguarded - listed, (
        "Write routes with no permission guard and not in "
        f"{AUTH_ONLY_ROUTES.name}; add a permission_gate(...) or list them:\n  - "
        + "\n  - ".join(sorted(unguarded - listed))
    )
    assert not listed - unguarded, (
        f"{AUTH_ONLY_ROUTES.name} lists routes that are now guarded or gone; "
        "remove them:\n  - " + "\n  - ".join(sorted(listed - unguarded))
    )
