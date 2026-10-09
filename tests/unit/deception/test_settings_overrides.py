"""The Settings › Deception layer: stored row over env, failing safe.

The console's write lands in a ``system_config`` row; every reader — the
daemon's decision path, the responder's approval gate, the status endpoint —
must see it, and a failed read must answer the env values (whose defaults
are inert) rather than raise.
"""

from types import SimpleNamespace

import pytest

from core.deception import config as deception_config
from core.deception.config import (
    SETTINGS_CONFIG_KEY,
    DeceptionConfig,
    allowlist_errors,
    clear_settings_cache,
)

pytestmark = pytest.mark.unit


class FakeSettings:
    """Only the env fields DeceptionConfig resolution reads."""

    daemon_deception_enabled = False
    daemon_deception_backend = "dry_run"
    daemon_honey_route_floor = 0.80
    daemon_honey_route_ttl = 3600
    daemon_honey_route_max_duration = 86400
    daemon_honey_route_min_observations = 3
    daemon_honey_route_window = 3600
    daemon_deception_kill_switch = False
    daemon_deception_allowlist = ""


class FakeConfigStore:
    """A stand-in for the system_config store, per test."""

    def __init__(self):
        self.rows = {}
        self.writes = []

    def read_system_config(self, key):
        return self.rows.get(key)

    def set_system_config(
        self, key, value, description=None, config_type=None, change_reason=None
    ):
        self.writes.append({"key": key, "value": value, "reason": change_reason})
        self.rows[key] = value
        return True


@pytest.fixture(autouse=True)
def _fresh_cache():
    """No test may inherit another's cached overrides (60 s TTL)."""
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture()
def store(monkeypatch):
    """Route every settings read/write through one fake store."""
    fake = FakeConfigStore()
    monkeypatch.setattr(
        "core.storage.config_service.get_config_service", lambda user_id=None: fake
    )
    return fake


def with_stored(monkeypatch, overrides):
    monkeypatch.setattr(deception_config, "_stored_overrides", lambda: dict(overrides))


# --- Resolution order: stored row, then env ---------------------------------


def test_stored_row_wins_over_env(monkeypatch):
    with_stored(
        monkeypatch,
        {"enabled": True, "ttl_seconds": 7200, "allowlist": "10.0.0.0/8"},
    )
    config = DeceptionConfig.resolved(FakeSettings())
    assert config.enabled is True
    assert config.ttl_seconds == 7200
    assert config.allowlist == "10.0.0.0/8"
    # A key the row omits falls back to env.
    assert config.honey_route_floor == 0.80


def test_no_stored_row_answers_env(monkeypatch):
    with_stored(monkeypatch, {})
    config = DeceptionConfig.resolved(FakeSettings())
    assert config.enabled is False
    assert config.backend == "dry_run"
    assert config.ttl_seconds == 3600
    assert config.min_observations == 3


def test_failed_read_answers_env(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no database")

    monkeypatch.setattr("core.storage.config_service.get_config_service", _boom)
    assert deception_config._stored_overrides() == {}
    config = DeceptionConfig.resolved(FakeSettings())
    assert config.enabled is False
    assert config.ttl_seconds == 3600


def test_stored_values_are_coerced(monkeypatch):
    # A hand-edited row must not be able to break the readers: junk answers
    # env, and a truthy string still reads as on.
    with_stored(
        monkeypatch,
        {
            "enabled": "yes",
            "backend": "bogus",
            "honey_route_floor": "not-a-number",
            "ttl_seconds": None,
        },
    )
    config = DeceptionConfig.resolved(FakeSettings())
    assert config.enabled is True
    assert config.backend == "dry_run"  # unknown name falls back
    assert config.honey_route_floor == 0.80
    assert config.ttl_seconds == 3600


def test_invalid_stored_backend_falls_back_to_env(monkeypatch):
    with_stored(monkeypatch, {"backend": "wireguard"})
    config = DeceptionConfig.resolved(FakeSettings())
    assert config.backend == "dry_run"


# --- Allowlist validation ----------------------------------------------------


def test_allowlist_errors_names_unparseable_entries():
    assert allowlist_errors("10.0.0.0/8, not-an-ip, 192.168.1.1") == ["not-an-ip"]


def test_allowlist_errors_tolerates_empty_and_spaces():
    assert allowlist_errors("") == []
    assert allowlist_errors("  10.0.0.5 , 203.0.113.0/24  ") == []


# --- The Settings endpoint ---------------------------------------------------


def _write_body(**overrides):
    body = {
        "enabled": True,
        "backend": "dry_run",
        "honey_route_floor": 0.75,
        "ttl_seconds": 7200,
        "max_duration_seconds": 86400,
        "min_observations": 2,
        "window_seconds": 1800,
        "allowlist": "10.0.0.0/8",
    }
    body.update(overrides)
    return body


async def test_settings_write_round_trips(store):
    from core.deception import deception_router

    user = SimpleNamespace(user_id="user-1")
    response = await deception_router.update_settings(
        deception_router.DeceptionSettingsWrite(**_write_body()), current_user=user
    )
    assert response["enabled"] is True
    assert response["ttl_seconds"] == 7200
    assert response["allowlist"] == "10.0.0.0/8"
    key, value = store.writes[0]["key"], store.writes[0]["value"]
    assert key == SETTINGS_CONFIG_KEY
    assert value["honey_route_floor"] == 0.75
    assert store.writes[0]["reason"]


async def test_settings_write_refuses_unknown_backend(store):
    from fastapi import HTTPException

    from core.deception import deception_router

    with pytest.raises(HTTPException) as excinfo:
        await deception_router.update_settings(
            deception_router.DeceptionSettingsWrite(**_write_body(backend="wireguard")),
            current_user=SimpleNamespace(user_id="user-1"),
        )
    assert excinfo.value.status_code == 422


async def test_settings_write_refuses_ttl_above_max_duration(store):
    from fastapi import HTTPException

    from core.deception import deception_router

    with pytest.raises(HTTPException) as excinfo:
        await deception_router.update_settings(
            deception_router.DeceptionSettingsWrite(
                **_write_body(ttl_seconds=86400, max_duration_seconds=3600)
            ),
            current_user=SimpleNamespace(user_id="user-1"),
        )
    assert excinfo.value.status_code == 422


async def test_settings_write_refuses_unparseable_allowlist(store):
    from fastapi import HTTPException

    from core.deception import deception_router

    with pytest.raises(HTTPException) as excinfo:
        await deception_router.update_settings(
            deception_router.DeceptionSettingsWrite(
                **_write_body(allowlist="10.0.0.0/8, scannerbox")
            ),
            current_user=SimpleNamespace(user_id="user-1"),
        )
    assert excinfo.value.status_code == 422
    assert "scannerbox" in excinfo.value.detail
