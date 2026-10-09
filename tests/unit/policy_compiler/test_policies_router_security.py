"""Security posture of the console policies router, against the real app.

Two gates:

1. **401 unauthenticated on EVERY route.** The sweep enumerates routes from
   the router object itself, so it cannot drift from the code: a new route is
   swept the day it exists. This extends the deny-by-default inventory gate
   (``tests/security/test_route_auth_coverage.py``) and the named-route sweep
   (``tests/security/test_unauth_endpoints.py``, whose ``PROTECTED_ROUTES``
   list also names this router's paths explicitly).
2. **Console-only placement.** The frozen ``/api/v1`` contract — both the
   committed snapshot and the live app's v1 subset — never serves compiled
   policies (locked decision 6: the lifecycle is console-side governance, not
   an external API promise).

The module-scoped app fixture and the DEV_MODE forcing follow
``test_unauth_endpoints.py``: authentication must be genuinely on, not the
dev-mode bypass that would silently no-op the whole sweep.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from core.auth import current_user as current_user_module
from core.config import get_settings
from core.policy_compiler.policies_router import ROUTER_META
from core.policy_compiler.policies_router import router as policies_router
from core.storage.connection import get_db_manager
from services.api import main as backend_main
from tests.unit.policy_compiler.fixtures.sample_ir import POLICY_ID

pytestmark = pytest.mark.unit

# 4 GET (list, inspect, decisions, export) + 4 POST (promote, suspend, rearm,
# retire). A route added without being swept means this count drifted.
EXPECTED_ROUTE_CASES = 8


@pytest.fixture(scope="module")
def app():
    """TestClient over the real app with auth force-enabled.

    Two places have to be forced, not one — see the fixture of the same
    shape in test_unauth_endpoints.py: ``core.auth.current_user`` captures
    ``DEV_MODE`` at import, while other routers read ``get_settings()``
    live, and conftest's autouse cache-clear discards a patched instance
    before the request runs. Hence attribute + environment.

    The client is deliberately NOT used as a context manager: entering one
    runs the app's lifespan, whose startup treats an uninitialized schema as
    fatal — a live-Postgres dependency this sweep must not have. Auth
    gating lives in route dependencies, not lifespan. But the auth
    dependency itself (``get_current_user``) takes a request-scoped session
    via ``UnitOfWorkSession``, so the session factory must exist — built
    here with ``db_manager.initialize()``, which only creates the (lazy)
    engine, no connection and no ``create_all``. An unauthenticated
    request is refused with 401 before the first query is ever executed.
    """
    prev = current_user_module.DEV_MODE
    current_user_module.DEV_MODE = False
    saved = {
        key: os.environ.get(key)
        for key in ("DEV_MODE", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_PASSWORD")
    }
    os.environ["DEV_MODE"] = "false"
    # Same pins conftest's autouse ``_no_ambient_postgres`` applies around
    # every test — but that fixture is function-scoped and this one is
    # module-scoped, so it builds the engine before those pins exist and
    # pins the same values itself.
    os.environ["POSTGRES_HOST"] = "postgres-blocked-in-unit-tests.invalid"
    os.environ["POSTGRES_PORT"] = "1"
    os.environ["POSTGRES_PASSWORD"] = "blocked-in-unit-tests"
    get_settings.cache_clear()
    db_manager = get_db_manager()
    db_manager.initialize()
    try:
        yield TestClient(backend_main.app)
    finally:
        current_user_module.DEV_MODE = prev
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        if db_manager._engine is not None:
            db_manager._engine.dispose()


def _sweep_cases() -> list[tuple[str, str, dict | None]]:
    """(method, url, body) for every route the router defines."""
    cases: list[tuple[str, str, dict | None]] = []
    for route in policies_router.routes:
        path = ROUTER_META.prefix + route.path
        body = {"version": 1} if "POST" in route.methods else None
        for method in sorted(route.methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            url = path.replace("{policy_id}", POLICY_ID)
            if path.endswith("/export"):
                url += "?format=rego"  # auth must fail before validation does
            cases.append((method, url, body))
    return cases


def test_the_sweep_is_generated_from_the_router():
    assert len(_sweep_cases()) == EXPECTED_ROUTE_CASES
    assert {method for method, _, _ in _sweep_cases()} == {"GET", "POST"}


@pytest.mark.parametrize("method,url,body", _sweep_cases())
def test_unauthenticated_request_is_401_on_every_route(app, method, url, body):
    response = app.request(method, url, json=body)
    assert response.status_code == 401, (
        f"{method} {url} returned {response.status_code} (expected 401): "
        f"{response.text[:200]}"
    )


def test_discovery_mounted_the_router(app):
    """The real app actually serves these paths (not just a standalone app).

    Read from the OpenAPI schema rather than walking ``app.routes``: mounted
    routers are reachable in the schema (and over the wire — the 401 sweep
    proves it) but not all show up in a naive ``app.routes`` path scan.
    """
    paths = backend_main.app.openapi()["paths"]
    mounted = [p for p in paths if p.startswith(ROUTER_META.prefix)]
    assert mounted, "discovery did not mount the compiled-policies router"


def test_no_v1_route_serves_compiled_policies(app):
    from scripts.generate_api_v1_contract import build_contract

    contract = build_contract(backend_main.app)
    assert "compiled-policies" not in json.dumps(contract)
