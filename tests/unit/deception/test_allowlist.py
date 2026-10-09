"""The allowlist: sanctioned scanners and shared NAT never get steered."""

import pytest

from tests.unit.deception.fixtures import ATTACKER

from core.deception.allowlist import Allowlist, allowlist_from_config
from core.deception.config import DeceptionConfig

pytestmark = pytest.mark.unit


class TestExemption:
    def test_an_exact_ip_is_exempt(self):
        assert Allowlist(f"{ATTACKER}/32").is_exempt(ATTACKER) is True

    def test_an_address_inside_a_cidr_is_exempt(self):
        assert Allowlist("203.0.113.0/24").is_exempt(ATTACKER) is True

    def test_an_outsider_is_not_exempt(self):
        assert Allowlist("203.0.113.0/24").is_exempt("198.51.100.9") is False

    def test_an_ipv6_entry_is_exempt(self):
        assert Allowlist("2001:db8::/32").is_exempt("2001:db8::1") is True

    def test_an_empty_allowlist_exempts_nothing(self):
        allowlist = Allowlist("")
        assert allowlist.is_exempt(ATTACKER) is False
        assert not allowlist

    def test_an_unparseable_address_is_not_exempt(self):
        assert Allowlist("10.0.0.0/8").is_exempt("n/a") is False

    def test_the_decision_clock_is_accepted_and_ignored(self):
        """now is reserved for a future time-scoped entry shape."""
        assert Allowlist(f"{ATTACKER}").is_exempt(ATTACKER, now=None) is True


class TestFromConfig:
    def test_the_config_string_configures_the_set(self):
        allowlist = allowlist_from_config(
            DeceptionConfig(allowlist="10.0.0.0/8, 192.0.2.4, garbage")
        )
        assert allowlist.is_exempt("10.1.2.3") is True
        assert allowlist.is_exempt("192.0.2.4") is True
        assert allowlist.is_exempt("203.0.113.7") is False
