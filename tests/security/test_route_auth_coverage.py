"""Route inventory for the surfaces the backend serves itself.

Three contracts, one walk:

* every ``/api/*`` route must require auth or be on the explicit public
  allowlist;
* every ``/internal/*`` route must come from a discovered router declaring
  ``Auth.ROUTER_MANAGED`` — that surface's auth runs inside the handlers,
  which a dependency walk cannot see (see the test below);
* the ``/mcp`` mount must be visible to this suite at all (E14: the walk
  used to filter to ``/api/``, so the security suite could not see the MCP
  surface it is guarding).

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
``_collect_routes`` walks both table shapes, and
``test_route_inventory_reaches_every_documented_path`` fails if the walk
ever goes stale against a future version.
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path

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


def _collect_routes(app, auth_deps) -> list[tuple[str, str, bool]]:
    """Return ``(path, method_label, has_auth)`` for every effective /api/ and
    /internal/ route.

    Handles both route-table shapes: modern FastAPI, where ``app.routes``
    holds lazy ``_IncludedRouter`` entries whose ``effective_candidates()``
    yields per-route contexts (and, where a router includes another router,
    further ``_IncludedRouter`` entries — hence the recursion); and older
    FastAPI, which flattens child routes into ``app.routes`` directly.

    Either way the object carrying ``.path`` also carries a ``.dependant``
    with mount-site ``dependencies=`` already folded in, so router-level and
    route-level auth are both visible from one chain walk.

    The /mcp surface is deliberately not collected here: it is a Starlette
    ``Mount`` — no ``.dependant``, no ``.methods`` — so a dependency walk can
    say nothing about it. ``test_mcp_mount_is_visible_to_the_suite`` pins it
    in the only terms a mount can be pinned in, and the four behaviors the
    surface must answer with live in ``test_mcp_surface.py``.
    """
    collected: list[tuple[str, str, bool]] = []

    def visit(obj) -> None:
        # Compared by name rather than imported: the class is private and
        # absent on older FastAPI, where an import would break collection.
        if type(obj).__name__ == "_IncludedRouter":
            for candidate in obj.effective_candidates():  # a method, not a list
                visit(candidate)
            return

        path = getattr(obj, "path", None)
        if not isinstance(path, str) or not path.startswith(("/api/", "/internal/")):
            return

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

    for route in app.routes:
        visit(route)

    return collected


def _auth_deps():
    from services.api.middleware.auth import get_current_active_user, get_current_user

    return {get_current_active_user, get_current_user}


def test_every_api_route_requires_auth_or_is_explicitly_public():
    # Import lazily so a broken main.py shows as a test failure rather
    # than a collection error.
    from services.api.main import PUBLIC_API_PATHS, app

    missing = {
        f"{method} {path}"
        for path, method, has_auth in _collect_routes(app, _auth_deps())
        if path.startswith("/api/")
        and not has_auth
        and not _is_public(path, PUBLIC_API_PATHS)
    }

    assert (
        not missing
    ), "Routes without auth (and not on PUBLIC_API_PATHS):\n  - " + "\n  - ".join(
        sorted(missing)
    )


def test_every_internal_route_is_declared_router_managed():
    """Every /internal route comes from a discovered router that declares
    ``Auth.ROUTER_MANAGED`` — the posture whose metadata says why auth is
    in-handler.

    The dependant walk above cannot see ``authorise()``: it runs inside each
    endpoint body, not as a dependency, so ``has_auth`` is False for every
    /internal route by design. What the inventory pins instead is the
    declaration. A hand-attached ``@app.post("/internal/...")`` in main.py —
    the hole this test exists for — has no discovered router behind it, and
    fails here instead of serving quietly.
    """
    from core.routing import Auth
    from services.api.discovery import load_router_specs
    from services.api.main import app

    managed_prefixes = {
        prefix
        for _name, _module, meta in load_router_specs()
        if meta.auth is Auth.ROUTER_MANAGED
        for prefix in (meta.prefix, *meta.legacy_prefixes)
    }

    internal_routes = [
        (path, method)
        for path, method, _auth in _collect_routes(app, _auth_deps())
        if path.startswith("/internal/")
    ]
    assert internal_routes, (
        "No /internal routes in the route table. Either the agent layer's "
        "routers stopped mounting — a regression to chase — or the walk went "
        "blind again (see the FastAPI #532 note in the module docstring)."
    )

    # Segment-boundary match: a prefix /internal/tools must not bless a
    # sibling like /internal/tools-admin mounted outside discovery.
    undeclared = sorted(
        f"{method} {path}"
        for path, method in internal_routes
        if not any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in managed_prefixes
        )
    )
    assert not undeclared, (
        "/internal routes mounted outside a discovered ROUTER_MANAGED router, "
        "where no declared auth posture covers them — mount them through "
        "discovery with ROUTER_META, not by hand:\n  - " + "\n  - ".join(undeclared)
    )


def test_mcp_mount_is_visible_to_the_suite():
    """E14, the mount half: a Starlette ``Mount`` has no dependant and no
    methods, so no dependency walk can pin it. The inventory pins presence —
    at the address the app advertises, with the credential gate behind it;
    the four answers the surface must give are ``test_mcp_surface.py``'s
    job."""
    from core.config import get_settings
    from services.api.main import app
    from services.api.mcp_surface import MOUNT_PATH, McpSurfaceGate

    address = f"{get_settings().vigil_context_path.rstrip('/')}{MOUNT_PATH}"
    mounts = [
        route
        for route in app.routes
        if type(route).__name__ == "Mount" and getattr(route, "path", None) == address
    ]
    assert len(mounts) == 1, (
        f"Expected exactly one Mount at {address}, found {len(mounts)}. The "
        "MCP surface is unmounted, moved, or mounted twice — all three "
        "answers change who can reach Vigil's tools and none may happen "
        "quietly."
    )
    assert isinstance(mounts[0].app, McpSurfaceGate), (
        "The /mcp mount does not point at McpSurfaceGate — the MCP server is "
        "served there without the credential check that refuses every "
        "request without one."
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

    documented = {
        p for p in app.openapi()["paths"] if p.startswith(("/api/", "/internal/"))
    }
    # Without this, an OpenAPI generation failure would make the comparison
    # below pass vacuously on two empty sets.
    assert documented, "app.openapi() reported no /api/ or /internal/ paths at all"

    reached = {path for path, _method, _auth in _collect_routes(app, _auth_deps())}

    # Subset, not equality: the walk also sees routes kept out of the schema
    # with include_in_schema=False.
    unreached = sorted(documented - reached)
    assert not unreached, (
        f"the route walk missed {len(unreached)} of {len(documented)} documented "
        f"/api/ and /internal/ paths, so it is no longer inspecting the real "
        f"route table (see issue #532). Fix the traversal — do not relax this "
        f"assertion:\n  - " + "\n  - ".join(unreached)
    )
