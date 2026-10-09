"""Config: pure parsing over a mapping — the ratchet-compliant VIGIL_EDGE_* set."""

from __future__ import annotations

import pytest

from services.edge.app.config import (
    ConfigError,
    EdgeConfig,
    flag_value,
    is_enabled,
)


def test_flag_off_by_default() -> None:
    assert flag_value({}) is None
    assert not is_enabled({})


@pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "on"])
def test_enabled_values(value: str) -> None:
    assert is_enabled({"VIGIL_EDGE_ENABLED": value})


@pytest.mark.parametrize("value", ["false", "", "0", "no", "off", "maybe"])
def test_disabled_values(value: str) -> None:
    assert not is_enabled({"VIGIL_EDGE_ENABLED": value})


def test_defaults_are_the_spec_set() -> None:
    config = EdgeConfig.from_env({})
    assert config.mode == "gateway"
    assert config.control_url == "https://vigil.internal"
    assert config.health_port == 9091
    assert config.model == "qwen2.5:1.5b"
    assert config.model_digest == ""
    assert config.model_url == "http://localhost:11434"
    assert config.node_labels == {}
    assert config.eve_path is None


def test_from_env_overrides() -> None:
    config = EdgeConfig.from_env(
        {
            "VIGIL_EDGE_NODE_ID": "gw-vpc-west-01",
            "VIGIL_EDGE_MODE": "cluster",
            "VIGIL_EDGE_CONTROL_URL": "https://vigil.example.internal",
            "VIGIL_EDGE_HEALTH_PORT": "9092",
            "VIGIL_EDGE_NODE_LABELS": '{"vigil.ai/edge-role": "gateway"}',
            "VIGIL_EDGE_DATA_DIR": "/tmp/edge-data",
            "VIGIL_EDGE_EVE_PATH": "/var/log/suricata/eve.json",
        }
    )
    assert config.node_id == "gw-vpc-west-01"
    assert config.mode == "cluster"
    assert config.health_port == 9092
    assert config.node_labels == {"vigil.ai/edge-role": "gateway"}
    assert config.eve_path is not None and config.eve_path.name == "eve.json"


def test_empty_model_disables_the_advisor() -> None:
    assert EdgeConfig.from_env({"VIGIL_EDGE_MODEL": ""}).model is None


def test_bad_mode_raises() -> None:
    with pytest.raises(ConfigError, match="VIGIL_EDGE_MODE"):
        EdgeConfig.from_env({"VIGIL_EDGE_MODE": "sidecar"})


def test_bad_port_raises() -> None:
    with pytest.raises(ConfigError, match="VIGIL_EDGE_HEALTH_PORT"):
        EdgeConfig.from_env({"VIGIL_EDGE_HEALTH_PORT": "ninety"})


def test_bad_labels_json_raises() -> None:
    with pytest.raises(ConfigError, match="VIGIL_EDGE_NODE_LABELS"):
        EdgeConfig.from_env({"VIGIL_EDGE_NODE_LABELS": "{not json"})


def test_non_string_label_values_raise() -> None:
    with pytest.raises(ConfigError, match="string -> string"):
        EdgeConfig.from_env({"VIGIL_EDGE_NODE_LABELS": '{"a": 1}'})


def test_validate_collects_missing_node_id() -> None:
    problems = EdgeConfig.from_env({}).validate()
    assert any("VIGIL_EDGE_NODE_ID" in p for p in problems)


def test_validate_clean_for_a_full_config() -> None:
    config = EdgeConfig.from_env({"VIGIL_EDGE_NODE_ID": "node-1"})
    assert config.validate() == []
