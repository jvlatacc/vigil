"""The containment lease surface answers 401 without a credential, and
it never learns a mutation verb.

A lease list is operator telemetry — who is contained, since when, under
what rule — so it is credential-gated like every other response-domain
read. And v1's surface is GET-only by construction: rollback runs in the
daemon and the agent tools, both demotions, and anything stronger goes
through the approvals queue. The route-table check below pins that — a
mutation verb cannot appear here without this test naming it.

Runs against the real FastAPI app from ``services.api.main`` with
``DEV_MODE=false`` forced, same shape as test_unauth_endpoints.py (see
that file's docstring for why both the module attribute and the cached
settings have to be forced).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

# Pre-import at collection time so ``sys.modules`` is locked in before
# anything else runs.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")
from fastapi.testclient import TestClient  # noqa: E402

from core.auth import (  # noqa: E402; noqa: E402  (DEV_MODE lives here)
    current_user as current_user_module,
)
from core.config import get_settings  # noqa: E402
from services.api import main as backend_main  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def client():
    prev = current_user_module.DEV_MODE
    current_user_module.DEV_MODE = False
    prev_env = os.environ.get("DEV_MODE")
    os.environ["DEV_MODE"] = "false"
    get_settings.cache_clear()
    try:
        with TestClient(backend_main.app) as c:
            yield c
    finally:
        current_user_module.DEV_MODE = prev
        if prev_env is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = prev_env
        get_settings.cache_clear()


class TestContainmentRouterAuth:
    def test_the_lease_list_challenges_a_caller_with_no_credential(self, client):
        response = client.get("/api/containment/leases")
        assert response.status_code == 401

    def test_a_single_lease_read_challenges_a_caller_with_no_credential(self, client):
        response = client.get("/api/containment/leases/lease-abc123")
        assert response.status_code == 401


class TestContainmentRouterIsReadOnly:
    def test_the_surface_registers_no_mutation_verb(self):
        # The published OpenAPI route table — the same artifact the
        # generated-types CI check consumes — is the authoritative view of
        # what the API exposes: raw app.routes iteration cannot see through
        # FastAPI's lazy _IncludedRouter wrappers. v1's surface is GET-only
        # by construction: rollback runs in the daemon and the agent tools
        # (both demotions), and anything stronger rides the approvals queue.
        paths = backend_main.app.openapi()["paths"]
        checked = {
            path: sorted(methods)
            for path, methods in paths.items()
            if path.startswith("/api/containment")
        }
        assert checked, "the containment router must be mounted at all"
        for path, methods in checked.items():
            assert methods == ["get"], (
                f"{path} publishes {methods} — the lease surface is "
                "read-only in v1; mutations run in the daemon or ride the "
                "approvals queue"
            )

    def test_undo_payload_is_not_a_published_field(self):
        # Undo tokens are daemon-internal capability: undo is keyed on the
        # lease id and the payload never leaves the process that applies it.
        from core.response.fastpath.containment_router import ContainmentLeaseOut

        assert "undo_payload" not in ContainmentLeaseOut.model_fields
