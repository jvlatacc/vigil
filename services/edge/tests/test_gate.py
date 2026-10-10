"""Decision gate acceptance suite: expired bundle -> Tier 0, malformed SLM
output -> deterministic-only, caps exhausted -> hold, SLM may lower but never
raise, every decision parseable with a named actor."""

from datetime import UTC, datetime

from services.edge.gate.gate import Outcome, SlmVerdict, decide, decision_rule_string
from services.edge.tests._fixtures import (
    NODE_ID,
    FakeCaps,
    make_bundle,
    make_observation,
)

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def verdict(confidence: float, *, wellformed: bool = True) -> SlmVerdict:
    return SlmVerdict(
        confidence=confidence,
        model_id="qwen2.5:1.5b",
        model_digest="sha256:" + "b" * 64,
        classification="malicious" if confidence >= 0.9 else "uncertain",
        evidence="c2 beacon cadence",
        wellformed=wellformed,
    )


def test_high_severity_rule_executes_within_band() -> None:
    decision = decide(
        make_observation(),
        make_bundle(),
        None,
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.EXECUTE
    assert decision.action is not None
    assert decision.action.action_type == "block_ip"
    assert decision.action.target == "203.0.113.55"
    assert decision.action.executor == "nftables"  # first allowed match in the bundle
    assert decision.action.ttl_seconds == 900  # min(default 900, max 3600)
    assert decision.confidence == 0.95  # deterministic floor for "high"


def test_expired_bundle_journals_at_tier0() -> None:
    late = datetime(2026, 10, 20, 0, 0, 0, tzinfo=UTC)
    decision = decide(
        make_observation(),
        make_bundle(),
        verdict(0.99),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=late,
    )
    assert decision.outcome is Outcome.JOURNAL_ONLY
    assert decision.tier.value == 0
    assert "tier=tier0" in decision.rule_string
    assert decision.action is None


def test_malformed_slm_output_degrades_to_deterministic() -> None:
    # Model says 0.10 but malformed: the verdict is discarded wholesale and the
    # deterministic floor (0.95 for high) stands.
    decision = decide(
        make_observation(),
        make_bundle(),
        verdict(0.10, wellformed=False),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.EXECUTE
    assert decision.confidence == 0.95


def test_slm_can_lower_confidence_into_a_hold() -> None:
    decision = decide(
        make_observation(),
        make_bundle(),
        verdict(0.50),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.HOLD
    assert decision.reason == "below_escalate_band"
    assert decision.confidence == 0.50


def test_slm_can_lower_below_auto_act_but_above_escalate() -> None:
    decision = decide(
        make_observation(),
        make_bundle(),
        verdict(0.88),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.HOLD
    assert decision.reason == "below_auto_act_band"


def test_slm_cannot_raise_above_deterministic_floor() -> None:
    # Medium floor is 0.85; model claims 0.99. min() keeps 0.85 -> the
    # medium rule stays in the escalate band (hold), not auto-act.
    payload_medium = make_bundle(
        rules=[
            {
                "rule_id": "lateral-medium",
                "match": {
                    "direction": "egress",
                    "ioc_set": "c2-active",
                    "dest_kind": "ip",
                },
                "severity_floor": "medium",
            }
        ]
    )
    decision = decide(
        make_observation(),
        payload_medium,
        verdict(0.99),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.HOLD
    assert decision.reason == "below_auto_act_band"
    assert decision.confidence == 0.85


def test_caps_exhausted_holds_never_drops() -> None:
    decision = decide(
        make_observation(),
        make_bundle(),
        None,
        caps=FakeCaps(per_hour=6),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.HOLD
    assert decision.reason == "cap_exhausted"
    assert "cap_exhausted" in decision.rule_string

    decision2 = decide(
        make_observation(),
        make_bundle(),
        None,
        caps=FakeCaps(active=24),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision2.outcome is Outcome.HOLD
    assert decision2.reason == "cap_exhausted"


def test_no_rule_match_journals_only() -> None:
    decision = decide(
        make_observation(dest_ip="198.51.100.1"),
        make_bundle(),
        None,
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.outcome is Outcome.JOURNAL_ONLY
    assert decision.reason == "no_rule_match"


def test_tier1_ignores_the_model_exact_iocs_only() -> None:
    bundle = make_bundle(autonomy_tier="tier1")
    decision = decide(
        make_observation(),
        bundle,
        verdict(0.10),
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    # At Tier 1 the model is not consulted: the deterministic floor stands and
    # the signed IOC rule executes.
    assert decision.outcome is Outcome.EXECUTE
    assert decision.confidence == 0.95


def test_action_not_in_allowed_list_holds() -> None:
    payload = make_bundle(
        allowed_actions=[{"action_type": "block_domain", "executor": "nftables"}]
    )
    decision = decide(
        make_observation(), payload, None, caps=FakeCaps(), node_id=NODE_ID, now=NOW
    )
    assert decision.outcome is Outcome.HOLD
    assert decision.reason == "no_allowed_action"


def test_every_decision_names_actor_and_parseable_rule() -> None:
    decision = decide(
        make_observation(),
        make_bundle(),
        None,
        caps=FakeCaps(),
        node_id=NODE_ID,
        now=NOW,
    )
    assert decision.actor == f"edge:{NODE_ID}@v7"
    assert decision.rule_string.startswith("edge.c2-egress-active tier=tier2 conf=")
    parsed = dict(token.split("=", 1) for token in decision.rule_string.split()[1:])
    assert parsed["tier"] == "tier2"
    assert parsed["conf"] == "0.95"


def test_rule_string_helper_reason_form() -> None:
    from services.edge.gate.tiers import AutonomyTier

    s = decision_rule_string(
        rule_id=None, tier=AutonomyTier.TIER_0, confidence=None, reason="tier0"
    )
    assert s == "edge.observe tier=tier0 reason=tier0"
