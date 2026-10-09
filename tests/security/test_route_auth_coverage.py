"""Route inventory: every /api/* route must require auth or be on the
explicit public allowlist.

Locks in the deny-by-default contract introduced after the 2026-05
security disclosure. If you add a new router or route without auth,
this test fails — and the fix is either to add ``dependencies=AUTH_DEPENDENCY``
to the include_router call (or ``Depends(get_current_active_user)`` to
the handler) or, if the route is intentionally public, to add it to
``PUBLIC_API_PATHS`` in ``services/api/main.py``.

Adding a route to ``PUBLIC_API_PATHS`` is a security decision, not a way
to make this test quiet. A feature-flagged inbound webhook receiver that
shows up here because it was mounted unconditionally must be fixed by
restoring the flag, not by allowlisting the path.

Traversal note (issue #532): FastAPI >= 0.137 no longer flattens child
routes into ``app.routes``. It stores lazy ``_IncludedRouter`` entries,
which have no ``.path`` attribute, so the ``for route in app.routes``
loop this test used to run examined 1 route out of 357 — ``/api/health``,
already on the allowlist — and passed unconditionally. Because
``requirements.txt`` had no upper bound on ``fastapi``, a transitive
upgrade disarmed the gate with no visible signal.
``_collect_api_routes`` walks both table shapes, and
``test_route_inventory_reaches_every_documented_path`` fails if the walk
ever goes stale against a future version.
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

# Importing services.api.main pulls in auth_service, which refuses to load
# without a JWT secret once DEV_MODE is false — the default anywhere
# without a .env, CI included. Set it here so this file stands alone; it
# previously only worked because test_unauth_endpoints.py happens to call
# os.environ.setdefault at collection time.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")

pytestmark = pytest.mark.unit


def _is_public(path: str, public_patterns) -> bool:
    """Match ``path`` against the public allowlist (supports ``*`` wildcards)."""
    for pat in public_patterns:
        if pat == path:
            return True
        if fnmatch.fnmatch(path, pat):
            return True
    return False


def _walk_dependants(dependant, auth_deps) -> bool:
    """Recursively check a dependant chain for an auth dependency."""
    if dependant is None:
        return False
    for dep in dependant.dependencies:
        if dep.call in auth_deps:
            return True
        if _walk_dependants(dep, auth_deps):
            return True
    return False


def _api_route_objects(app) -> "Iterator[tuple[Any, str]]":
    """Yield ``(route_object, path)`` for every effective /api/ route.

    Shared by the inventory below and the edge guard classification: under
    modern FastAPI the real ``APIRoute`` objects hide inside lazy
    ``_IncludedRouter`` entries, so any naive ``app.routes`` loop sees nothing
    (issue #532). The path is yielded alongside because its str-ness is
    verified here and is not re-derivable from the object's type.
    """

    def visit(obj):
        # Compared by name rather than imported: the class is private and
        # absent on older FastAPI, where an import would break collection.
        if type(obj).__name__ == "_IncludedRouter":
            for candidate in obj.effective_candidates():  # a method, not a list
                yield from visit(candidate)
            return

        path = getattr(obj, "path", None)
        if isinstance(path, str) and path.startswith("/api/"):
            yield obj, path

    for route in app.routes:
        yield from visit(route)


def _collect_api_routes(app, auth_deps) -> list[tuple[str, str, bool]]:
    """Return ``(path, method_label, has_auth)`` for every effective /api/ route.

    Handles both route-table shapes: modern FastAPI, where ``app.routes``
    holds lazy ``_IncludedRouter`` entries whose ``effective_candidates()``
    yields per-route contexts (and, where a router includes another router,
    further ``_IncludedRouter`` entries — hence the recursion); and older
    FastAPI, which flattens child routes into ``app.routes`` directly.

    Either way the object carrying ``.path`` also carries a ``.dependant``
    with mount-site ``dependencies=`` already folded in, so router-level and
    route-level auth are both visible from one chain walk.
    """
    collected: list[tuple[str, str, bool]] = []

    for obj, path in _api_route_objects(app):
        methods = getattr(obj, "methods", None)
        collected.append(
            (
                # path_format renders convertors the way OpenAPI documents
                # them: /api/f/{name:path} -> /api/f/{name}.
                getattr(obj, "path_format", None) or path,
                "/".join(sorted(methods)) if methods else type(obj).__name__,
                _walk_dependants(getattr(obj, "dependant", None), auth_deps),
            )
        )

    return collected


def _auth_deps():
    from services.api.middleware.auth import get_current_active_user, get_current_user

    # Router-managed edge guards are authentication dependencies too: the
    # generic inventory must recognize them or every edge route reads as
    # unauthenticated. test_edge_routes_carry_their_declared_guard pins WHICH
    # route carries WHICH guard.
    from services.api.routers.edge import require_edge_node, require_enrollment_token

    return {
        get_current_active_user,
        get_current_user,
        require_edge_node,
        require_enrollment_token,
    }


def test_every_api_route_requires_auth_or_is_explicitly_public():
    # Import lazily so a broken main.py shows as a test failure rather
    # than a collection error.
    from services.api.main import PUBLIC_API_PATHS, app

    missing = {
        f"{method} {path}"
        for path, method, has_auth in _collect_api_routes(app, _auth_deps())
        if not has_auth and not _is_public(path, PUBLIC_API_PATHS)
    }

    assert (
        not missing
    ), "Routes without auth (and not on PUBLIC_API_PATHS):\n  - " + "\n  - ".join(
        sorted(missing)
    )


def test_route_inventory_reaches_every_documented_path():
    """Guard the guard: fail if the traversal stops reaching the route table.

    The failure this exists to catch is not "a route lost its auth" — it is
    "the check silently stopped checking". ``app.openapi()`` is public,
    stable API, so it is a self-calibrating oracle for what the walk above
    must reach: no threshold to rot as the API grows, and the next breaking
    FastAPI change lands as a red test instead of a silent green one.
    """
    from services.api.main import app

    documented = {p for p in app.openapi()["paths"] if p.startswith("/api/")}
    # Without this, an OpenAPI generation failure would make the comparison
    # below pass vacuously on two empty sets.
    assert documented, "app.openapi() reported no /api/ paths at all"

    reached = {path for path, _method, _auth in _collect_api_routes(app, _auth_deps())}

    # Subset, not equality: the walk also sees routes kept out of the schema
    # with include_in_schema=False.
    unreached = sorted(documented - reached)
    assert not unreached, (
        f"the route walk missed {len(unreached)} of {len(documented)} documented "
        f"/api/ paths, so it is no longer inspecting the real route table "
        f"(see issue #532). Fix the traversal — do not relax this assertion:\n  - "
        + "\n  - ".join(unreached)
    )


# ---------------------------------------------------------------------------
# Edge router (ROUTER_MANAGED): per-route guards, classified and proven
# ---------------------------------------------------------------------------

# (method, v1 path) -> guard the route must carry. The legacy mounts of the
# same handlers are checked with the same expectation (see the test below).
EDGE_ROUTE_POSTURES = {
    ("POST", "/api/v1/edge/enroll"): "enrollment-token",
    ("GET", "/api/v1/edge/nodes"): "operator",
    ("POST", "/api/v1/edge/nodes/{node_id}/revoke"): "operator",
    ("GET", "/api/v1/edge/policy"): "node-token",
    ("POST", "/api/v1/edge/journal"): "node-token",
}


def _dependant_calls(dependant) -> set:
    """Every dependency callable reachable from a route's dependant chain."""
    calls: set = set()
    if dependant is None:
        return calls
    for dep in dependant.dependencies:
        calls.add(dep.call)
        calls |= _dependant_calls(dep)
    return calls


def _edge_guard(app, path: str, method: str) -> str | None:
    """Classify one mounted route: which kind of auth does it carry?"""
    from services.api.middleware.auth import get_current_user
    from services.api.routers.edge import require_edge_node, require_enrollment_token

    for route, route_path in _api_route_objects(app):
        if (getattr(route, "path_format", None) or route_path) != path:
            continue
        if method not in (route.methods or set()):
            continue
        calls = _dependant_calls(getattr(route, "dependant", None))
        if require_enrollment_token in calls:
            return "enrollment-token"
        if require_edge_node in calls:
            return "node-token"
        if get_current_user in calls:  # permission gates chain it
            return "operator"
        return None
    return "missing"


@pytest.mark.parametrize(
    ("method", "v1_path"), sorted(EDGE_ROUTE_POSTURES), ids=lambda p: p
)
def test_edge_route_carries_its_declared_guard(app, method, v1_path):
    """Every edge route — versioned and legacy mount — carries exactly the
    guard the ROUTER_META reason declares."""
    assert _edge_guard(app, v1_path, method) == EDGE_ROUTE_POSTURES[(method, v1_path)]
    legacy_path = v1_path.replace("/api/v1/", "/api/", 1)
    assert (
        _edge_guard(app, legacy_path, method) == EDGE_ROUTE_POSTURES[(method, v1_path)]
    )


def test_edge_route_inventory_is_complete(app):
    """A new edge route added without a classification fails here.

    Guard the guard: the classification map above must meet the real route
    table, so an unauthenticated edge route cannot slip in unclassified.
    """
    mounted = set()
    for path, method, _auth in _collect_api_routes(app, _auth_deps()):
        if "/edge/" not in path:
            continue
        normalized = path.replace("/api/edge/", "/api/v1/edge/", 1)
        for method_label in method.split("/"):
            if method_label in ("GET", "POST"):
                mounted.add((method_label, normalized))
    assert mounted == set(EDGE_ROUTE_POSTURES)


@pytest.fixture()
def app():
    from services.api.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def refused_session_client():
    """TestClient whose unit-of-work session refuses every data operation.

    FastAPI solves the session dependency even when a guard refuses the
    request, so the override must be creatable — but any query/add/execute
    means a handler body ran without authenticating, and fails loudly.
    """

    class _NoDatabaseSession:
        def __getattr__(self, name):
            def _forbidden(*args, **kwargs):
                raise AssertionError(
                    f"route reached the database without authenticating (session.{name})"
                )

            return _forbidden

    from fastapi.testclient import TestClient

    from core.routing import request_unit_of_work
    from services.api.main import app

    app.dependency_overrides[request_unit_of_work] = _NoDatabaseSession
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(request_unit_of_work, None)


@pytest.mark.parametrize(
    "path",
    ["/api/v1/edge/policy", "/api/edge/policy"],
    ids=str,
)
def test_policy_fetch_refuses_missing_token(refused_session_client, path):
    response = refused_session_client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/v1/edge/journal", "/api/edge/journal"],
    ids=str,
)
def test_journal_push_refuses_missing_token(refused_session_client, path):
    # A fully valid push body: the 401 must come from the missing token, so
    # the assertion cannot be satisfied by a body-validation 422.
    body = {
        "node_id": "wn-7f3a",
        "policy_version": 42,
        "chain_head": "a" * 64,
        "records": [
            {
                "seq": 1,
                "ts": "2026-10-09T13:00:00Z",
                "mode": "AUTONOMOUS",
                "idempotency_key": "block_ip:198.51.100.7",
                "action_type": "block_ip",
                "target": "198.51.100.7",
                "decision_rule": "edge-001 met (slm 0.93 >= floor 0.90)",
                "execution": {"status": "executed", "executor": "nftables"},
                "prev_hash": "0" * 64,
            }
        ],
    }
    response = refused_session_client.post(path, json=body)
    assert response.status_code == 401


def test_enrollment_refuses_when_unconfigured(refused_session_client, monkeypatch):
    """No EDGE_ENROLLMENT_TOKEN -> 503, before anything else (fail-closed)."""
    monkeypatch.delenv("EDGE_ENROLLMENT_TOKEN", raising=False)
    response = refused_session_client.post("/api/v1/edge/enroll", json={})
    assert response.status_code == 503


def test_enrollment_refuses_missing_bearer(refused_session_client, monkeypatch):
    """Configured secret, no presented token -> 401."""
    monkeypatch.setenv("EDGE_ENROLLMENT_TOKEN", "test-only-enrollment-secret")
    response = refused_session_client.post("/api/v1/edge/enroll", json={})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/v1/edge/nodes", "/api/edge/nodes"],
    ids=str,
)
def test_node_administration_refuses_anonymous_callers(refused_session_client, path):
    """No session -> 401 from the console auth chain, never a node listing."""
    response = refused_session_client.get(path)
    assert response.status_code == 401
