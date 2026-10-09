"""The fast-path policy's decision matrix, over both tiers.

T1 (post-triage) is the default tier: Gate 1's severity and
recommended-action predicates plus the review threshold on the triage
confidence. T0 (pre-triage) acts on source-native signals only and is a
further opt-in. Every refusal is None; every pass renders its deciding rule.
"""

import pytest

from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.policy import (
    FastPathDecision,
    TriageSignal,
    evaluate_fast_path,
)

pytestmark = pytest.mark.unit

TARGET = "203.0.113.7"


def _finding(
    *,
    src_ips=(TARGET,),
    severity="critical",
    mitre_predictions=None,
    finding_id="f-1",
):
    return {
        "finding_id": finding_id,
        "severity": severity,
        "mitre_predictions": mitre_predictions,
        "entity_context": {"src_ips": list(src_ips)},
    }


def _enabled(**overrides):
    return FastPathConfig(enabled=True, **overrides)


@pytest.mark.parametrize(
    ("severity", "recommended"),
    [
        ("critical", "isolate"),
        ("high", "monitor"),
        ("medium", "block"),
        ("CRITICAL", "ISOLATE"),  # the gate reads lowercased fields
    ],
)
def test_t1_fires_when_gate_one_predicates_and_the_review_threshold_are_met(
    severity, recommended
):
    decision = evaluate_fast_path(
        _finding(), TriageSignal(severity, 0.86, recommended), _enabled()
    )
    assert isinstance(decision, FastPathDecision)
    assert decision.action_type == "rate_limit"
    assert decision.target == TARGET
    assert decision.ttl_seconds == 600
    assert decision.rule == "fast_path.review_threshold=0.85 met (0.86)"


@pytest.mark.parametrize(
    ("severity", "recommended", "confidence"),
    [
        ("medium", "monitor", 0.99),  # no Gate 1 predicate
        ("low", "dismiss", 0.99),
        ("high", "monitor", 0.84),  # below the review threshold
        ("critical", "isolate", 1.2),  # a confidence is a probability
        ("critical", "isolate", float("nan")),
    ],
)
def test_t1_refuses_the_rest_of_the_matrix(severity, recommended, confidence):
    finding = _finding()
    triage = TriageSignal(severity, confidence, recommended)
    assert evaluate_fast_path(finding, triage, _enabled()) is None


def test_a_confidence_at_the_threshold_fires():
    decision = evaluate_fast_path(
        _finding(), TriageSignal("high", 0.85, "monitor"), _enabled()
    )
    assert decision is not None
    assert decision.rule == "fast_path.review_threshold=0.85 met (0.85)"


def test_the_t1_signal_snapshot_carries_what_the_rule_read():
    decision = evaluate_fast_path(
        _finding(finding_id="f-42"), TriageSignal("High", 0.90, "Monitor"), _enabled()
    )
    assert decision is not None
    assert decision.signals == {
        "tier": "t1",
        "finding_id": "f-42",
        "severity": "high",
        "recommended_action": "monitor",
        "confidence": 0.90,
    }


def test_the_decision_carries_the_configured_ttl():
    decision = evaluate_fast_path(
        _finding(),
        TriageSignal("critical", 0.9, "isolate"),
        _enabled(default_ttl_seconds=120),
    )
    assert decision is not None
    assert decision.ttl_seconds == 120


def test_t0_fires_on_source_native_critical_with_a_predicted_technique():
    finding = _finding(severity="critical", mitre_predictions={"T1486": 0.9})
    decision = evaluate_fast_path(finding, None, _enabled(pre_triage_enabled=True))
    assert decision is not None
    assert decision.action_type == "rate_limit"
    assert decision.rule == "fast_path.pre_triage_source_severity=critical"
    assert decision.signals == {
        "tier": "t0",
        "finding_id": "f-1",
        "source_severity": "critical",
        "mitre_predictions": {"T1486": 0.9},
    }


@pytest.mark.parametrize(
    ("severity", "mitre"),
    [
        ("high", {"T1486": 0.9}),  # not the top band
        ("critical", {}),  # no predicted technique
        ("critical", None),
        ("", None),
    ],
)
def test_t0_refuses_narrower_predicates(severity, mitre):
    finding = _finding(severity=severity, mitre_predictions=mitre)
    assert evaluate_fast_path(finding, None, _enabled(pre_triage_enabled=True)) is None


def test_t0_stays_off_unless_its_tier_is_enabled():
    finding = _finding(severity="critical", mitre_predictions={"T1486": 0.9})
    assert evaluate_fast_path(finding, None, _enabled()) is None


def test_t0_backstops_a_t1_refusal_when_enabled():
    # The tiers run in order: T1 first; T0's source-native net fires only
    # when the operator turned it on and T1 did not act.
    finding = _finding(severity="critical", mitre_predictions={"T1486": 0.9})
    low_confidence = TriageSignal("critical", 0.20, "monitor")
    decision = evaluate_fast_path(
        finding, low_confidence, _enabled(pre_triage_enabled=True)
    )
    assert decision is not None
    assert decision.signals["tier"] == "t0"


@pytest.mark.parametrize(
    "triage",
    [TriageSignal("critical", 0.99, "isolate"), None],
)
def test_a_disabled_config_yields_none_for_every_input(triage):
    finding = _finding(severity="critical", mitre_predictions={"T1486": 0.9})
    for config in (FastPathConfig(), FastPathConfig(pre_triage_enabled=True)):
        assert evaluate_fast_path(finding, triage, config) is None


@pytest.mark.parametrize(
    "src_ips",
    [
        [],  # no candidates
        [""],  # not an address
        ["  "],
        ["ftp.example.com"],  # a name, not an address
        ["127.0.0.1"],  # loopback
        ["0.0.0.0"],  # unspecified
        ["224.0.0.1"],  # multicast
        ["169.254.1.1"],  # link-local
        ["240.0.0.1"],  # reserved
    ],
)
def test_a_target_the_discipline_refuses_yields_no_action(src_ips):
    finding = _finding(src_ips=src_ips)
    triage = TriageSignal("critical", 0.9, "isolate")
    assert evaluate_fast_path(finding, triage, _enabled()) is None


def test_a_finding_without_entity_context_has_no_target():
    triage = TriageSignal("critical", 0.9, "isolate")
    decision = evaluate_fast_path({"finding_id": "f-1"}, triage, _enabled())
    assert decision is None


def test_an_ipv4_mapped_ipv6_target_unrolls():
    finding = _finding(src_ips=["::ffff:203.0.113.7"])
    decision = evaluate_fast_path(
        finding, TriageSignal("critical", 0.9, "isolate"), _enabled()
    )
    assert decision is not None
    assert decision.target == TARGET


def test_the_first_routable_ip_wins():
    finding = _finding(src_ips=["224.0.0.1", TARGET])
    decision = evaluate_fast_path(
        finding, TriageSignal("critical", 0.9, "isolate"), _enabled()
    )
    assert decision is not None
    assert decision.target == TARGET


def test_a_target_at_its_cap_is_refused():
    triage = TriageSignal("critical", 0.9, "isolate")
    live = {TARGET: 1}
    assert evaluate_fast_path(_finding(), triage, _enabled(), live) is None


def test_cap_headroom_still_fires():
    triage = TriageSignal("critical", 0.9, "isolate")
    decision = evaluate_fast_path(
        _finding(),
        triage,
        _enabled(max_speculative_per_target=2),
        active_speculative_by_target={TARGET: 1},
    )
    assert decision is not None


def test_the_cap_counts_only_the_same_target():
    triage = TriageSignal("critical", 0.9, "isolate")
    decision = evaluate_fast_path(
        _finding(),
        triage,
        _enabled(),
        active_speculative_by_target={"198.51.100.1": 3},
    )
    assert decision is not None


def test_an_empty_allowlist_refuses_both_tiers():
    config = _enabled(
        pre_triage_enabled=True, allowed_action_types=frozenset({"tarpit"})
    )
    finding = _finding(severity="critical", mitre_predictions={"T1486": 0.9})
    assert (
        evaluate_fast_path(finding, TriageSignal("critical", 0.9, "isolate"), config)
        is None
    )
    assert evaluate_fast_path(finding, None, config) is None


def test_the_same_inputs_yield_the_same_decision():
    # Purity: the decision varies with nothing but its inputs.
    triage = TriageSignal("critical", 0.9, "isolate")
    first = evaluate_fast_path(_finding(), triage, _enabled())
    second = evaluate_fast_path(_finding(), triage, _enabled())
    assert first == second
