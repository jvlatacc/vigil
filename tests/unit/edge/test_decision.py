"""The decision ladder: one test per refusal class, in the brief's order.

Every test decides with injected values — packs parsed from real pack bytes,
a controllable ``now``, a budget built from the envelope — so nothing here
can flake on wall-clock time, and the ladder's purity is itself asserted.
"""

from __future__ import annotations

import builtins
from dataclasses import replace
from datetime import timedelta

import pytest

from core.edge.decision import (
    ACTION_NOT_IN_ENVELOPE,
    BELOW_CONFIDENCE_FLOOR,
    IRREVERSIBLE_NOT_ALLOWED,
    POLICY_EXPIRED,
    PROTECTED_TARGET,
    RATE_CAP_REACHED,
    SLM_DECISIONS_NOT_ALLOWED,
    TTL_EXCEEDS_ENVELOPE,
    LocalTriage,
    decide_local_action,
)
from core.edge.envelope import HourlyBudget, budget_for
from core.edge.policy import EdgeAction, EdgeRule, PolicyPack, parse_policy
from core.edge.signing import deterministic_json
from core.edge.target_guard import TargetGuard
from core.edge.wire import TS_FORMAT

from .helpers import NOW, policy_doc

TARGET = "198.51.100.7"


def make_pack(**overrides) -> PolicyPack:
    """A pack parsed the way a synced node would parse it — real bytes."""
    parsed = parse_policy(deterministic_json(policy_doc(**overrides)), now=NOW)
    assert parsed.ok and parsed.pack is not None
    return parsed.pack


def make_guard(pack: PolicyPack, **categories) -> TargetGuard:
    return TargetGuard.from_pack(
        pack,
        self_addresses=categories.get("self_addresses", ("198.51.100.2",)),
        gateway_addresses=categories.get("gateway_addresses", ("192.168.1.1",)),
        control_plane_addresses=categories.get(
            "control_plane_addresses", ("10.20.0.0/24",)
        ),
        dns_resolvers=categories.get("dns_resolvers", ("10.0.0.53",)),
    )


def decide(
    *,
    pack: PolicyPack | None = None,
    rule: EdgeRule | None = None,
    triage: LocalTriage | None = None,
    target: str = TARGET,
    guard: TargetGuard | None = None,
    budget: HourlyBudget | None = None,
    now=None,
):
    """The ladder with the spec's happy-path defaults; each test overrides
    exactly the rung it is pinning."""
    pack = pack or make_pack()
    rule = rule or pack.rules[0]
    triage = triage or LocalTriage(confidence=0.93, source="sensor")
    return decide_local_action(
        pack,
        rule,
        triage,
        target,
        guard or make_guard(pack),
        budget or budget_for(pack.autonomy_envelope),
        now=now or NOW,
    )


class TestAllowedDecision:
    def test_allowance_carries_the_journal_fields(self):
        decision = decide()
        assert decision.allowed and decision.code is None
        assert decision.policy_version == 42
        assert decision.rule_id == "edge-001"
        assert decision.action == EdgeAction(type="block_ip", ttl_minutes=30)
        assert decision.target == TARGET
        assert decision.confidence == 0.93
        assert decision.triage_source == "sensor"
        # The rendered rule is journal-shaped: rule, source, floor, ttl, cap.
        assert decision.decision_rule == (
            "edge-001 met (sensor 0.93 >= floor 0.90, ttl 30 <= 30, cap 1/5)"
        )

    def test_confidence_at_the_floor_is_allowed(self):
        # "at or above which a rule match acts" — the boundary acts.
        assert decide(triage=LocalTriage(0.90)).allowed

    def test_rule_floor_can_sit_above_the_envelope_floor(self):
        # The effective floor is max(envelope, rule): a stricter rule raises
        # the bar; a looser rule cannot lower it below the envelope.
        pack = make_pack(
            envelope={
                "allowed_actions": ["block_ip"],
                "max_actions_per_hour": 5,
                "max_action_ttl_minutes": 30,
                "require_reversible": True,
                "confidence_floor": 0.70,
                "allow_slm_decisions": False,
            },
        )
        strict_rule = replace(pack.rules[0], min_local_confidence=0.95)
        assert (
            decide(pack=pack, rule=strict_rule, triage=LocalTriage(0.90)).code
            == BELOW_CONFIDENCE_FLOOR
        )
        assert decide(pack=pack, rule=strict_rule, triage=LocalTriage(0.95)).allowed


class TestRefusalClasses:
    def test_action_outside_the_envelope_is_refused(self):
        # The schema enum only ever parses block_ip; the ladder re-checks so
        # a runtime bug or future schema loosening cannot smuggle a type in.
        rule = EdgeRule(
            rule_id="edge-002",
            indicator="ip",
            mitre=("T1071",),
            min_local_confidence=None,
            action=EdgeAction(type="process_kill", ttl_minutes=30),
        )
        decision = decide(rule=rule)
        assert decision.code == ACTION_NOT_IN_ENVELOPE
        assert "action=process_kill" in decision.decision_rule

    def test_confidence_below_the_effective_floor_is_refused(self):
        decision = decide(triage=LocalTriage(0.85))
        assert decision.code == BELOW_CONFIDENCE_FLOOR
        assert decision.decision_rule == "edge.confidence_floor=0.90 not met (0.85)"

    @pytest.mark.parametrize("confidence", [float("nan"), 5.0, -0.5, float("inf")])
    def test_out_of_range_confidence_never_reads_as_high(self, confidence):
        # The approval_requirement precedent: a confidence is a probability;
        # anything else is a caller inflating the number. NaN's comparisons
        # are all False — without the range gate it would read as high.
        decision = decide(triage=LocalTriage(confidence))
        assert decision.code == BELOW_CONFIDENCE_FLOOR
        assert "edge.confidence_range" in decision.decision_rule

    def test_slm_confidence_without_signed_authority_is_refused(self):
        # allow_slm_decisions defaults false: SLM output is advisory. A
        # confidence that arrives SLM-sourced refuses — the ladder never
        # re-labels it as sensor-sourced to let it through.
        decision = decide(triage=LocalTriage(0.99, source="slm"))
        assert decision.code == SLM_DECISIONS_NOT_ALLOWED
        assert "edge.allow_slm_decisions=False" in decision.decision_rule

    def test_slm_confidence_with_signed_authority_is_allowed(self):
        pack = make_pack()
        granted = replace(pack.autonomy_envelope, allow_slm_decisions=True)
        decision = decide(
            pack=replace(pack, autonomy_envelope=granted),
            triage=LocalTriage(0.99, source="slm"),
        )
        assert decision.allowed
        assert "slm 0.99" in decision.decision_rule

    def test_irreversible_action_is_refused(self):
        # The envelope allowlist would have to name the type for the ladder
        # to reach the reversibility rung — which is the point: even a pack
        # that allows a type with no reversible story cannot enforce it while
        # require_reversible holds.
        pack = make_pack()
        widened = replace(
            pack.autonomy_envelope, allowed_actions=("block_ip", "process_kill")
        )
        rule = EdgeRule(
            rule_id="edge-003",
            indicator="ip",
            mitre=(),
            min_local_confidence=None,
            action=EdgeAction(type="process_kill", ttl_minutes=30),
        )
        decision = decide(pack=replace(pack, autonomy_envelope=widened), rule=rule)
        assert decision.code == IRREVERSIBLE_NOT_ALLOWED
        assert "edge.require_reversible=True" in decision.decision_rule

    def test_protected_target_is_refused_when_every_other_check_would_pass(self):
        # Max confidence, allowed action, sane ttl, budget to spare — and the
        # guard still refuses, because the target is the gateway.
        decision = decide(triage=LocalTriage(0.99), target="192.168.1.1")
        assert decision.code == PROTECTED_TARGET
        assert decision.decision_rule == "edge.protected_target=gateway (192.168.1.1)"

    def test_protected_target_refusal_does_not_burn_the_budget(self):
        # The guard runs before the cap: a flood of refusals must not starve
        # legitimate enforcement of the hour's remaining budget.
        pack = make_pack()
        budget = HourlyBudget(limit=1)
        refused = decide(pack=pack, target="192.168.1.1", budget=budget)
        assert refused.code == PROTECTED_TARGET
        assert budget.taken == 0
        assert decide(pack=pack, budget=budget).allowed
        assert budget.taken == 1

    def test_ttl_above_the_ceiling_is_refused(self):
        pack = make_pack()
        long_rule = replace(
            pack.rules[0], action=EdgeAction(type="block_ip", ttl_minutes=60)
        )
        decision = decide(pack=pack, rule=long_rule)
        assert decision.code == TTL_EXCEEDS_ENVELOPE
        assert "edge.max_action_ttl_minutes=30" in decision.decision_rule

    def test_hourly_cap_exhaustion_is_refused(self):
        pack = make_pack()
        rule = pack.rules[0]
        guard = make_guard(pack)
        budget = HourlyBudget(limit=pack.autonomy_envelope.max_actions_per_hour)
        decisions = [
            decide_local_action(
                pack, rule, LocalTriage(0.93), TARGET, guard, budget, now=NOW
            )
            for _ in range(pack.autonomy_envelope.max_actions_per_hour + 1)
        ]
        assert all(d.allowed for d in decisions[:-1])
        assert decisions[-1].code == RATE_CAP_REACHED
        assert (
            f"taken={pack.autonomy_envelope.max_actions_per_hour}"
            in decisions[-1].decision_rule
        )

    def test_budget_wider_than_the_envelope_is_refused(self):
        # A budget not derived via budget_for cannot widen the signed cap.
        pack = make_pack()
        decision = decide(pack=pack, budget=HourlyBudget(limit=50))
        assert decision.code == RATE_CAP_REACHED
        assert "budget=50" in decision.decision_rule

    def test_expired_policy_is_refused_at_the_boundary(self):
        # Controllable clock: decide AT not_after — no sleeps, no wall clock.
        pack = make_pack()
        decision = decide(pack=pack, now=pack.not_after)
        assert decision.code == POLICY_EXPIRED
        assert f"edge.policy_not_after={pack.not_after.strftime(TS_FORMAT)}" in (
            decision.decision_rule
        )

    def test_policy_one_second_before_expiry_is_allowed(self):
        pack = make_pack()
        assert decide(pack=pack, now=pack.not_after - timedelta(seconds=1)).allowed

    def test_the_ladder_reports_the_first_gate_in_its_order(self):
        # A candidate violating three gates at once reports the earliest:
        # allowlist before confidence, confidence before the guard.
        bad_rule = EdgeRule(
            rule_id="edge-004",
            indicator="ip",
            mitre=(),
            min_local_confidence=None,
            action=EdgeAction(type="process_kill", ttl_minutes=30),
        )
        nan = LocalTriage(float("nan"))
        assert decide(rule=bad_rule, triage=nan, target="127.0.0.1").code == (
            ACTION_NOT_IN_ENVELOPE
        )
        assert (
            decide(rule=make_pack().rules[0], triage=nan, target="127.0.0.1").code
            == BELOW_CONFIDENCE_FLOOR
        )


class TestPurity:
    def test_same_inputs_same_decision(self):
        pack = make_pack()
        first = decide(pack=pack, budget=HourlyBudget(limit=5))
        second = decide(pack=pack, budget=HourlyBudget(limit=5))
        assert first == second

    def test_the_clock_is_injected_not_read(self):
        # If the ladder read the wall clock, a decision could not flip with
        # only the ``now`` argument changing.
        pack = make_pack()
        assert decide(pack=pack, now=NOW).allowed
        assert decide(pack=pack, now=pack.not_after).code == POLICY_EXPIRED

    def test_the_ladder_performs_no_file_io(self, monkeypatch):
        # Close the usual I/O door, then decide: a pure ladder cannot need
        # it. (Not exhaustive — the point is that nothing here reaches out.)
        def no_open(*args, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("decide_local_action performed file I/O")

        monkeypatch.setattr(builtins, "open", no_open)
        pack = make_pack()
        decision = decide(pack=pack)
        assert decision.allowed
