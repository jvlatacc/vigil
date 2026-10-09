"""Unit tests for the Fast-Path policy gate — one case per precedence rule.

No ``no_db`` fixture seam is needed here, and that is the point under test:
the gate imports nothing that can reach a database or a model (lint-imports
enforces the same for the package), so every case below runs on plain
constructed inputs. What the seam patches in the approval suite, the gate
never imports at all.
"""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from core.response.fastpath import (
    FastPathConfig,
    FastPathVerdict,
    GateCounters,
    evaluate,
    record_decision,
)


@pytest.fixture(autouse=True)
def _fresh_counter():
    """Reset the lazy counter cache per test: once a meter is stubbed in,
    the module global would otherwise keep it for the whole session and the
    swallow test would pass vacuously."""
    with patch("core.response.fastpath.gate._verdicts_counter", None):
        yield


def _finding(**overrides):
    """A finding the gate wants to lease on: critical, confident, one actor IP."""
    finding = {
        "finding_id": "f-1",
        "severity": "critical",
        "recommended_action": "isolate",
        "triage_confidence": 0.92,
        "detector": "crowdstrike",
        "entity_context": {
            "src_ips": ["203.0.113.7"],
            "dst_ips": ["10.0.0.5"],
            "hostnames": [],
            "usernames": [],
            "domains": [],
            "file_hashes": [],
        },
    }
    finding.update(overrides)
    return finding


def _live_config(**overrides):
    """Apply-on config: enabled, not shadow. The kill-switch default is what
    ships; tests that need a lease decision say so explicitly."""
    return FastPathConfig(enabled=True, shadow_mode=False, **overrides)


def _assert_complete(decision):
    """The audit contract every verdict owes adjudication: the rule that
    fired and the observed values frozen at gate time."""
    assert decision.decision_rule
    assert "severity" in decision.observed
    assert "confidence" in decision.observed
    assert decision.observed["detector"]


class TestAllowlist:
    """(a) deny_targets outranks every detection — even critical."""

    def test_deny_target_beats_critical_detection(self):
        config = _live_config(deny_targets=frozenset({"203.0.113.7"}))
        decision = evaluate(_finding(), config)
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.deny_targets" in decision.decision_rule
        assert "203.0.113.7" in decision.decision_rule
        _assert_complete(decision)

    def test_deny_match_is_case_insensitive(self):
        finding = _finding(
            entity_context={"src_ips": [], "hostnames": ["DB-Prod-01.corp"]}
        )
        config = _live_config(deny_targets=frozenset({"db-prod-01.corp"}))
        decision = evaluate(finding, config)
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "deny_targets" in decision.decision_rule

    def test_allowlist_guards_the_lease_target_only(self):
        """The allowlist protects principals from being leased against — it
        does not suppress containment of an unprotected attacker elsewhere
        in the finding's entity context."""
        config = _live_config(deny_targets=frozenset({"db-prod-01.corp"}))
        decision = evaluate(_finding(), config)
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE
        assert decision.target == "203.0.113.7"


class TestKillSwitch:
    """(b) enabled=False decides nothing — a decision, not a silence."""

    def test_disabled_gate_never_leases(self):
        decision = evaluate(_finding(), FastPathConfig(enabled=False))
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert decision.decision_rule == "fastpath.enabled=False"
        _assert_complete(decision)

    def test_disabled_gate_wins_over_shadow(self):
        """The kill switch outranks shadow recording: off means off."""
        decision = evaluate(_finding(), FastPathConfig(enabled=False, shadow_mode=True))
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert decision.decision_rule == "fastpath.enabled=False"


class TestShadowMode:
    """(c) Shadow stamps the outcome — it neither forces leases nor skips
    the checks a real run would face."""

    def test_shadow_marks_the_lease(self):
        decision = evaluate(_finding(), FastPathConfig(enabled=True, shadow_mode=True))
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE
        assert decision.is_shadow is True
        assert decision.action_type == "rate_limit"
        assert decision.ttl_seconds == 300
        _assert_complete(decision)

    def test_shadow_does_not_bypass_caps(self):
        config = FastPathConfig(enabled=True, shadow_mode=True)
        decision = evaluate(
            _finding(), config, GateCounters(active_leases_for_entity=1)
        )
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "max_leases_per_entity" in decision.decision_rule

    def test_shadow_does_not_force_leases(self):
        """A shadow run records what the real gate would do — an ineligible
        finding stays ineligible, or the replay data would be noise."""
        config = FastPathConfig(enabled=True, shadow_mode=True)
        decision = evaluate(_finding(severity="medium"), config)
        assert decision.verdict is FastPathVerdict.NO_ACTION


class TestCaps:
    """(d) Each cap blocks on its own; the rule names which one fired."""

    def test_per_entity_cap_blocks(self):
        config = _live_config(max_leases_per_entity=1)
        decision = evaluate(
            _finding(), config, GateCounters(active_leases_for_entity=1)
        )
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.max_leases_per_entity=1" in decision.decision_rule
        _assert_complete(decision)

    def test_per_entity_cap_under_limit_leases(self):
        config = _live_config(max_leases_per_entity=2)
        decision = evaluate(
            _finding(), config, GateCounters(active_leases_for_entity=1)
        )
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE

    def test_per_window_cap_blocks(self):
        config = _live_config(max_leases_per_window=20)
        decision = evaluate(_finding(), config, GateCounters(leases_in_window=20))
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.max_leases_per_window=20" in decision.decision_rule
        _assert_complete(decision)

    def test_anti_flap_blocks_within_the_floor(self):
        config = _live_config(anti_flap_rollback_floor_seconds=600)
        decision = evaluate(
            _finding(), config, GateCounters(seconds_since_last_rollback=599.0)
        )
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.anti_flap_rollback_floor_seconds=600" in decision.decision_rule
        _assert_complete(decision)

    def test_anti_flap_releases_at_the_floor(self):
        config = _live_config(anti_flap_rollback_floor_seconds=600)
        decision = evaluate(
            _finding(), config, GateCounters(seconds_since_last_rollback=600.0)
        )
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE


class TestEligibility:
    """(e) A known principal, a severity with a floor, the confidence to
    clear it, an action type the config still allows."""

    def test_unknown_entity_class_never_leases(self):
        decision = evaluate(_finding(entity_context={}), _live_config())
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.entity_class=unknown" in decision.decision_rule
        _assert_complete(decision)

    def test_non_principal_entity_context_is_unknown(self):
        """dst_ips and file_hashes are not principals: nothing to contain."""
        finding = _finding(
            entity_context={"dst_ips": ["10.0.0.5"], "file_hashes": ["abc123"]}
        )
        decision = evaluate(finding, _live_config())
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "entity_class=unknown" in decision.decision_rule

    def test_severity_outside_the_band_is_ineligible(self):
        decision = evaluate(
            _finding(severity="medium", triage_confidence=0.99), _live_config()
        )
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "not in allowed_severities" in decision.decision_rule

    def test_critical_below_floor_blocked(self):
        decision = evaluate(_finding(triage_confidence=0.69), _live_config())
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "critical_action_floor" in decision.decision_rule
        _assert_complete(decision)

    def test_high_severity_maps_to_challenge_at_floor(self):
        decision = evaluate(
            _finding(severity="high", triage_confidence=0.80), _live_config()
        )
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE
        assert decision.action_type == "challenge"
        assert "high_action_floor" in decision.decision_rule

    def test_confidence_out_of_range_is_never_above_the_floor(self):
        """A confidence is a probability; 1.5 is inflation, not confidence."""
        decision = evaluate(_finding(triage_confidence=1.5), _live_config())
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "fastpath.confidence_range" in decision.decision_rule

    def test_missing_confidence_defaults_like_the_processor(self):
        """The processor reads triage_confidence with a 0.5 default; the
        gate reads the same field the same way, and 0.5 clears no floor."""
        finding = _finding()
        del finding["triage_confidence"]
        decision = evaluate(finding, _live_config())
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "action_floor" in decision.decision_rule

    def test_action_type_removed_from_vocabulary_blocks(self):
        config = _live_config(allowed_action_types=frozenset({"challenge"}))
        decision = evaluate(_finding(), config)  # critical maps to rate_limit
        assert decision.verdict is FastPathVerdict.NO_ACTION
        assert "not in allowed_action_types" in decision.decision_rule
        _assert_complete(decision)


class TestLease:
    """(f) The lease earns itself: mapped action, clamped TTL, complete
    observed mirror."""

    def test_critical_finding_issues_rate_limit_lease(self):
        decision = evaluate(_finding(), _live_config())
        assert decision.verdict is FastPathVerdict.ISSUE_LEASE
        assert decision.action_type == "rate_limit"
        assert decision.target == "203.0.113.7"
        assert decision.ttl_seconds == 300
        assert decision.is_shadow is False
        assert "critical_action_floor" in decision.decision_rule
        assert "0.90" in decision.decision_rule or "0.70" in decision.decision_rule
        _assert_complete(decision)
        assert decision.observed["severity"] == "critical"
        assert decision.observed["confidence"] == 0.92
        assert decision.observed["finding_id"] == "f-1"

    def test_ttl_clamped_to_max(self):
        decision = evaluate(_finding(), _live_config(default_ttl_seconds=5000))
        assert decision.ttl_seconds == 900

    def test_ttl_clamped_to_min(self):
        decision = evaluate(_finding(), _live_config(default_ttl_seconds=10))
        assert decision.ttl_seconds == 60

    def test_decision_is_immutable(self):
        decision = evaluate(_finding(), _live_config())
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.verdict = FastPathVerdict.NO_ACTION


class TestMetrics:
    """The verdict counter is best-effort and never loses a decision."""

    def test_record_decision_counts_verdicts(self):
        counter = MagicMock()
        meter = MagicMock()
        meter.create_counter.return_value = counter
        with patch("core.response.fastpath.gate.get_meter", return_value=meter):
            record_decision(evaluate(_finding(), _live_config()))
        counter.add.assert_called_once()
        args, _ = counter.add.call_args
        assert args[0] == 1
        assert args[1]["verdict"] == "issue_lease"
        assert args[1]["shadow"] == "False"

    def test_record_decision_swallows_counter_errors(self):
        counter = MagicMock()
        counter.add.side_effect = RuntimeError("otel down")
        meter = MagicMock()
        meter.create_counter.return_value = counter
        with patch("core.response.fastpath.gate.get_meter", return_value=meter):
            record_decision(evaluate(_finding(), _live_config()))
