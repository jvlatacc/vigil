"""Canary credential behavior: the canary always succeeds, nothing else
does, and every generated value is identifiable as fake (spec, Locked:
"canary-only credentials" and the leak-identifiability requirement)."""

import logging

import pytest

from services.decoy.canary import (
    CANARY_SECRET_KEY,
    CanaryCredentials,
    resolve_canary,
)
from services.decoy.config import CANARY_MARKER

pytestmark = pytest.mark.unit


def test_canary_succeeds_with_its_own_value(canary):
    assert canary.matches("vigil-canary:unit-test-password") is True


def test_canary_fails_everything_else(canary):
    assert canary.matches("password") is False
    assert canary.matches("") is False
    assert canary.matches("vigil-canary:unit-test-passwor") is False  # near miss
    assert canary.matches("VIGIL-CANARY:UNIT-TEST-PASSWORD") is False


def test_resolve_canary_without_secret_generates_marked_ephemeral(monkeypatch):
    monkeypatch.setattr(
        "services.decoy.canary.get_secret", lambda key: None, raising=True
    )
    canary = resolve_canary()
    assert canary.ephemeral is True
    # The planted value is identifiable as fake on sight (leak identifiability).
    assert canary.marked.startswith(f"{CANARY_MARKER}:")
    # Ephemeral canaries are unique per lifetime — nothing durable or shared.
    assert resolve_canary().marked != canary.marked


def test_resolve_canary_reads_the_secret_channel(monkeypatch):
    seen = {}

    def fake_get_secret(key):
        seen["key"] = key
        return f"{CANARY_MARKER}:from-secret-plumbing"

    monkeypatch.setattr("services.decoy.canary.get_secret", fake_get_secret)
    canary = resolve_canary()
    assert seen["key"] == CANARY_SECRET_KEY
    assert canary.ephemeral is False
    assert canary.matches(f"{CANARY_MARKER}:from-secret-plumbing") is True


def test_resolve_canary_warns_when_configured_value_lacks_marker(caplog):
    with caplog.at_level(logging.WARNING, logger="services.decoy.canary"):
        canary = resolve_canary(configured="operator-picked-but-unmarked")
    assert "does not contain the marker" in caplog.text
    # Still used — the operator's value is authoritative, loudly flagged.
    assert canary.matches("operator-picked-but-unmarked") is True


def test_resolve_canary_accepts_marked_configured_value(caplog):
    with caplog.at_level(logging.WARNING, logger="services.decoy.canary"):
        canary = resolve_canary(configured=f"{CANARY_MARKER}:proper")
    assert "does not contain the marker" not in caplog.text
    assert canary.ephemeral is False


def test_ephemeral_marked_value_embeds_the_marker():
    marked = CanaryCredentials(
        password=f"{CANARY_MARKER}-abc123", ephemeral=True
    ).marked
    assert marked.startswith(f"{CANARY_MARKER}:")
    assert "abc123" in marked


def test_injectable_configuration_beats_the_secret_channel(monkeypatch):
    monkeypatch.setattr(
        "services.decoy.canary.get_secret",
        lambda key: f"{CANARY_MARKER}:from-channel",
        raising=True,
    )
    canary = resolve_canary(configured=f"{CANARY_MARKER}:injected")
    assert canary.matches(f"{CANARY_MARKER}:injected") is True
    assert canary.matches(f"{CANARY_MARKER}:from-channel") is False
