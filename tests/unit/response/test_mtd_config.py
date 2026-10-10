"""MTD config that defaults off, and a bridge that mirrors Settings.

Default-off is the feature's first acceptance criterion: with the env unset
``MtdConfig`` constructs disabled, so ``mtd_route_decision`` refuses every
input before any other gate is read. The bridge carries an operator's
numbers the way ``ResponseConfig`` does — the two bands share a module,
never a threshold.
"""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.response.config import MtdConfig

pytestmark = pytest.mark.unit


def _settings(**overrides) -> SimpleNamespace:
    """A settings stand-in: the bridge-relevant fields at their defaults."""
    values = dict(
        daemon_mtd_enabled=False,
        daemon_mtd_confidence_floor=0.60,
        daemon_mtd_session_ttl_seconds=3600,
        daemon_mtd_internal_only=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_default_config_is_disabled():
    config = MtdConfig()
    assert config.enabled is False
    assert config.confidence_floor == 0.60
    assert config.session_ttl_seconds == 3600
    assert config.internal_destinations_only is True


def test_the_bridge_defaults_match_the_settings_defaults():
    # The bridge mirrors Settings' literals the way ResponseConfig does; if
    # one side moves without the other, a default install changes meaning.
    fields = Settings.model_fields
    config = MtdConfig()
    assert config.enabled is fields["daemon_mtd_enabled"].default
    assert config.confidence_floor == fields["daemon_mtd_confidence_floor"].default
    assert (
        config.session_ttl_seconds == fields["daemon_mtd_session_ttl_seconds"].default
    )
    assert (
        config.internal_destinations_only
        is fields["daemon_mtd_internal_only"].default
    )


def test_from_settings_carries_the_operators_numbers():
    config = MtdConfig.from_settings(
        _settings(
            daemon_mtd_enabled=True,
            daemon_mtd_confidence_floor=0.75,
            daemon_mtd_session_ttl_seconds=600,
            daemon_mtd_internal_only=False,
        )
    )
    assert config.enabled is True
    assert config.confidence_floor == 0.75
    assert config.session_ttl_seconds == 600
    assert config.internal_destinations_only is False


def test_the_config_is_frozen():
    # A band a caller could mutate mid-flight is a band no rule string
    # vouches for: the thresholds a decision fired on must still be the
    # thresholds the row records.
    with pytest.raises(FrozenInstanceError):
        MtdConfig().enabled = True  # type: ignore[misc]
