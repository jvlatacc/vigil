"""Shared fixtures for the edge control-plane tests."""

import pytest

from core.edge import registry


@pytest.fixture
def edge_enrollment_secret(monkeypatch) -> str:
    """Pin VIGIL_EDGE_ENROLLMENT_SECRET at the late-lookup seam.

    ``core.secrets.get_secret`` is documented as the one patch seam, but the
    registry imports it by name — patch it in the registry's namespace so
    tests never depend on process-wide environment state. Returns the value
    tests should use when minting tokens.
    """
    secret = "edge-test-enrollment-secret"
    monkeypatch.setattr(
        registry, "get_secret", lambda key, default=None: secret, raising=True
    )
    return secret
