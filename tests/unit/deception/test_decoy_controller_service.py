"""Decoy-controller service internals: config, registry, drivers.

Pure unit — the HTTP surface is covered by
tests/integration/test_decoy_controller_api.py. The nftables and cilium
renderers are tested as the pure functions they are: a ruleset or manifest
that drifts from desired state is the driver's only failure mode.
"""

import pytest

from services.decoy_controller.config import (
    DRIVER_MEMORY,
    ControllerConfig,
    parse_decoy_map,
)
from services.decoy_controller.drivers import MemoryDriver, build_driver
from services.decoy_controller.drivers.cilium import (
    build_policy,
    policy_name,
)
from services.decoy_controller.drivers.nftables import (
    render_rule,
    render_ruleset,
)
from services.decoy_controller.registry import (
    RegistryFull,
    Rule,
    RuleRegistry,
)
from tests.unit.deception.fixtures import ATTACKER, VICTIM


def _rule(lease_id="lease-1", **overrides):
    defaults = dict(
        lease_id=lease_id,
        source_ip=ATTACKER,
        destination_ips=(VICTIM,),
        ports=(445,),
        ttl_seconds=3600,
        created_at=100.0,
        expires_at=3700.0,
        ref="",
    )
    defaults.update(overrides)
    return Rule(**defaults)


class TestConfig:
    def test_defaults_are_inert(self, monkeypatch):
        for name in (
            "DECOY_CONTROLLER_DRIVER",
            "DECOY_CONTROLLER_TOKEN",
            "DECOY_CONTROLLER_DECOY_MAP",
        ):
            monkeypatch.delenv(name, raising=False)
        config = ControllerConfig.from_env()
        assert config.driver == DRIVER_MEMORY  # records, touches nothing
        assert config.token == ""  # deny-by-default auth

    def test_unknown_driver_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("DECOY_CONTROLLER_DRIVER", "ebpf-magic")
        config = ControllerConfig.from_env()
        assert config.driver == DRIVER_MEMORY

    def test_parse_decoy_map(self):
        assert parse_decoy_map("445=10.0.5.11,3389=10.0.5.12:3389") == {
            445: "10.0.5.11",
            3389: "10.0.5.12:3389",
        }

    def test_parse_decoy_map_skips_garbage_entries_loudly(self, caplog):
        assert parse_decoy_map("nonsense,445=10.0.5.11,,99999=10.0.5.9") == {
            445: "10.0.5.11"
        }
        assert "nonsense" in caplog.text

    def test_endpoint_for_uses_per_port_override(self):
        config = ControllerConfig(decoy_ip="10.0.5.10", decoy_map="445=10.0.5.11")
        assert config.endpoint_for(445) == ("10.0.5.11", None)
        assert config.endpoint_for(3389) == ("10.0.5.10", None)

    def test_endpoint_for_parses_port_rewrites(self):
        config = ControllerConfig(decoy_map="445=10.0.5.11:2222")
        assert config.endpoint_for(445) == ("10.0.5.11", 2222)

    def test_endpoint_for_handles_bracketed_ipv6(self):
        config = ControllerConfig(
            decoy_ip="fd00:decoy::10",
            decoy_map="445=[fd00:decoy::11]:2222",
        )
        assert config.endpoint_for(445) == ("fd00:decoy::11", 2222)
        assert config.endpoint_for(3389) == ("fd00:decoy::10", None)


class TestRegistry:
    def test_upsert_get_and_all_ordering(self):
        clock = {"now": 1000.0}
        registry = RuleRegistry(clock=lambda: clock["now"])
        registry.upsert(
            lease_id="b",
            source_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445],
            ttl_seconds=60,
        )
        clock["now"] = 1030.0
        registry.upsert(
            lease_id="a",
            source_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[3389],
            ttl_seconds=60,
        )
        assert [r.lease_id for r in registry.all()] == ["b", "a"]  # oldest first

    def test_renewal_keeps_created_at_and_extends_expiry(self):
        clock = {"now": 1000.0}
        registry = RuleRegistry(clock=lambda: clock["now"])
        first = registry.upsert(
            lease_id="l",
            source_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445],
            ttl_seconds=60,
        )
        assert first.created_at == 1000.0
        clock["now"] = 1030.0
        renewed = registry.renew("l", 60)
        assert renewed.created_at == 1000.0
        assert renewed.expires_at == 1090.0

    def test_expiry_and_removal(self):
        clock = {"now": 1000.0}
        registry = RuleRegistry(clock=lambda: clock["now"])
        registry.upsert(
            lease_id="l",
            source_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445],
            ttl_seconds=60,
        )
        assert registry.expired() == []
        clock["now"] = 1060.0
        assert [r.lease_id for r in registry.expired()] == ["l"]
        registry.remove("l")
        assert registry.all() == []

    def test_registry_full_refuses_new_leases_but_renews_existing(self):
        registry = RuleRegistry(max_rules=1, clock=lambda: 0.0)
        registry.upsert(
            lease_id="l1",
            source_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445],
            ttl_seconds=60,
        )
        with pytest.raises(RegistryFull):
            registry.upsert(
                lease_id="l2",
                source_ip=ATTACKER,
                destination_ips=[VICTIM],
                ports=[445],
                ttl_seconds=60,
            )
        registry.renew("l1", 60)  # renewal is not a new lease

    def test_clear_returns_removed_ids(self):
        registry = RuleRegistry(clock=lambda: 0.0)
        for lease_id in ("a", "b"):
            registry.upsert(
                lease_id=lease_id,
                source_ip=ATTACKER,
                destination_ips=[VICTIM],
                ports=[445],
                ttl_seconds=60,
            )
        assert sorted(registry.clear()) == ["a", "b"]
        assert registry.all() == []


class TestMemoryDriver:
    def test_sync_reflects_desired_state(self):
        driver = MemoryDriver()
        refs = driver.sync([_rule("lease-1")])
        assert refs == {"lease-1": "memory:lease-1"}
        assert set(driver.plane) == {"lease-1"}
        driver.sync([])  # removal is exact
        assert driver.plane == {}


class TestNftablesRenderer:
    def test_ipv4_lease_renders_dnat_with_lease_comment(self):
        config = ControllerConfig(decoy_ip="10.0.5.10")
        commands = render_rule(_rule(), config)
        assert len(commands) == 1
        assert (
            f"ip saddr {ATTACKER} ip daddr {VICTIM} tcp dport 445 "
            "dnat ip to 10.0.5.10:445" in commands[0]
        )
        assert 'comment "vigil-lease:lease-1"' in commands[0]

    def test_port_map_rewrites_the_target_port(self):
        config = ControllerConfig(decoy_map="445=10.0.5.11:2222")
        commands = render_rule(_rule(), config)
        assert "dnat ip to 10.0.5.11:2222" in commands[0]

    def test_ruleset_is_flush_plus_chain_plus_every_lease(self):
        config = ControllerConfig()
        ruleset = render_ruleset([_rule("a"), _rule("b")], config)
        assert ruleset.startswith("flush table inet vigildecoy")
        assert "type nat hook prerouting priority" in ruleset
        assert 'comment "vigil-lease:a"' in ruleset
        assert 'comment "vigil-lease:b"' in ruleset

    def test_cross_family_destinations_are_skipped_not_rendered(self):
        # An nft batch mixing families fails whole — one wrong rule would
        # drop every other lease's rules with it.
        config = ControllerConfig(decoy_ip="10.0.5.10")
        rule = _rule(lease_id="v6", source_ip="2001:db8::7", destination_ips=(VICTIM,))
        assert render_rule(rule, config) == []

    def test_ipv6_lease_renders_ip6_family(self):
        config = ControllerConfig(decoy_ip="fd00:decoy::10")
        rule = _rule(
            lease_id="v6",
            source_ip="2001:db8::7",
            destination_ips=("2001:db8::25",),
        )
        commands = render_rule(rule, config)
        assert "ip6 saddr 2001:db8::7 ip6 daddr 2001:db8::25" in commands[0]
        assert "dnat ip6 to [fd00:decoy::10]:445" in commands[0]


class TestCiliumPolicyBuilder:
    def test_policy_name_is_a_valid_k8s_name(self):
        assert policy_name("lease-abc123") == "vigil-decoy-lease-abc123"
        weird = policy_name("LEASE with__weird/../chars!@#")
        assert weird.startswith("vigil-decoy-")
        assert len(weird) <= 63
        assert "/" not in weird

    def test_policy_scopes_to_destinations_and_labels_the_lease(self):
        from services.decoy_controller.drivers.cilium import (
            LABEL_LEASE,
            LABEL_MANAGED,
        )

        policy = build_policy(_rule(), "decoys", "10.0.5.10")
        assert policy["apiVersion"] == "cilium.io/v2"
        assert policy["kind"] == "CiliumLocalRedirectPolicy"
        assert policy["metadata"]["labels"][LABEL_LEASE] == "lease-1"
        assert policy["metadata"]["labels"][LABEL_MANAGED] == ("vigil-decoy-controller")
        assert policy["spec"]["addressMatcher"]["matchIps"] == [f"{VICTIM}/32"]
        assert policy["spec"]["addressMatcher"]["redirectAddress"] == {
            "v4": ["10.0.5.10"]
        }

    def test_ipv6_destinations_are_skipped(self):
        rule = _rule(lease_id="v6", destination_ips=("2001:db8::25",))
        policy = build_policy(rule, "decoys", "10.0.5.10")
        assert policy["spec"]["addressMatcher"]["matchIps"] == []


class TestBuildDriver:
    def test_memory_builds(self):
        config = ControllerConfig(driver=DRIVER_MEMORY)
        assert isinstance(build_driver(config), MemoryDriver)

    def test_cilium_dependency_error_names_the_fix(self, monkeypatch):
        # The kubernetes client must stay scoped to this service; a missing
        # one is a construction-time error with the install path in it.
        import builtins

        real_import = builtins.__import__

        def no_kubernetes(name, *args, **kwargs):
            if name == "kubernetes":
                raise ImportError("No module named 'kubernetes'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_kubernetes)
        config = ControllerConfig(driver="cilium")
        with pytest.raises(RuntimeError, match="services/decoy_controller"):
            build_driver(config)
