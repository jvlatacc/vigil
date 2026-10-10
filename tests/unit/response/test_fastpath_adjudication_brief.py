"""The adjudication brief and the verdict parser — the pure half.

Pins what the adjudicator reads and what the review seam parses, with no
database: the brief is a pure render of a committed row's record (id, rule,
TTL, rollback recipe, signal snapshot, simulation label, the verdict
contract and the authority that outranks it), and ``parse_verdict`` reads
exactly the CONCLUDE decisions that name one of the three resolutions —
nothing else, ever, parses as a verdict.
"""

import pytest

from core.response.approval_service import PendingAction
from core.response.fastpath.adjudication import (
    VERDICT_ESCALATE,
    VERDICT_RELEASE,
    VERDICT_RETAIN,
    FastPathVerdict,
    adjudication_hypothesis,
    build_adjudication_brief,
    parse_verdict,
    verdict_from_events,
)

pytestmark = [pytest.mark.unit]


def _row(**overrides) -> PendingAction:
    values = dict(
        action_id="spec-1",
        action_type="rate_limit",
        title="Transient rate limit",
        description="Fast-path containment",
        target="203.0.113.7",
        confidence=0.92,
        reason="Fast path dispatched",
        evidence=["finding f-1"],
        created_at="2026-10-10T00:00:00Z",
        created_by="fast-path",
        requires_approval=False,
        status="speculative",
        parameters={
            "ttl_seconds": 600,
            "expires_at": "2026-10-10T00:10:00+00:00",
            "rule": "fast_path.review_threshold=0.85 met (0.92)",
            "signals": {"tier": "t1", "finding_id": "f-1", "severity": "critical"},
            "rollback": {
                "adapter": "cloudflare",
                "action_type": "rate_limit",
                "target": "203.0.113.7",
                "external_ref": "rs-1:rule-1",
            },
            "simulation": False,
        },
    )
    values.update(overrides)
    return PendingAction(**values)


def _conclude(verdict, **extra):
    payload = {"action": "CONCLUDE", "verdict": verdict}
    payload.update(extra)
    return payload


class TestParseVerdict:
    def test_a_verdict_bearing_conclude_parses(self):
        verdict = parse_verdict(
            _conclude(VERDICT_RELEASE, stated_confidence=0.86, rationale="benign")
        )

        assert verdict == FastPathVerdict(
            verdict=VERDICT_RELEASE, rationale="benign", confidence=0.86
        )

    def test_each_of_the_three_resolutions_parses(self):
        for verdict_value in (VERDICT_RELEASE, VERDICT_ESCALATE, VERDICT_RETAIN):
            assert parse_verdict(_conclude(verdict_value)).verdict == verdict_value

    def test_retain_carries_its_asked_extension(self):
        verdict = parse_verdict(_conclude(VERDICT_RETAIN, retention_seconds=300))

        assert verdict.retention_seconds == 300

    def test_retain_without_an_extension_asks_for_none(self):
        verdict = parse_verdict(_conclude(VERDICT_RETAIN))

        assert verdict.retention_seconds is None

    def test_escalate_carries_its_proposed_action(self):
        verdict = parse_verdict(
            _conclude(
                VERDICT_ESCALATE,
                proposed_full_action={"action_type": "waf_block"},
            )
        )

        assert verdict.proposed_full_action == {"action_type": "waf_block"}

    def test_a_non_conclude_decision_is_not_a_verdict(self):
        assert parse_verdict({"action": "INVESTIGATE", "verdict": "release"}) is None

    def test_a_conclude_without_a_verdict_is_not_a_verdict(self):
        assert parse_verdict({"action": "CONCLUDE", "rationale": "..."}) is None

    def test_an_unknown_verdict_is_not_a_verdict(self):
        assert parse_verdict(_conclude("block")) is None

    def test_a_non_probability_confidence_is_not_read_as_one(self):
        for stated in (1.5, -0.1, "high", None, True):
            verdict = parse_verdict(
                _conclude(VERDICT_RELEASE, stated_confidence=stated)
            )
            assert verdict.confidence is None, stated

    def test_a_non_positive_retention_is_not_read_as_an_extension(self):
        for asked in (0, -300, "long", None):
            verdict = parse_verdict(
                _conclude(VERDICT_RETAIN, retention_seconds=asked)
            )
            assert verdict.retention_seconds is None, asked

    def test_a_non_mapping_is_not_a_verdict(self):
        assert parse_verdict(None) is None
        assert parse_verdict("release") is None


class TestVerdictFromEvents:
    def test_the_last_verdict_bearing_conclude_wins(self):
        events = [
            {"kind": "decision", "payload": {"decision": {"action": "INVESTIGATE"}}},
            {"kind": "decision", "payload": {"decision": _conclude("release")}},
            {
                "kind": "decision",
                "payload": {
                    "decision": _conclude(VERDICT_RETAIN, retention_seconds=120)
                },
            },
        ]

        assert verdict_from_events(events).verdict == VERDICT_RETAIN

    def test_a_ledger_without_a_verdict_parses_to_none(self):
        events = [
            {"kind": "system", "payload": {"event": "started"}},
            {"kind": "decision", "payload": {"decision": {"action": "CONCLUDE"}}},
            {"kind": "decision", "payload": {"decision": _conclude("block")}},
        ]

        assert verdict_from_events(events) is None

    def test_malformed_events_never_raise(self):
        events = [
            {"kind": "decision", "payload": "not-a-mapping"},
            {"kind": "decision", "payload": {"decision": 42}},
            "not-even-a-mapping",
            {},
        ]

        assert verdict_from_events(events) is None


class TestBrief:
    def test_the_brief_carries_the_whole_record(self):
        brief = build_adjudication_brief(_row())

        assert "spec-1" in brief
        assert "203.0.113.7" in brief
        assert "rate_limit" in brief
        assert "fast_path.review_threshold=0.85 met (0.92)" in brief
        assert "600s" in brief
        assert "2026-10-10T00:10:00+00:00" in brief
        assert "f-1" in brief
        assert "rs-1:rule-1" in brief
        # The verdict contract, and the authority that outranks it.
        assert '"release"' in brief
        assert '"escalate"' in brief
        assert '"retain"' in brief
        assert "TTL sweep" in brief

    def test_the_brief_labels_simulated_enforcement(self):
        simulated = _row(parameters={**_row().parameters, "simulation": True})

        brief = build_adjudication_brief(simulated)

        assert "simulated" in brief
        assert "records intent only" in brief

    def test_the_brief_says_the_run_executes_nothing(self):
        brief = build_adjudication_brief(_row())

        assert "You execute\nnothing" in brief

    def test_the_brief_survives_a_row_with_no_record(self):
        bare = _row(parameters={})

        brief = build_adjudication_brief(bare)

        assert bare.action_id in brief
        assert "unrecorded" in brief

    def test_the_hypothesis_names_the_target_and_the_rule(self):
        hypothesis = adjudication_hypothesis(_row())

        assert "203.0.113.7" in hypothesis
        assert "fast_path.review_threshold=0.85 met (0.92)" in hypothesis
        assert "warranted" in hypothesis
