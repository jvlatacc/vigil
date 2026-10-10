"""Synthetic outcome sets through the maturity evidence rules.

No database: the pure core (``classify_run`` → ``accumulate_outcomes`` →
``build_evidence`` → ``is_eligible`` → ``compile_policy``) takes run
observations, so every eligibility semantic the spec pins is testable as a
table of outcomes — an eligible set compiles; insufficient-N, inconsistent,
reopened, and duplicate-heavy sets do not.
"""

from datetime import UTC, datetime

import pytest

from core.policy_compiler.compiler import CompileError, compile_policy
from core.policy_compiler.maturity import (
    DUPLICATE,
    REOPENED,
    ClosureObservation,
    RunObservation,
    accumulate_outcomes,
    build_evidence,
    classify_run,
    is_eligible,
)
from core.policy_compiler.models import PolicyIR

pytestmark = pytest.mark.unit

WORKFLOW = "wf_hunt_cred_stuffing"
SOURCE = "okta.system_log"


def _now() -> datetime:
    return datetime(2026, 10, 9, 20, 0, 0, tzinfo=UTC)


def closure(
    category: str = "resolved",
    *,
    case_closed: bool = True,
    in_window: bool = True,
) -> ClosureObservation:
    return ClosureObservation(
        category=category, case_closed=case_closed, in_window=in_window
    )


def run(
    outcome: str | None = "resolved",
    *,
    run_id: str = "wfr-20261001-00000001",
    techniques: frozenset[str] = frozenset({"T1110.003"}),
    entity_types: frozenset[str] = frozenset({"src_ip"}),
    severity: str | None = "high",
    category: str | None = "credential_stuffing",
    action: str | None = "investigate",
) -> RunObservation:
    return RunObservation(
        run_id=run_id,
        workflow_id=WORKFLOW,
        data_source=SOURCE,
        techniques=techniques,
        entity_types=entity_types,
        outcome=outcome,
        observed_severity=severity,
        observed_category=category,
        observed_action=action,
    )


def resolved_set(
    n: int = 10,
    *,
    techniques: frozenset[str] | None = None,
    severity: str | None = "high",
    category: str | None = "credential_stuffing",
    action: str | None = "investigate",
) -> list[RunObservation]:
    base = run()
    return [
        run(
            run_id=f"wfr-20261001-{i:08d}",
            techniques=techniques if techniques is not None else base.techniques,
            severity=severity,
            category=category,
            action=action,
        )
        for i in range(n)
    ]


# --- classify_run: one outcome word per run ----------------------------------


def test_an_intact_closure_is_its_category():
    assert classify_run([closure("resolved")]) == "resolved"


def test_a_retracted_closure_is_an_override():
    assert classify_run([closure(case_closed=False)]) == REOPENED


def test_the_override_wins_over_an_intact_closure():
    closures = [closure("resolved"), closure(case_closed=False)]
    assert classify_run(closures) == REOPENED


def test_the_latest_intact_closure_is_the_outcome():
    closures = [closure("false_positive"), closure("resolved")]
    assert classify_run(closures) == "resolved"
    assert classify_run(list(reversed(closures))) == "false_positive"


def test_nothing_in_window_is_no_evidence_yet():
    assert classify_run([closure("resolved", in_window=False)]) is None


def test_a_retraction_outside_the_window_is_not_an_override():
    # A retracted closure whose every dated trace (closed_at, case updated_at)
    # predates the window is old news, not a current override.
    assert classify_run([closure(case_closed=False, in_window=False)]) is None


def test_an_empty_link_set_is_no_evidence():
    assert classify_run([]) is None


# --- accumulate_outcomes: duplicates and overrides ---------------------------


def test_duplicates_count_in_neither_numerator_nor_denominator():
    outcomes, overrides = accumulate_outcomes(
        [run(), run(), run(outcome=DUPLICATE), run(outcome=DUPLICATE)]
    )
    assert outcomes == {"resolved": 2}
    assert overrides == 0


def test_a_reopened_run_is_an_override_and_never_an_outcome():
    outcomes, overrides = accumulate_outcomes([run(), run(outcome=REOPENED)])
    assert outcomes == {"resolved": 1}
    assert overrides == 1


def test_no_outcome_contributes_neither():
    outcomes, overrides = accumulate_outcomes([run(), run(outcome=None)])
    assert outcomes == {"resolved": 1}
    assert overrides == 0


# --- build_evidence: identity and the replayed decision ----------------------


def test_techniques_pool_across_counted_evidence_runs():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        [
            run(techniques=frozenset({"T1110.003"})),
            run(techniques=frozenset({"T1110.004"})),
        ],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.techniques == ["T1110.003", "T1110.004"]


def test_runs_without_a_counted_outcome_do_not_vote_for_identity():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        [
            run(),
            run(outcome=DUPLICATE, techniques=frozenset({"T9999.001"})),
            run(outcome=REOPENED, techniques=frozenset({"T9999.002"})),
            run(outcome=None, techniques=frozenset({"T9999.003"})),
        ],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.techniques == ["T1110.003"]


def test_entity_types_intersect_over_findings_that_carry_any():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        [
            run(entity_types=frozenset({"src_ip", "user_account"})),
            run(entity_types=frozenset({"src_ip", "host"})),
            run(entity_types=frozenset()),  # no context: does not vote
        ],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.entity_context_types == ["src_ip"]


def test_the_decision_is_the_modal_triage_of_the_resolved_runs():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        [
            run(severity="high"),
            run(severity="high", action="investigate"),
            run(severity="medium", action="monitor"),
        ],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.observed_severity == "high"
    assert evidence.observed_recommended_action == "investigate"


def test_the_enrichment_normalizer_accepts_the_daemons_deceive_action():
    # _replayable_action is the vocabulary filter on the enrichment values the
    # daemon's triage write path persists; an unaccepted verb returns None and
    # silently stops voting in the modal decision. The daemon added ``deceive``
    # (probes.py ACTIONS, the MTD verb) — the filter must keep accepting it.
    from core.policy_compiler.maturity import _replayable_action

    assert _replayable_action("deceive") == "deceive"


def test_modal_ties_break_alphabetically():
    evidence = build_evidence(
        WORKFLOW, SOURCE, [run(severity="high"), run(severity="medium")], window_days=30
    )
    assert evidence is not None
    assert evidence.observed_severity == "high"


def test_an_archetype_with_no_techniques_builds_no_evidence():
    assert (
        build_evidence(WORKFLOW, SOURCE, [run(techniques=frozenset())], window_days=30)
        is None
    )


def test_consistency_is_the_resolved_share_of_counted_outcomes():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(9) + [run(outcome="false_positive")],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.total() == 10
    assert evidence.consistency == pytest.approx(0.9)


# --- is_eligible: the compile gate over synthetic outcome sets ---------------


def test_an_eligible_set_compiles():
    evidence = build_evidence(WORKFLOW, SOURCE, resolved_set(10), window_days=30)
    assert evidence is not None
    assert is_eligible(evidence, min_runs=10, min_consistency=0.90)
    # The gate exists to feed the compiler: an eligible set really compiles,
    # and what comes out validates as the IR the evaluator runs.
    result = compile_policy(evidence, now=_now())
    PolicyIR.from_dict(result.ir)


def test_an_insufficient_n_set_does_not_compile():
    evidence = build_evidence(WORKFLOW, SOURCE, resolved_set(9), window_days=30)
    assert evidence is not None
    assert not is_eligible(evidence, min_runs=10, min_consistency=0.90)


def test_an_inconsistent_set_does_not_compile():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(8)
        + [run(outcome="false_positive"), run(outcome="false_positive")],
        window_days=30,
    )
    assert evidence is not None
    # 8/10 = 0.80: ten runs, but too many of them were not resolutions.
    assert not is_eligible(evidence, min_runs=10, min_consistency=0.90)


def test_a_reopened_set_is_ineligible_however_consistent_the_rest():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(12) + [run(outcome=REOPENED)],
        window_days=30,
    )
    assert evidence is not None
    # 12/12 resolved and still ineligible: the override is a determination
    # withdrawn, the strongest evidence the archetype is not settled.
    assert evidence.consistency == 1.0
    assert not is_eligible(evidence, min_runs=10, min_consistency=0.90)


def test_a_duplicate_heavy_set_does_not_compile():
    # Eight duplicates and two resolutions: the raw case count says ten, the
    # counted evidence says two.
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(2) + [run(outcome=DUPLICATE) for _ in range(8)],
        window_days=30,
    )
    assert evidence is not None
    assert evidence.total() == 2
    assert not is_eligible(evidence, min_runs=10, min_consistency=0.90)


def test_consistency_at_the_boundary_is_eligible_below_it_is_not():
    at = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(9) + [run(outcome="false_positive")],
        window_days=30,
    )
    under = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(9)
        + [run(outcome="false_positive"), run(outcome="false_positive")],
        window_days=30,
    )
    assert at is not None and under is not None
    assert at.consistency == pytest.approx(0.90)
    assert under.consistency < 0.90
    assert is_eligible(at, min_runs=10, min_consistency=0.90)
    assert not is_eligible(under, min_runs=10, min_consistency=0.90)


def test_a_set_with_no_recorded_triage_cannot_compile():
    evidence = build_evidence(
        WORKFLOW,
        SOURCE,
        resolved_set(10, severity=None, category=None, action=None),
        window_days=30,
    )
    assert evidence is not None
    assert is_eligible(evidence, min_runs=10, min_consistency=0.90)
    with pytest.raises(CompileError):
        # Nothing observed to replay: an empty decision is not an honest one.
        compile_policy(evidence, now=_now())
