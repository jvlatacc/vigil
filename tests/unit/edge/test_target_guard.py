"""The pre-executor guard: structural floor, signed categories, fail-closed parsing."""

from __future__ import annotations

import json

import pytest

from core.edge.policy import PolicyPack, parse_policy
from core.edge.target_guard import TargetGuard

from .helpers import NOW, policy_doc


def _pack(**overrides) -> PolicyPack:
    parsed = parse_policy(json.dumps(policy_doc(**overrides)).encode(), now=NOW)
    assert parsed.ok and parsed.pack is not None
    return parsed.pack


def make_guard(pack: PolicyPack | None = None, **categories) -> TargetGuard:
    """A guard for a parsed pack, with per-category configured addresses."""
    return TargetGuard.from_pack(
        pack or _pack(),
        self_addresses=categories.get("self_addresses", ()),
        gateway_addresses=categories.get("gateway_addresses", ()),
        control_plane_addresses=categories.get("control_plane_addresses", ()),
        dns_resolvers=categories.get("dns_resolvers", ()),
    )


class TestClearTargets:
    def test_public_addresses_are_clear(self):
        guard = make_guard(
            gateway_addresses=("192.168.1.1",),
            control_plane_addresses=("10.20.0.0/24",),
            dns_resolvers=("10.0.0.53",),
        )
        assert guard.check("198.51.100.7") is None
        assert guard.check("203.0.113.7") is None
        assert guard.check("2606:4700:4700::1111") is None

    def test_whitespace_around_the_target_is_parsed(self):
        assert make_guard().check(" 198.51.100.7 ") is None

    def test_rfc1918_is_not_protected_by_being_private(self):
        # Lateral movement is exactly what the guard exists to allow blocking:
        # a private-range attacker is blockable unless a configured category
        # names their address (the gateway lives in RFC1918 too).
        assert make_guard().check("192.168.5.23") is None


class TestStructuralFloor:
    @pytest.mark.parametrize("target", ["127.0.0.1", "127.8.9.10", "::1"])
    def test_loopback_is_refused(self, target):
        reason = make_guard().check(target)
        assert reason is not None and reason.startswith("self (loopback")

    def test_link_local_is_refused(self):
        guard = make_guard()
        assert "link-local" in (guard.check("169.254.169.254") or "")
        assert "link-local" in (guard.check("fe80::1") or "")

    def test_multicast_and_reserved_are_refused(self):
        guard = make_guard()
        assert "multicast" in (guard.check("224.0.0.1") or "")
        assert "reserved" in (guard.check("240.0.0.1") or "")

    def test_wardens_own_address_is_refused(self):
        guard = make_guard(self_addresses=("198.51.100.2",))
        assert guard.check("198.51.100.2") == "self (198.51.100.2)"

    def test_floor_survives_a_pack_that_lists_no_category(self):
        # protected_targets=[] — no signed category is active, yet the
        # structural floor and the node's own address still refuse.
        guard = make_guard(_pack(protected=[]), self_addresses=("198.51.100.2",))
        assert guard.check("127.0.0.1") is not None
        assert guard.check("198.51.100.2") is not None
        assert guard.check("169.254.0.1") is not None
        assert guard.check("198.51.100.7") is None


class TestSignedCategories:
    def test_configured_gateway_is_refused(self):
        guard = make_guard(gateway_addresses=("192.168.1.1",))
        assert guard.check("192.168.1.1") == "gateway (192.168.1.1)"

    def test_configured_resolvers_are_refused(self):
        guard = make_guard(dns_resolvers=("10.0.0.53", "fde0:53::1"))
        assert guard.check("10.0.0.53") is not None
        assert guard.check("fde0:53::1") is not None

    def test_control_plane_network_is_refused_by_membership(self):
        guard = make_guard(control_plane_addresses=("10.20.0.0/24",))
        assert guard.check("10.20.0.4") == "control_plane (10.20.0.4)"
        assert guard.check("10.20.1.4") is None

    def test_a_pack_omitting_a_category_unguards_its_configured_set(self):
        # The signed category list gates the configured external sets: a pack
        # that omits "gateway" lifts that protection — and can never lift the
        # structural floor with it.
        guard = make_guard(
            _pack(protected=["self", "control_plane", "dns_resolvers"]),
            gateway_addresses=("192.168.1.1",),
        )
        assert guard.check("192.168.1.1") is None
        assert guard.check("127.0.0.1") is not None


class TestFailClosedParsing:
    def test_mapped_ipv6_form_of_a_protected_address_is_refused(self):
        guard = make_guard(self_addresses=("198.51.100.2",))
        # The v4 address hiding in a v6 literal must not slip past the guard.
        assert "loopback" in (guard.check("::ffff:127.0.0.1") or "")
        assert "self" in (guard.check("::ffff:198.51.100.2") or "")

    def test_unparseable_target_is_refused(self):
        guard = make_guard()
        assert "unparseable" in (guard.check("not-an-ip") or "")
        assert "unparseable" in (guard.check("evil.example.com") or "")

    def test_sloppy_network_configuration_raises(self):
        # Host bits set — fail the configuration, not the node.
        with pytest.raises(ValueError, match="10.0.0.1/8"):
            make_guard(control_plane_addresses=("10.0.0.1/8",))
