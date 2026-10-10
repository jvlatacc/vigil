"""Guard config that cannot be misread: bad numbers refuse, bad JSON refuses.

``approval_requirement`` treats a confidence outside [0, 1] as a caller
inflating the number, and holds the action. Guard construction has no
action to hold, so ``GuardConfig.from_settings`` refuses the configuration
instead — the same refusal to let garbage read as valid, one step earlier
(#944).
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.response.guards_config import GuardConfig, GuardConfigError

pytestmark = pytest.mark.unit


def _settings(**overrides) -> SimpleNamespace:
    """A settings stand-in: the bridge-relevant fields at their defaults."""
    values = dict(
        daemon_containment_quotas_enabled=True,
        daemon_subnet_scope_prefix=24,
        daemon_containment_quota_subnet_pct_per_min=5.0,
        daemon_containment_quota_global_per_min=30,
        daemon_containment_quota_global_per_hour=200,
        daemon_breaker_cooldown_seconds=900,
        daemon_breaker_invariant_probe_trip=3,
        daemon_breaker_origin_flood_trip=10,
        daemon_protected_assets=[],
        daemon_trusted_origins=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_the_bridge_defaults_match_the_settings_defaults():
    # The bridge mirrors Settings' literals the way ResponseConfig does; if
    # one side moves without the other, a default install changes meaning.
    fields = Settings.model_fields
    config = GuardConfig()
    assert config.quotas_enabled is fields["daemon_containment_quotas_enabled"].default
    assert config.subnet_scope_prefix == fields["daemon_subnet_scope_prefix"].default
    assert (
        config.quota_subnet_pct_per_min
        == fields["daemon_containment_quota_subnet_pct_per_min"].default
    )
    assert (
        config.quota_global_per_min
        == fields["daemon_containment_quota_global_per_min"].default
    )
    assert (
        config.quota_global_per_hour
        == fields["daemon_containment_quota_global_per_hour"].default
    )
    assert (
        config.breaker_cooldown_seconds
        == fields["daemon_breaker_cooldown_seconds"].default
    )
    assert (
        config.breaker_invariant_probe_trip
        == fields["daemon_breaker_invariant_probe_trip"].default
    )
    assert (
        config.breaker_origin_flood_trip
        == fields["daemon_breaker_origin_flood_trip"].default
    )
    assert config.protected_assets == ()
    assert config.trusted_origins == ()


def test_from_settings_carries_the_operators_numbers():
    config = GuardConfig.from_settings(
        _settings(
            daemon_subnet_scope_prefix=16,
            daemon_containment_quota_global_per_min=5,
            daemon_breaker_cooldown_seconds=60,
        )
    )
    assert config.subnet_scope_prefix == 16
    assert config.quota_global_per_min == 5
    assert config.breaker_cooldown_seconds == 60
    assert config.quotas_enabled is True


@pytest.mark.parametrize("prefix", [33, -1, "24", 24.0, True, None])
def test_a_scope_prefix_outside_the_address_range_is_refused(prefix):
    with pytest.raises(GuardConfigError, match="daemon_subnet_scope_prefix"):
        GuardConfig.from_settings(_settings(daemon_subnet_scope_prefix=prefix))


@pytest.mark.parametrize("prefix", [0, 32])
def test_the_prefix_boundaries_are_valid_scopes(prefix):
    assert GuardConfig.from_settings(_settings(daemon_subnet_scope_prefix=prefix))


@pytest.mark.parametrize("pct", [0, 0.0, -5.0, 100.5, "5", float("nan"), float("inf")])
def test_a_subnet_percentage_that_is_not_one_is_refused(pct):
    # Zero is not a quota but a shutdown; the off switch is the boolean.
    with pytest.raises(
        GuardConfigError, match="daemon_containment_quota_subnet_pct_per_min"
    ):
        GuardConfig.from_settings(
            _settings(daemon_containment_quota_subnet_pct_per_min=pct)
        )


@pytest.mark.parametrize("pct", [0.5, 100.0])
def test_the_percentage_boundaries_are_valid_quotas(pct):
    config = GuardConfig.from_settings(
        _settings(daemon_containment_quota_subnet_pct_per_min=pct)
    )
    assert config.quota_subnet_pct_per_min == float(pct)


@pytest.mark.parametrize(
    "field",
    [
        "daemon_containment_quota_global_per_min",
        "daemon_containment_quota_global_per_hour",
        "daemon_breaker_cooldown_seconds",
        "daemon_breaker_invariant_probe_trip",
        "daemon_breaker_origin_flood_trip",
    ],
)
@pytest.mark.parametrize("value", [0, -1, "30", 2.5, True, None])
def test_an_integer_knob_that_cannot_count_is_refused(field, value):
    with pytest.raises(GuardConfigError, match=field):
        GuardConfig.from_settings(_settings(**{field: value}))


@pytest.mark.parametrize("field", ["daemon_protected_assets", "daemon_trusted_origins"])
def test_a_malformed_seed_string_is_refused_at_the_bridge(field):
    with pytest.raises(GuardConfigError, match="not valid JSON"):
        GuardConfig.from_settings(_settings(**{field: "{not json"}))


@pytest.mark.parametrize("field", ["daemon_protected_assets", "daemon_trusted_origins"])
def test_seed_entries_that_are_not_objects_are_refused(field):
    with pytest.raises(GuardConfigError, match="every entry must be a JSON object"):
        GuardConfig.from_settings(_settings(**{field: ["sensor-edge-01"]}))


def test_json_seed_strings_parse_into_read_only_tuples():
    config = GuardConfig.from_settings(
        _settings(
            daemon_protected_assets='[{"match_kind": "cidr", "match_value": "10.0.0.0/24"}]',
            daemon_trusted_origins='[{"origin_id": "sensor-edge-01"}]',
        )
    )
    assert config.protected_assets == (
        {"match_kind": "cidr", "match_value": "10.0.0.0/24"},
    )
    assert config.trusted_origins == ({"origin_id": "sensor-edge-01"},)


def test_a_seed_list_passes_through_as_a_tuple():
    entries = [{"match_kind": "ip", "match_value": "10.0.0.53"}]
    config = GuardConfig.from_settings(_settings(daemon_protected_assets=entries))
    assert config.protected_assets == tuple(entries)


def test_a_blank_seed_string_means_no_seed():
    config = GuardConfig.from_settings(
        _settings(daemon_protected_assets="", daemon_trusted_origins="  ")
    )
    assert config.protected_assets == ()
    assert config.trusted_origins == ()


def test_settings_parses_a_json_seed_env_value():
    settings = Settings(
        daemon_protected_assets='[{"match_kind": "ip", "match_value": "10.0.0.53"}]'
    )
    assert settings.daemon_protected_assets == [
        {"match_kind": "ip", "match_value": "10.0.0.53"}
    ]


def test_settings_refuses_a_malformed_seed_env_value():
    # Fail validation at boot (validate_settings_or_exit exits EX_CONFIG)
    # rather than booting with invariants that read as absent.
    with pytest.raises(ValidationError):
        Settings(daemon_protected_assets='[{"match_kind": }')
