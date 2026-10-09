"""Never-quarantine parsing and matching decide on the target, not the teller.

The environment floor is evaluated before any operator row, and the first
matching rule wins — the row's reason records the rule it was decided by.
"""

import pytest

from core.response.config import ResponseConfig
from core.response.protected_targets import (
    ORIGIN_ENV,
    ORIGIN_OPERATOR,
    ProtectedTarget,
    current_rules,
    env_floor_rules,
    invariant_hold,
    match_target,
    parse_entries,
    parse_entry,
)

pytestmark = pytest.mark.unit


def _rule(entry: str, origin: str = ORIGIN_OPERATOR) -> ProtectedTarget:
    rule = parse_entry(entry, origin, reason="because", created_by="pytest")
    assert rule is not None
    return rule


def _operator_row(kind: str, value: str) -> ProtectedTarget:
    return ProtectedTarget(
        kind=kind,
        value=value,
        origin=ORIGIN_OPERATOR,
        reason="wider operator range",
        created_by="pytest",
    )


class TestParseEntry:
    def test_an_ip_entry_matches_its_address(self):
        rule = _rule("ip:10.0.0.5", ORIGIN_ENV)
        assert match_target("block_ip", "10.0.0.5", (rule,)) is rule

    def test_a_cidr_entry_contains_its_addresses(self):
        rule = _rule("cidr:10.0.8.0/22", ORIGIN_ENV)
        assert match_target("block_ip", "10.0.11.9", (rule,)) is rule

    def test_a_hostname_glob_ignores_case(self):
        rule = _rule("hostname_glob:*.Corp.Example", ORIGIN_ENV)
        assert match_target("isolate_host", "dns.CORP.example", (rule,)) is rule

    def test_a_role_entry_matches_a_target_naming_the_role(self):
        rule = _rule("role:DOMAIN_CONTROLLER", ORIGIN_ENV)
        assert match_target("isolate_host", "domain_controller", (rule,)) is rule
        assert rule.value == "domain_controller"  # hostnames are case-insensitive

    def test_an_unknown_kind_does_not_parse(self):
        assert parse_entry("subnet:10.0.0.0/8", ORIGIN_OPERATOR) is None

    def test_an_invalid_cidr_does_not_parse(self):
        assert parse_entry("cidr:10.0.0.0/99", ORIGIN_OPERATOR) is None

    def test_an_invalid_ip_does_not_parse(self):
        assert parse_entry("ip:10.0.0.256", ORIGIN_OPERATOR) is None

    def test_an_empty_value_cannot_match_everything(self):
        assert parse_entry("hostname_glob:", ORIGIN_OPERATOR) is None


class TestMatchTarget:
    def test_an_unmatched_target_matches_nothing(self):
        rule = _rule("ip:10.0.0.5", ORIGIN_ENV)
        assert match_target("block_ip", "10.0.0.6", (rule,)) is None

    def test_a_target_with_no_rules_at_all_matches_nothing(self):
        assert match_target("block_ip", "10.0.0.5", ()) is None

    def test_first_match_wins(self):
        wide = _rule("cidr:10.0.0.0/8", ORIGIN_ENV)
        narrow = _rule("ip:10.0.0.5", ORIGIN_OPERATOR)
        matched = match_target("block_ip", "10.0.0.5", (wide, narrow))
        assert matched is wide

    def test_a_similar_address_outside_the_cidr_is_not_a_hit(self):
        # A containment target is matched by address, not by text prefix.
        rule = _rule("cidr:10.0.0.0/24", ORIGIN_ENV)
        assert match_target("block_ip", "10.0.1.50", (rule,)) is None

    def test_an_ipv6_target_matches_its_own_cidr(self):
        rule = _rule("cidr:2001:db8::/48", ORIGIN_ENV)
        assert match_target("block_ip", "2001:db8::1", (rule,)) is rule

    def test_an_ipv4_mapped_ipv6_target_matches_its_ipv4_cidr(self):
        rule = _rule("cidr:10.0.0.0/24", ORIGIN_ENV)
        assert match_target("block_ip", "::ffff:10.0.0.5", (rule,)) is rule


class TestParseEntries:
    def test_env_entries_are_parsed_in_order(self):
        parsed, unparsed = parse_entries(
            ["ip:10.0.0.5", "cidr:10.0.0.0/24"], ORIGIN_ENV
        )
        assert [r.kind for r in parsed] == ["ip", "cidr"]
        assert all(r.origin == ORIGIN_ENV for r in parsed)
        assert unparsed == ()

    def test_an_unparseable_entry_is_reported_not_dropped(self):
        parsed, unparsed = parse_entries(["ip:10.0.0.5", "nope:zzz"], ORIGIN_ENV)
        assert len(parsed) == 1
        assert unparsed == ("nope:zzz",)

    def test_blank_entries_are_skipped(self):
        parsed, unparsed = parse_entries(["  ", "ip:10.0.0.5", ""], ORIGIN_ENV)
        assert len(parsed) == 1
        assert unparsed == ()


class TestInvariantHold:
    def test_a_hold_names_the_rule_it_was_decided_by(self):
        rules = env_floor_rules(ResponseConfig(never_quarantine=("ip:10.0.0.5",)))
        hold = invariant_hold("block_ip", "10.0.0.5", rules)
        assert hold is not None
        assert hold.startswith("approval.protected_target=env:ip:10.0.0.5")

    def test_a_failed_read_holds_containment_whatever_the_target(self):
        rules = current_rules(ResponseConfig(), read_failed=True)
        assert invariant_hold("block_ip", "203.0.113.9", rules) is not None

    def test_an_unparsed_env_entry_holds_containment(self):
        config = ResponseConfig(never_quarantine=("nope:zzz",))
        rules = current_rules(config)
        assert rules.unparsed == ("nope:zzz",)
        assert invariant_hold("block_ip", "203.0.113.9", rules) is not None

    def test_a_non_containment_action_is_never_held(self):
        rules = current_rules(ResponseConfig(), read_failed=True)
        assert invariant_hold("workflow_phase", "anything", rules) is None


class TestCurrentRules:
    def test_the_environment_floor_is_evaluated_before_operator_rows(self):
        config = ResponseConfig(never_quarantine=("ip:10.0.0.5",))
        rules = current_rules(config, [_operator_row("cidr", "10.0.0.0/8")])
        assert rules.ordered[0].origin == ORIGIN_ENV
        assert rules.ordered[0].kind == "ip"
        assert rules.ordered[1].origin == ORIGIN_OPERATOR

    def test_an_env_origin_row_joins_the_floor(self):
        rules = current_rules(
            ResponseConfig(),
            [
                ProtectedTarget(
                    kind="cidr",
                    value="10.0.0.0/8",
                    origin=ORIGIN_ENV,
                    reason="from the environment",
                    created_by="environment",
                )
            ],
        )
        assert all(r.origin == ORIGIN_ENV for r in rules.floor)
        assert rules.operator == ()

    def test_parsed_rules_without_accidents_are_not_fail_closed(self):
        config = ResponseConfig(never_quarantine=("ip:10.0.0.5",))
        assert current_rules(config, []).read_failed is False
        assert current_rules(config, []).unparsed == ()
