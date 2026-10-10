"""Shared fixtures for the decoy unit tests: a fixed canary, a recording
emitter, and an enabled DecoyConfig. No database, no environment reads —
these are pure unit fixtures."""

import pytest

from services.decoy.canary import CanaryCredentials
from services.decoy.config import DecoyConfig


class RecordingEmitter:
    """Stands in for SessionEventEmitter: records payloads, always succeeds."""

    def __init__(self, fail: bool = False):
        self.payloads: list = []
        self.emitted = 0
        self._fail = fail

    @property
    def enabled(self) -> bool:
        return True

    async def emit(self, payload) -> bool:
        self.payloads.append(payload)
        self.emitted += 1
        return not self._fail


@pytest.fixture
def canary() -> CanaryCredentials:
    # A configured-style canary: the caller knows the plaintext, the marker
    # is embedded by construction (the containment test relies on this).
    return CanaryCredentials(
        password="vigil-canary:unit-test-password", ephemeral=False
    )


@pytest.fixture
def config() -> DecoyConfig:
    return DecoyConfig(enabled=True, session_ttl_seconds=3600)


@pytest.fixture
def emitter() -> RecordingEmitter:
    return RecordingEmitter()
