"""FastPathConfig defaults, env overrides, and the ttl invariants."""

import pytest
from pydantic import ValidationError

from core.response.fastpath.config import FastPathConfig

pytestmark = pytest.mark.unit


def test_defaults_are_inert_and_time_bounded():
    config = FastPathConfig()
    assert config.enabled is False
    assert config.pre_triage_enabled is False
    assert config.default_ttl_seconds == 600
    assert config.max_ttl_seconds == 3600
    assert config.max_speculative_per_target == 1


def test_the_tier_gates_are_independent():
    config = FastPathConfig(enabled=True, pre_triage_enabled=True)
    assert config.enabled is True
    assert config.pre_triage_enabled is True


def test_env_overrides_move_the_switches(monkeypatch):
    monkeypatch.setenv("FAST_PATH_ENABLED", "true")
    monkeypatch.setenv("FAST_PATH_PRE_TRIAGE_ENABLED", "true")
    monkeypatch.setenv("FAST_PATH_DEFAULT_TTL_SECONDS", "300")
    config = FastPathConfig()
    assert config.enabled is True
    assert config.pre_triage_enabled is True
    assert config.default_ttl_seconds == 300


def test_the_allowlist_and_enforced_set_match_the_spec():
    config = FastPathConfig()
    assert config.allowed_action_types == frozenset(
        {"rate_limit", "tarpit", "session_pin", "latency_inject"}
    )
    assert config.enforced_action_types == frozenset({"rate_limit"})


def test_a_default_ttl_above_the_ceiling_is_refused():
    with pytest.raises(ValidationError):
        FastPathConfig(default_ttl_seconds=3601, max_ttl_seconds=3600)


def test_a_zero_ttl_is_refused():
    with pytest.raises(ValidationError):
        FastPathConfig(default_ttl_seconds=0)
    with pytest.raises(ValidationError):
        FastPathConfig(max_ttl_seconds=0)
