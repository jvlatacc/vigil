"""AC8 — shipped defaults are inert, and every env key reaches its field.

A compose up with no deception configuration must behave exactly like the
pre-feature daemon: posture off, backend dry-run, no env key undocumented.
"""

import pytest

from core.deception.backends import DryRunBackend, build_backend
from core.deception.config import DeceptionConfig, parse_allowlist_entries
from core.response.config import ResponseConfig

pytestmark = pytest.mark.unit


class TestResponseConfigDefaults:
    def test_the_honey_fields_ship_disabled(self):
        config = ResponseConfig()
        assert config.honey_route_enabled is False
        assert config.honey_route_floor == 0.80
        assert config.honey_route_ttl_seconds == 3600

    def test_the_deny_bands_keep_their_values(self):
        config = ResponseConfig()
        assert config.confidence_threshold == 0.90
        assert config.review_threshold == 0.85
        assert config.monitor_threshold == 0.70
        assert config.critical_action_floor == 0.70
        assert config.high_action_floor == 0.80


class TestDeceptionConfigDefaults:
    def test_shipped_defaults_are_inert(self):
        config = DeceptionConfig()
        assert config.enabled is False
        assert config.backend == "dry_run"
        assert config.kill_switch is False

    def test_the_safety_rails_have_defaults(self):
        config = DeceptionConfig()
        assert config.honey_route_floor == 0.80
        assert config.ttl_seconds == 3600
        assert config.max_duration_seconds == 86400
        assert config.min_observations == 3
        assert config.window_seconds == 3600


class TestFromSettings:
    def test_every_env_key_reaches_its_field(self):
        class _Settings:
            daemon_deception_enabled = True
            daemon_deception_backend = "controller"
            daemon_honey_route_floor = 0.66
            daemon_honey_route_ttl = 600
            daemon_honey_route_max_duration = 7200
            daemon_honey_route_min_observations = 5
            daemon_honey_route_window = 1800
            daemon_deception_kill_switch = True
            daemon_deception_allowlist = "10.0.0.0/8, 192.0.2.4"

        config = DeceptionConfig.from_settings(_Settings())
        assert config.enabled is True
        assert config.backend == "controller"
        assert config.honey_route_floor == 0.66
        assert config.ttl_seconds == 600
        assert config.max_duration_seconds == 7200
        assert config.min_observations == 5
        assert config.window_seconds == 1800
        assert config.kill_switch is True
        assert config.allowlist == "10.0.0.0/8, 192.0.2.4"


class TestAllowlistParsing:
    def test_a_mixed_list_parses_its_valid_entries(self):
        networks = parse_allowlist_entries("192.0.2.4, 10.0.0.0/8, not-an-ip")
        assert len(networks) == 2
        assert any(str(n) == "10.0.0.0/8" for n in networks)
        assert any(str(n) == "192.0.2.4/32" for n in networks)

    def test_a_host_bit_outside_its_mask_is_not_strict(self):
        networks = parse_allowlist_entries("10.0.4.25/8")
        assert [str(n) for n in networks] == ["10.0.0.0/8"]

    def test_an_empty_string_parses_to_nothing(self):
        assert parse_allowlist_entries("") == ()
        assert parse_allowlist_entries(None) == ()


class TestBackendFactory:
    def test_dry_run_is_the_buildable_default(self):
        assert isinstance(build_backend("dry_run"), DryRunBackend)

    def test_the_controller_backend_ships_in_pr2(self):
        # Named in the spine, shipped with the decoy-controller slice:
        # building it is the default path once an operator points Vigil at
        # the controller (unconfigured construction is allowed; calls fail
        # closed without credentials — see test_controller_backend.py).
        from core.deception.backends import ControllerBackend

        assert isinstance(build_backend("controller"), ControllerBackend)

    def test_an_unknown_backend_fails_at_construction(self):
        with pytest.raises(ValueError, match="Unknown deception steering backend"):
            build_backend("carrier-pigeon")
