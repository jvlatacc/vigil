"""jit_fast_path_enabled: default off in every environment, wired through, declared.

Also the maturity tunables: DB-first runtime-config keys whose env fallbacks
are named in ``ENV_FALLBACKS`` with defaults in ``core.policy_compiler.config``
(docs/adr/0001). No Postgres.
"""

from pathlib import Path

import pytest

from core.config import Settings, get_settings
from core.intent import INTENT_FIELDS, LOWER_TIGHTER, effective_values, read_intent
from core.platform import runtime_config
from core.policy_compiler import config as pc_config
from services.daemon.config import DaemonConfig

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO / "env.example"
COMPOSE = REPO / "infra" / "docker" / "docker-compose.yml"
HELM_VALUES = REPO / "infra" / "helm" / "vigil" / "values.yaml"

KNOB = "triage.jit_fast_path_enabled"

# (runtime-config key, env var, spec default)
TUNABLES = [
    (pc_config.MIN_RUNS_KEY, "POLICY_COMPILER_MIN_RUNS", pc_config.MIN_RUNS_DEFAULT),
    (
        pc_config.MIN_CONSISTENCY_KEY,
        "POLICY_COMPILER_MIN_CONSISTENCY",
        pc_config.MIN_CONSISTENCY_DEFAULT,
    ),
    (
        pc_config.WINDOW_DAYS_KEY,
        "POLICY_COMPILER_WINDOW_DAYS",
        pc_config.WINDOW_DAYS_DEFAULT,
    ),
    (
        pc_config.DRIFT_LIMIT_KEY,
        "POLICY_COMPILER_DRIFT_LIMIT",
        pc_config.DRIFT_LIMIT_DEFAULT,
    ),
]


# --- the flag ------------------------------------------------------------------


def test_settings_field_defaults_off(monkeypatch):
    monkeypatch.delenv("JIT_FAST_PATH_ENABLED", raising=False)
    get_settings.cache_clear()
    assert Settings.model_fields["jit_fast_path_enabled"].default is False
    assert Settings().jit_fast_path_enabled is False


def test_daemon_config_defaults_off(monkeypatch):
    monkeypatch.delenv("JIT_FAST_PATH_ENABLED", raising=False)
    get_settings.cache_clear()
    assert DaemonConfig.from_env().processing.jit_fast_path_enabled is False


def test_env_can_turn_the_flag_on(monkeypatch):
    monkeypatch.setenv("JIT_FAST_PATH_ENABLED", "true")
    get_settings.cache_clear()
    assert Settings().jit_fast_path_enabled is True


def test_default_off_in_every_environment():
    # env.example documents the shipped default; compose and Helm pass it
    # through explicitly, again off. A deployment that upgrades gains nothing.
    assert 'JIT_FAST_PATH_ENABLED="false"' in ENV_EXAMPLE.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "  JIT_FAST_PATH_ENABLED: ${JIT_FAST_PATH_ENABLED:-false}" in compose
    assert 'JIT_FAST_PATH_ENABLED: "false"' in HELM_VALUES.read_text(encoding="utf-8")


# --- the INTENT.md declaration ---------------------------------------------------


def test_knob_is_registered_with_a_reader():
    field = next(f for f in INTENT_FIELDS if f.key == KNOB)
    assert field.path == "processing.jit_fast_path_enabled"
    assert field.setting == "jit_fast_path_enabled"
    assert field.rule == LOWER_TIGHTER


def test_shipped_manifest_declares_the_knob_off():
    declared = read_intent()
    assert declared is not None
    assert declared[KNOB] is False


def test_effective_value_walks_the_daemon_config():
    assert effective_values(DaemonConfig())[KNOB] is False


# --- the maturity tunables -------------------------------------------------------


def test_tunable_keys_are_runtime_config_keys_with_env_fallbacks():
    for key, env_name, _default in TUNABLES:
        assert runtime_config.ENV_FALLBACKS.get(key) == env_name
        # The fallback name is the key, upper-cased, by the module's convention.
        assert env_name == key.upper()


def test_tunable_defaults_are_the_spec_defaults():
    assert pc_config.MIN_RUNS_DEFAULT == 10
    assert pc_config.MIN_CONSISTENCY_DEFAULT == 0.90
    assert pc_config.WINDOW_DAYS_DEFAULT == 30
    assert pc_config.DRIFT_LIMIT_DEFAULT == 3


def test_env_fallback_resolves_with_coercion(monkeypatch):
    runtime_config.clear_cache()
    monkeypatch.setattr(runtime_config, "_fetch_db_config", lambda: None)
    monkeypatch.setenv("POLICY_COMPILER_MIN_RUNS", "12")
    monkeypatch.setenv("POLICY_COMPILER_MIN_CONSISTENCY", "0.85")
    assert runtime_config.get_ai_operations_setting(pc_config.MIN_RUNS_KEY, 10) == 12
    assert (
        runtime_config.get_ai_operations_setting(pc_config.MIN_CONSISTENCY_KEY, 0.90)
        == 0.85
    )


def test_db_value_wins_over_the_env_fallback(monkeypatch):
    runtime_config.clear_cache()
    monkeypatch.setattr(
        runtime_config,
        "_fetch_db_config",
        lambda: {pc_config.MIN_RUNS_KEY: 25},
    )
    monkeypatch.setenv("POLICY_COMPILER_MIN_RUNS", "12")
    assert runtime_config.get_ai_operations_setting(pc_config.MIN_RUNS_KEY, 10) == 25
