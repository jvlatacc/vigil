"""Unit tests for CepConfig env parsing (defaults, overrides, clamping)."""

from __future__ import annotations

import pytest

from core.cep.config import CepConfig

_CEP_KEYS = (
    "CEP_ENABLED",
    "CEP_QUEUE_MAX",
    "CEP_SNAPSHOT_INTERVAL_S",
    "CEP_GRAPH_MAX_NODES",
    "CEP_GRAPH_MAX_EDGES",
    "CEP_RULES_PATH",
)


@pytest.fixture(autouse=True)
def clean_cep_env(monkeypatch: pytest.MonkeyPatch):
    """Keep the tests hermetic of the developer's shell."""
    for key in _CEP_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_match_env_example_documentation():
    config = CepConfig.from_env()
    assert config.enabled is True
    assert config.queue_max == 1000
    assert config.snapshot_interval_s == 60
    assert config.graph_max_nodes == 10_000
    assert config.graph_max_edges == 50_000
    assert config.rules_path == "data/cep_rules"


@pytest.mark.parametrize("raw", ["true", "1", "yes", "on", "TRUE", "Yes"])
def test_enabled_truthy_values(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv("CEP_ENABLED", raw)
    assert CepConfig.from_env().enabled is True


@pytest.mark.parametrize("raw", ["false", "0", "no", "off"])
def test_enabled_falsy_values(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv("CEP_ENABLED", raw)
    assert CepConfig.from_env().enabled is False


def test_enabled_empty_value_uses_default(monkeypatch: pytest.MonkeyPatch):
    """Set-but-empty (the compose rendering of an unset default) is the
    unset default, not an explicit opt-out."""
    monkeypatch.setenv("CEP_ENABLED", "")
    assert CepConfig.from_env().enabled is True


def test_integer_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CEP_QUEUE_MAX", "50")
    monkeypatch.setenv("CEP_SNAPSHOT_INTERVAL_S", "300")
    monkeypatch.setenv("CEP_GRAPH_MAX_NODES", "20000")
    monkeypatch.setenv("CEP_GRAPH_MAX_EDGES", "90000")
    monkeypatch.setenv("CEP_RULES_PATH", "/etc/vigil/cep-rules")

    config = CepConfig.from_env()
    assert config.queue_max == 50
    assert config.snapshot_interval_s == 300
    assert config.graph_max_nodes == 20_000
    assert config.graph_max_edges == 90_000
    assert config.rules_path == "/etc/vigil/cep-rules"


def test_garbage_int_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CEP_QUEUE_MAX", "not-a-number")
    assert CepConfig.from_env().queue_max == 1000


def test_below_minimum_is_clamped(monkeypatch: pytest.MonkeyPatch):
    """The bounds are load-bearing: an unbounded queue would defeat the
    drop design, so a nonsense value must not widen them."""
    monkeypatch.setenv("CEP_QUEUE_MAX", "0")
    monkeypatch.setenv("CEP_SNAPSHOT_INTERVAL_S", "-5")
    config = CepConfig.from_env()
    assert config.queue_max == 1
    assert config.snapshot_interval_s == 1
