"""The edge fleet has no public contract: mounted, but schema-invisible.

The frozen ``/api/v1`` snapshot is what external callers are handed, and the
edge sync surface is deliberately machine-internal (per-node credentials, no
console caller). These tests pin both facts: every ``/internal/edge/*`` route
is mounted and routable in the real app, and none of them — nor anything
about them — appears in the OpenAPI schema or the frozen contract snapshot.

FastAPI ≥0.141 represents an included router as a single ``_IncludedRouter``
route rather than flattening its children into ``app.routes`` (each keeps its
own ``.path``), so "is it mounted" is answered by walking the tree the same
way the router walks it — not by grepping top-level paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

pytestmark = pytest.mark.unit

SNAPSHOT = Path(__file__).resolve().parents[3] / "core/api/v1/contract.snapshot.json"


def _mounted_paths(routes: list, prefix: str = "") -> Iterator[str]:
    """Every routable path in the app, through nested included routers."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:  # fastapi >=0.141 _IncludedRouter wrapper
            context = route.include_context
            yield from _mounted_paths(inner.routes, prefix + context.prefix)
            continue
        path = getattr(route, "path", None)
        if path is not None:
            yield prefix + path


@pytest.fixture(scope="module")
def app_and_schema():
    from services.api.main import app

    return app, app.openapi()


def test_edge_routes_are_mounted(app_and_schema):
    app, _ = app_and_schema
    mounted = set(_mounted_paths(list(app.routes)))
    assert {
        "/internal/edge/enroll",
        "/internal/edge/{node_id}/policy",
        "/internal/edge/{node_id}/events",
        "/internal/edge/{node_id}/heartbeat",
        "/internal/edge/nodes/{node_id}/revoke",
    } <= mounted


def test_no_edge_route_appears_in_the_openapi_schema(app_and_schema):
    _, schema = app_and_schema
    offenders = [p for p in schema.get("paths", {}) if "/internal/edge" in p]
    assert offenders == [], "edge routes must stay out of the public schema"


def test_frozen_v1_contract_has_no_edge_paths():
    snapshot = json.loads(SNAPSHOT.read_text())["paths"]
    offenders = [p for p in snapshot if "/internal/edge" in p]
    assert offenders == [], "the frozen /api/v1 contract must not gain edge paths"
