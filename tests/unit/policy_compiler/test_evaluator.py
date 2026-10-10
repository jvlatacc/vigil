"""Evaluator tests: field access, truth tables, determinism, and the bound.

The property the spec pins — a policy hit must be indistinguishable from an
LLM triage downstream, except faster and cheaper — rests on this module:
fail-closed field access over pre-LLM fields, first-match-wins ordering,
bit-for-bit determinism, and microsecond-scale evaluation asserted with an
upper bound.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import datetime, timezone

import pytest

from core.policy_compiler.compiler import ArchetypeEvidence, compile_policy
from core.policy_compiler.evaluator import TriageDecision, evaluate
from core.policy_compiler.models import PolicyIR, PolicyMode, compute_content_hash
from tests.unit.policy_compiler.fixtures.sample_ir import sample_evidence

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 9, 20, 0, 0, tzinfo=timezone.utc)


def finding(**overrides):
    """A realistic pre-LLM finding dict (poller-normalized shapes)."""
    base = {
        "finding_id": "fnd_20261009_0001",
        "timestamp": "2026-10-09T19:59:00Z",
        "data_source": "okta.system_log",
        "title": "Sign-in anomaly",
        "description": "Impossible-travel pattern from the SIEM.",
        "mitre_predictions": {"T1110.003": 0.9, "T1110.004": 0.8},
        "entity_context": {
            "src_ips": ["203.0.113.7"],
            "usernames": ["jvanlowe"],
        },
        "severity": "low",
        "status": "new",
    }
    return {**base, **overrides}


def _in_state(evidence: ArchetypeEvidence, state: str) -> PolicyIR:
    """A compiled policy pinned to a lifecycle state.

    The content hash excludes lifecycle state, so re-pinning changes no
    hash — the explicit state swap is what the evaluator keys its mode on.
    """
    document = compile_policy(evidence, now=NOW).ir
    document["state"] = state
    document["content_hash"] = compute_content_hash(document)
    return PolicyIR.from_dict(document)


def policy_in_state(state: str) -> PolicyIR:
    """The sample archetype under a lifecycle state."""
    return _in_state(sample_evidence(), state)


def shadow_sample() -> PolicyIR:
    """The sample archetype as an evaluating (shadow) row."""
    return policy_in_state("shadow")


def other_evidence() -> ArchetypeEvidence:
    """A second archetype, for ordering tests."""
    return ArchetypeEvidence(
        workflow_id="wf_hunt_impossible_travel",
        window_days=30,
        data_sources=["splunk"],
        techniques=["T1078"],
        entity_context_types=["src_ip"],
        outcomes={"resolved": 12},
        consistency=0.92,
        analyst_overrides=0,
        observed_severity="medium",
        observed_recommended_action="monitor",
        observed_category="impossible_travel",
    )


def shadow_other() -> PolicyIR:
    """The second archetype as an evaluating (shadow) row."""
    return _in_state(other_evidence(), "shadow")


def finding_matching_both():
    """A finding both fixture archetypes can claim: shared source, both technique sets."""
    return finding(
        data_source="splunk",
        mitre_predictions={"T1110.003": 0.9, "T1078": 0.8},
        entity_context={"src_ips": ["203.0.113.7"], "usernames": ["jvanlowe"]},
    )


# --- Matching over pre-LLM fields ---------------------------------------------


def test_a_finding_of_the_archetype_matches_the_sample_policy():
    evaluation = evaluate([shadow_sample()], finding())
    assert evaluation is not None
    assert evaluation.policy_id == shadow_sample().policy_id


def test_a_finding_from_another_data_source_does_not_match():
    assert evaluate([shadow_sample()], finding(data_source="crowdstrike")) is None


def test_a_finding_without_the_techniques_does_not_match():
    assert (
        evaluate([shadow_sample()], finding(mitre_predictions={"T1566": 0.9})) is None
    )


@pytest.mark.parametrize("predictions", [{}, None, ["T1110.003"], "T1110.003", 42])
def test_non_canonical_mitre_prediction_shapes_carry_no_techniques(predictions):
    # The poller normalizes to {technique_id: confidence}; anything else is
    # not a prediction set and matches no technique clause.
    assert evaluate([shadow_sample()], finding(mitre_predictions=predictions)) is None


def test_a_finding_missing_one_of_the_entity_types_does_not_match():
    assert (
        evaluate(
            [shadow_sample()],
            finding(entity_context={"src_ips": ["1.2.3.4"]}),
        )
        is None
    )


@pytest.mark.parametrize(
    "entity_context",
    [
        None,
        {},
        {"src_ips": [], "usernames": []},  # empty values claim nothing
        {"src_ips": None, "usernames": None},
        "not-a-mapping",
    ],
)
def test_degenerate_entity_contexts_claim_no_types(entity_context):
    assert evaluate([shadow_sample()], finding(entity_context=entity_context)) is None


@pytest.mark.parametrize("data_source", [None, ["okta.system_log"], {"okta": True}, ""])
def test_a_missing_or_non_string_data_source_matches_no_clause(data_source):
    assert evaluate([shadow_sample()], finding(data_source=data_source)) is None


def test_legacy_singular_entity_keys_map_to_the_same_types():
    legacy = finding(entity_context={"src_ip": "203.0.113.7", "username": "jvanlowe"})
    assert evaluate([shadow_sample()], legacy) is not None


def test_an_unmapped_entity_key_passes_through_verbatim():
    # A future poller key is matchable the day it appears: its name is its type.
    unmapped = finding(
        entity_context={
            "container_ids": ["abc"],
            "src_ips": ["203.0.113.7"],
            "usernames": ["jvanlowe"],
        }
    )
    assert evaluate([shadow_sample()], unmapped) is not None


# --- any_of / all_of truth tables ----------------------------------------------


@pytest.mark.parametrize(
    ("predictions", "matches"),
    [
        ({"T1110.003": 0.9}, True),  # any_of: one of the archetype's techniques
        ({"T1110.004": 0.7, "T1566": 0.9}, True),  # any_of: one of + noise
        ({"T1110.003": 0.9, "T1110.004": 0.8}, True),  # any_of: the whole set
        ({"T1566": 0.9}, False),  # any_of: disjoint
    ],
)
def test_technique_any_of_truth_table(predictions, matches):
    assert (
        evaluate([shadow_sample()], finding(mitre_predictions=predictions)) is not None
    ) is matches


def test_an_all_of_technique_clause_requires_every_technique():
    evidence = ArchetypeEvidence(**sample_evidence().__dict__)
    evidence_out = compile_policy(evidence, now=NOW).ir
    evidence_out["match"]["techniques"] = {"all_of": ["T1110.003", "T1110.004"]}
    evidence_out["state"] = "shadow"
    evidence_out["content_hash"] = compute_content_hash(evidence_out)
    all_of_policy = PolicyIR.from_dict(evidence_out)

    complete = finding()  # carries both techniques
    partial = finding(mitre_predictions={"T1110.003": 0.9})
    assert evaluate([all_of_policy], complete) is not None
    assert evaluate([all_of_policy], partial) is None


@pytest.mark.parametrize(
    ("entity_context", "matches"),
    [
        ({"src_ips": ["1.2.3.4"], "usernames": ["a"]}, True),  # all_of satisfied
        ({"src_ips": ["1.2.3.4"]}, False),  # all_of: one type missing
        (
            {"src_ips": ["1.2.3.4"], "usernames": ["a"], "hostnames": ["web-1"]},
            True,  # all_of satisfied + extra types are fine
        ),
    ],
)
def test_entity_type_truth_table(entity_context, matches):
    assert (
        evaluate([shadow_sample()], finding(entity_context=entity_context)) is not None
    ) is matches


def test_a_policy_without_an_entity_clause_ignores_entity_context():
    evidence = ArchetypeEvidence(
        **{**sample_evidence().__dict__, "entity_context_types": []}
    )
    unconstrained = _in_state(evidence, "shadow")
    bare = finding(entity_context={})
    assert evaluate([unconstrained], bare) is not None


# --- Workflow identity ----------------------------------------------------------


def test_a_finding_claiming_another_workflow_does_not_match():
    assert evaluate([shadow_sample()], finding(workflow_id="wf_other")) is None


def test_a_finding_claiming_the_archetypes_own_workflow_matches():
    own = shadow_sample().match.workflow_id
    assert evaluate([shadow_sample()], finding(workflow_id=own)) is not None


# --- Ordering, determinism, and the bound ---------------------------------------


def test_first_match_wins_in_sequence_order():
    matching = finding_matching_both()
    evaluation = evaluate([shadow_sample(), shadow_other()], matching)
    assert evaluation is not None
    assert evaluation.policy_id == shadow_sample().policy_id  # first in sequence

    evaluation = evaluate([shadow_other(), shadow_sample()], matching)
    assert evaluation is not None
    assert evaluation.policy_id == shadow_other().policy_id


def test_the_same_finding_and_sequence_decide_bit_for_bit():
    policies = [shadow_sample(), shadow_other()]
    target = finding_matching_both()
    first = evaluate(policies, target)
    second = evaluate(policies, target)
    assert first is not None and second is not None
    assert (first.policy_id, first.policy_version, first.content_hash) == (
        second.policy_id,
        second.policy_version,
        second.content_hash,
    )
    assert first.decision == second.decision
    assert first.mode is second.mode


def test_evaluation_does_not_mutate_the_finding():
    original = finding_matching_both()
    snapshot = copy.deepcopy(original)
    evaluate([shadow_sample()], original)
    assert original == snapshot


def test_evaluation_completes_well_under_a_millisecond_at_scale():
    import time

    policies = [shadow_sample(), shadow_other()] * 50  # 100 rows: realistic ceiling
    target = finding_matching_both()
    started_ns = time.perf_counter_ns()
    evaluation = evaluate(policies, target)
    elapsed_us = (time.perf_counter_ns() - started_ns) // 1000
    assert evaluation is not None
    assert elapsed_us < 1_000  # the asserted microsecond upper bound
    assert 0 <= evaluation.evaluation_us <= elapsed_us


# --- Modes and refusals -----------------------------------------------------------


def test_shadow_and_suspended_rows_evaluate_as_shadow_mode():
    for state in ("shadow", "suspended"):
        assert evaluate([policy_in_state(state)], finding()).mode is PolicyMode.SHADOW


def test_an_active_row_evaluates_as_active_mode():
    assert evaluate([policy_in_state("active")], finding()).mode is PolicyMode.ACTIVE


@pytest.mark.parametrize("invisible_state", ["candidate", "retired"])
def test_candidate_and_retired_rows_are_never_evaluated(invisible_state):
    with pytest.raises(ValueError, match="never evaluated"):
        evaluate([policy_in_state(invisible_state)], finding())


def test_an_unpinned_policy_is_refused():
    unpinned = dataclasses.replace(shadow_sample(), content_hash=None)
    with pytest.raises(ValueError, match="no content hash"):
        evaluate([unpinned], finding())


# --- The triage key contract --------------------------------------------------------


def test_the_evaluation_writes_the_llm_triage_key_set():
    evaluation = evaluate([policy_in_state("active")], finding())
    fields = evaluation.as_finding_fields()
    # Exactly the finding keys _apply_triage_result writes — no more, no less.
    assert set(fields) == {
        "severity",
        "triage_confidence",
        "category",
        "recommended_action",
        "triage_reasoning",
    }
    assert fields["triage_confidence"] == evaluation.decision.confidence


def test_the_ai_triage_block_carries_the_provenance():
    evaluation = evaluate([policy_in_state("active")], finding())
    block = evaluation.as_ai_triage_block("2026-10-09T20:00:00Z")
    assert block["source"] == "jit_policy"
    assert block["policy_id"] == evaluation.policy_id
    assert block["version"] == evaluation.policy_version
    assert block["content_hash"] == evaluation.content_hash
    assert block["evaluation_us"] == evaluation.evaluation_us
    assert block["result"] == evaluation.decision.as_triage_result()


def test_a_triage_decision_is_frozen():
    decision = TriageDecision(
        severity="high",
        confidence=0.93,
        recommended_action="investigate",
        category="credential_stuffing",
        reasoning="because",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.severity = "low"
