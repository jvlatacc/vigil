"""The /mcp mount, from the security suite's side of the glass.

``tests/unit/api/test_mcp_surface_gate.py`` owns the gate's behavior in
detail. What that file could not give the security suite is what E14 found
missing: ``tests/security/`` was blind to the mount. The route inventory
filtered to ``/api/``, and nothing in this directory mentioned ``/mcp`` at
all — so a gate that quietly vanished from the route table, or stopped
refusing, would have left the security suite green while the surface opened.

This file is the suite's sight-line, in two halves: the mount is on the
route table where the app advertises it, and it is the credential gate
sitting there — then the four answers the surface must give. A closed
surface is not found. An open one challenges the unauthenticated. And the
two credentials that must never open it — a session JWT, and the
development credential with the bypass off — do not.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

# Importing services.api.main refuses to load without a JWT secret once
# DEV_MODE is false — the default in CI. The other security tests that
# import the app set this for the same reason.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")

pytestmark = pytest.mark.unit


def _mcp_mount(app):
    """The Mount serving Vigil's MCP server, or None if it is gone."""
    from core.config import get_settings

    address = f"{get_settings().vigil_context_path.rstrip('/')}/mcp"
    return next(
        (
            route
            for route in app.routes
            if type(route).__name__ == "Mount"
            and getattr(route, "path", None) == address
        ),
        None,
    )


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from services.api.main import app

    with TestClient(app) as c:
        yield c


# --- The mount the suite is guarding ------------------------------------------


def test_the_mount_is_on_the_route_table():
    """E14: the security suite can see the thing it is guarding.

    A mount that disappears from the route table — unmounted, renamed,
    moved to an address nothing documents — fails here, in the suite whose
    job is the integration boundary, rather than only in whatever test
    happens to exercise the MCP client that week.
    """
    from services.api.main import app

    assert _mcp_mount(app) is not None, (
        "No /mcp mount in the route table. Either the surface was unmounted "
        "(a regression to chase) or it moved (update MOUNT_PATH and this "
        "sight-line together)."
    )


def test_the_mount_serves_the_gate_not_the_raw_server():
    """What sits at /mcp answers credentials before anything else runs."""
    from services.api.main import app
    from services.api.mcp_surface import McpSurfaceGate

    mount = _mcp_mount(app)
    assert mount is not None  # the named failure above, if it comes to that
    assert isinstance(mount.app, McpSurfaceGate), (
        "The /mcp mount no longer points at McpSurfaceGate. The MCP server "
        "app would be reachable without the credential check that refuses "
        "every request without one."
    )


# --- The four answers ----------------------------------------------------------


def test_a_closed_surface_is_not_found(client):
    """The shipped setting (`vigil_mcp_enabled` defaults to false): the
    surface does not announce that it exists."""
    with patch("services.api.mcp_surface.is_enabled", return_value=False):
        response = client.post("/mcp", json={})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_an_open_surface_challenges_the_unauthenticated(client):
    with patch("services.api.mcp_surface.is_enabled", return_value=True):
        response = client.post("/mcp", json={})

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


class _SessionUser:
    """Just enough of a user to mint a session token: generate_jwt_token is
    a staticmethod and reads four attributes off the object."""

    user_id = "u-suite"
    username = "analyst"
    email = "analyst@example.com"
    role_id = "r-analyst"


def test_a_session_jwt_does_not_open_the_surface(client):
    """The credential that opens /api is the wrong kind here.

    Mint a real one — correctly signed with the same secret the backend
    checks — rather than pasting a string shaped like a JWT: the point is
    that the refusal is about the kind of credential, not its malformation.
    A future change that wires session auth into the MCP gate lands as this
    test going red, not as a quiet widening of who can reach Vigil's tools.
    """
    from core.auth.auth_service import AuthService

    session_jwt = AuthService.generate_jwt_token(_SessionUser())

    with patch("services.api.mcp_surface.is_enabled", return_value=True):
        response = client.post(
            "/mcp", json={}, headers={"Authorization": f"Bearer {session_jwt}"}
        )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_the_dev_credential_is_refused_when_the_bypass_is_off(client):
    """DEV_MODE is the other credential that must not work here: the fixed
    development token only authenticates behind the bypass, which is off on
    every packaged path."""
    from services.api.mcp_surface import DEV_MODE_TOKEN

    with patch("services.api.mcp_surface.is_enabled", return_value=True), patch(
        "core.config.get_settings"
    ) as settings:
        settings.return_value.dev_mode = False
        response = client.post(
            "/mcp", json={}, headers={"Authorization": f"Bearer {DEV_MODE_TOKEN}"}
        )

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
