"""The Settings UI surface for the JIT policy compiler tunables.

The four ``policy_compiler_*`` runtime-config keys (docs/adr/0001) are edited
from Settings via ``AIOperationsSettingsConfig``; here the model's defaults and
bounds are pinned against ``core.policy_compiler.config``, and the POST
endpoint is shown to persist them (the write the maturity job reads back
through ``get_ai_operations_setting``). No database: the config service is a
mock, the ``test_integrations_config_save.py`` pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.api.routers import config as config_module
from services.api.routers.config import AIOperationsSettingsConfig

pytestmark = pytest.mark.unit


class _User:
    user_id = "user-1"


def _stored(value: dict | None) -> MagicMock:
    service = MagicMock()
    service.get_system_config.return_value = value
    service.set_system_config.return_value = True
    return service


# --- model defaults and bounds -------------------------------------------------


def test_defaults_match_the_shipped_maturity_thresholds():
    config = AIOperationsSettingsConfig()
    assert config.policy_compiler_min_runs == 10
    assert config.policy_compiler_min_consistency == pytest.approx(0.90)
    assert config.policy_compiler_window_days == 30
    assert config.policy_compiler_drift_limit == 3


def test_ollama_defaults_are_unchanged():
    # The fields this screen adds must not disturb the existing toggles.
    config = AIOperationsSettingsConfig()
    assert config.local_ollama_recovery_enabled is True
    assert config.local_ollama_recovery_retry_limit == 1
    assert config.local_ollama_recovery_restart_gateway is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_compiler_min_runs", 0),
        ("policy_compiler_min_runs", 1001),
        ("policy_compiler_min_consistency", -0.1),
        ("policy_compiler_min_consistency", 1.1),
        ("policy_compiler_window_days", 0),
        ("policy_compiler_window_days", 366),
        ("policy_compiler_drift_limit", 0),
        ("policy_compiler_drift_limit", 101),
    ],
)
def test_out_of_range_tunables_are_rejected(field: str, value: float):
    with pytest.raises(ValueError, match=field):
        AIOperationsSettingsConfig(**{field: value})


# --- the endpoints -------------------------------------------------------------


def test_get_serves_defaults_when_nothing_is_stored(monkeypatch):
    monkeypatch.setattr(
        config_module, "get_config_service", lambda *a, **k: _stored(None)
    )
    data = config_module.get_ai_operations_config()
    assert data["policy_compiler_min_runs"] == 10
    assert data["policy_compiler_min_consistency"] == pytest.approx(0.90)
    assert data["policy_compiler_window_days"] == 30
    assert data["policy_compiler_drift_limit"] == 3


def test_get_merges_stored_tunables_over_defaults(monkeypatch):
    stored = {
        "policy_compiler_min_runs": 25,
        "policy_compiler_min_consistency": 0.95,
    }
    monkeypatch.setattr(
        config_module, "get_config_service", lambda *a, **k: _stored(stored)
    )
    data = config_module.get_ai_operations_config()
    assert data["policy_compiler_min_runs"] == 25
    assert data["policy_compiler_min_consistency"] == pytest.approx(0.95)
    # unset keys keep their defaults
    assert data["policy_compiler_window_days"] == 30
    assert data["policy_compiler_drift_limit"] == 3


def test_get_drops_keys_the_schema_no_longer_declares(monkeypatch):
    stored = {"policy_compiler_min_runs": 25, "stale_knob": 7}
    monkeypatch.setattr(
        config_module, "get_config_service", lambda *a, **k: _stored(stored)
    )
    assert "stale_knob" not in config_module.get_ai_operations_config()


def test_post_persists_the_tunables_and_invalidates_the_cache(monkeypatch):
    service = _stored(None)
    monkeypatch.setattr(config_module, "get_config_service", lambda *a, **k: service)
    cleared = []
    monkeypatch.setattr(
        "core.platform.runtime_config.clear_cache", lambda: cleared.append(True)
    )

    payload = AIOperationsSettingsConfig(
        policy_compiler_min_runs=25,
        policy_compiler_min_consistency=0.95,
        policy_compiler_window_days=14,
        policy_compiler_drift_limit=5,
    )
    result = config_module.set_ai_operations_config(payload, current_user=_User())

    assert result == {"success": True, "message": "AI operations config updated"}
    args, kwargs = service.set_system_config.call_args
    assert kwargs.get("key") or args[0] == "ai_operations.settings"
    stored = kwargs.get("value") if "value" in kwargs else args[1]
    assert stored["policy_compiler_min_runs"] == 25
    assert stored["policy_compiler_min_consistency"] == pytest.approx(0.95)
    assert stored["policy_compiler_window_days"] == 14
    assert stored["policy_compiler_drift_limit"] == 5
    assert cleared == [True]


def test_failed_persist_is_an_error_not_a_success(monkeypatch):
    service = _stored(None)
    service.set_system_config.return_value = False
    monkeypatch.setattr(config_module, "get_config_service", lambda *a, **k: service)

    with pytest.raises(HTTPException) as exc:
        config_module.set_ai_operations_config(
            AIOperationsSettingsConfig(), current_user=_User()
        )
    assert exc.value.status_code == 500
