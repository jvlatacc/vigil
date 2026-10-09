"""Validation tests for the policy IR — the alert-farming defense lives here.

The gate the spec pins: predicates bind only to evidence-anchored, pre-LLM
fields (workflow identity, data_source, technique predictions, entity-context
key types); free-text fields and unrepresentable render targets are rejected
at compile validation, and a stored document that was modified after hashing
is refused where it is read.
"""

from __future__ import annotations

import pytest

from core.policy_compiler.models import (
    HASH_EXCLUDED_KEYS,
    IR_VERSION,
    RECOMMENDED_ACTIONS,
    SEVERITIES,
    PolicyMode,
    PolicyValidationError,
    canonical_json,
    compute_content_hash,
    mode_for_state,
    validate_ir,
)
from tests.unit.policy_compiler.fixtures.sample_ir import (
    COMPILED_AT,
    POLICY_ID,
    hashed_ir_dict,
    sample_ir_dict,
)

pytestmark = pytest.mark.unit


# --- The valid sample --------------------------------------------------------


def test_the_spec_sample_ir_validates():
    canonical = validate_ir(sample_ir_dict())
    assert canonical["match"]["workflow_id"] == "wf_hunt_cred_stuffing"
    assert canonical["decision"]["severity"] == "high"
    # Canonicalization: sets sorted, timestamp Z-suffixed.
    assert canonical["match"]["data_source"] == {
        "any_of": ["okta.system_log", "splunk"]
    }
    assert canonical["compiled_at"] == COMPILED_AT


def test_round_trip_through_the_typed_view_is_lossless():
    from core.policy_compiler.models import PolicyIR

    ir = PolicyIR.from_dict(hashed_ir_dict())
    assert ir.to_dict() == hashed_ir_dict()


def test_canonical_json_is_stable_across_calls():
    from tests.unit.policy_compiler.fixtures.sample_ir import verified_ir

    assert canonical_json(verified_ir()) == canonical_json(verified_ir())


def test_equivalent_documents_hash_identically():
    first = compute_content_hash(sample_ir_dict())
    second = compute_content_hash(hashed_ir_dict())
    assert first == second


# --- Envelope ----------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        "ir_version",
        "policy_id",
        "version",
        "state",
        "compiled_at",
        "match",
        "decision",
        "maturity",
    ],
)
def test_a_missing_required_key_is_refused_by_name(missing):
    ir = sample_ir_dict()
    del ir[missing]
    with pytest.raises(PolicyValidationError, match=missing):
        validate_ir(ir)


def test_an_unknown_top_level_key_is_refused():
    ir = sample_ir_dict()
    ir["sneaky"] = {"allow_unauthenticated": True}
    with pytest.raises(PolicyValidationError, match="sneaky"):
        validate_ir(ir)


def test_an_unsupported_ir_version_is_refused():
    ir = sample_ir_dict()
    ir["ir_version"] = IR_VERSION + 1
    with pytest.raises(PolicyValidationError, match="ir_version"):
        validate_ir(ir)


@pytest.mark.parametrize(
    "bad_id", ["policy_9f2c1a7b3d5e4082", "pol_NOTMINTED", "", "pol_"]
)
def test_a_non_minted_policy_id_is_refused(bad_id):
    ir = sample_ir_dict()
    ir["policy_id"] = bad_id
    with pytest.raises(PolicyValidationError, match="policy_id"):
        validate_ir(ir)


def test_the_sample_policy_id_passes_the_mint_check():
    assert POLICY_ID.startswith("pol_")


def test_a_state_outside_the_lifecycle_is_refused():
    ir = sample_ir_dict()
    ir["state"] = "autonomous"
    with pytest.raises(PolicyValidationError, match="state"):
        validate_ir(ir)


def test_a_non_iso_timestamp_is_refused():
    ir = sample_ir_dict()
    ir["compiled_at"] = "yesterday afternoon"
    with pytest.raises(PolicyValidationError, match="compiled_at"):
        validate_ir(ir)


def test_an_offset_timestamp_is_canonicalized_to_utc_z_form():
    ir = sample_ir_dict()
    ir["compiled_at"] = "2026-10-09T22:00:00+02:00"
    assert validate_ir(ir)["compiled_at"] == COMPILED_AT


# --- The alert-farming defense: no free-text predicates ----------------------


@pytest.mark.parametrize("free_text_key", ["title", "description", "raw_event"])
def test_a_free_text_predicate_key_is_refused_by_name(free_text_key):
    ir = sample_ir_dict()
    ir["match"][free_text_key] = "Sign in from unfamiliar location — please reset 2FA"
    with pytest.raises(PolicyValidationError) as exc:
        validate_ir(ir)
    message = str(exc.value)
    assert free_text_key in message
    assert "evidence-anchored" in message


def test_prose_in_a_technique_predicate_is_refused():
    ir = sample_ir_dict()
    ir["match"]["techniques"] = {"any_of": ["T1110.003", "or whatever looks scary"]}
    with pytest.raises(PolicyValidationError, match="techniques"):
        validate_ir(ir)


def test_a_tactic_name_is_not_a_technique_id():
    ir = sample_ir_dict()
    ir["match"]["techniques"] = {"all_of": ["Credential Access"]}
    with pytest.raises(PolicyValidationError, match="techniques"):
        validate_ir(ir)


def test_whitespace_surrounding_a_data_source_is_refused():
    ir = sample_ir_dict()
    ir["match"]["data_source"] = [" okta.system_log"]
    with pytest.raises(PolicyValidationError, match="data_source"):
        validate_ir(ir)


def test_a_control_character_in_a_predicate_is_refused():
    ir = sample_ir_dict()
    ir["match"]["techniques"] = {"any_of": ["T1110\x0b.003"]}
    with pytest.raises(PolicyValidationError, match="control characters"):
        validate_ir(ir)


# --- Predicate canonicalization ---------------------------------------------


def test_sets_are_deduped_and_sorted_canonically():
    ir = sample_ir_dict()
    ir["match"]["techniques"] = {"any_of": ["T9999", "T1110.003", "T9999"]}
    canonical = validate_ir(ir)
    assert canonical["match"]["techniques"]["any_of"] == ["T1110.003", "T9999"]


def test_a_bare_data_source_list_canonicalizes_to_the_object_form():
    from tests.unit.policy_compiler.fixtures.sample_ir import DATA_SOURCES

    bare = sample_ir_dict()
    bare["match"]["data_source"] = list(DATA_SOURCES)
    object_form = sample_ir_dict()
    assert validate_ir(bare) == validate_ir(object_form)


def test_an_empty_predicate_group_is_refused():
    ir = sample_ir_dict()
    ir["match"]["techniques"] = {}
    with pytest.raises(PolicyValidationError, match="techniques"):
        validate_ir(ir)


def test_an_unknown_key_inside_a_predicate_group_is_refused():
    ir = sample_ir_dict()
    ir["match"]["entity_context_types"] = {"some_of": ["src_ip"]}
    with pytest.raises(PolicyValidationError, match="some_of"):
        validate_ir(ir)


# --- Decision ----------------------------------------------------------------


def test_an_out_of_range_confidence_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["confidence"] = 1.5
    with pytest.raises(PolicyValidationError, match="confidence"):
        validate_ir(ir)


def test_a_non_finite_confidence_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["confidence"] = float("nan")
    with pytest.raises(PolicyValidationError, match="confidence"):
        validate_ir(ir)


def test_a_severity_outside_the_vocabulary_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["severity"] = "apocalyptic"
    with pytest.raises(PolicyValidationError, match="severity"):
        validate_ir(ir)


def test_an_action_outside_the_vocabulary_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["recommended_action"] = "nuke"
    with pytest.raises(PolicyValidationError, match="recommended_action"):
        validate_ir(ir)


def test_the_vocabularies_match_the_daemons():
    # Mirrored from services/daemon/probes.py (core cannot import services):
    # this test fails loudly if the two spellings drift apart. Read from the
    # daemon source so the comparison is live, not another copy.
    import ast
    import pathlib

    probes = pathlib.Path("services/daemon/probes.py").read_text()
    module = ast.parse(probes)
    literals = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Tuple)
        and node.targets[0].id in ("SEVERITIES", "ACTIONS")
    }
    assert literals["SEVERITIES"] == SEVERITIES
    assert literals["ACTIONS"] == RECOMMENDED_ACTIONS


def test_a_prose_category_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["category"] = "Looks Like Credential Stuffing!"
    with pytest.raises(PolicyValidationError, match="category"):
        validate_ir(ir)


def test_reasoning_beyond_the_prose_cap_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["reasoning"] = "x" * 2001
    with pytest.raises(PolicyValidationError, match="reasoning"):
        validate_ir(ir)


def test_claiming_unattended_actions_is_refused():
    ir = sample_ir_dict()
    ir["decision"]["actions_human_only"] = False
    with pytest.raises(PolicyValidationError) as exc:
        validate_ir(ir)
    assert "ADR 0001" in str(exc.value)


# --- Maturity evidence -------------------------------------------------------


def test_match_and_maturity_naming_different_workflows_is_refused():
    ir = sample_ir_dict()
    ir["maturity"]["workflow_id"] = "wf_other_hunt"
    with pytest.raises(PolicyValidationError, match="workflow_id"):
        validate_ir(ir)


def test_negative_outcome_counts_are_refused():
    ir = sample_ir_dict()
    ir["maturity"]["outcomes"]["resolved"] = -1
    with pytest.raises(PolicyValidationError, match="outcomes"):
        validate_ir(ir)


def test_an_outcome_key_that_is_not_a_closure_token_is_refused():
    ir = sample_ir_dict()
    ir["maturity"]["outcomes"][" analyst said so"] = 2
    with pytest.raises(PolicyValidationError, match="closure-category"):
        validate_ir(ir)


def test_consistency_outside_zero_to_one_is_refused():
    ir = sample_ir_dict()
    ir["maturity"]["consistency"] = 1.2
    with pytest.raises(PolicyValidationError, match="consistency"):
        validate_ir(ir)


def test_analyst_overrides_cannot_be_negative():
    ir = sample_ir_dict()
    ir["maturity"]["analyst_overrides"] = -1
    with pytest.raises(PolicyValidationError, match="analyst_overrides"):
        validate_ir(ir)


def test_window_days_outside_a_year_decade_is_refused():
    ir = sample_ir_dict()
    ir["maturity"]["window_days"] = 0
    with pytest.raises(PolicyValidationError, match="window_days"):
        validate_ir(ir)


# --- Content hash ------------------------------------------------------------


def test_lifecycle_envelope_changes_do_not_change_the_hash():
    base = compute_content_hash(sample_ir_dict())
    promoted = sample_ir_dict()
    promoted["state"] = "active"
    promoted["compiled_at"] = "2026-10-10T00:00:00Z"
    promoted["renders"] = {"rego": "sha256:" + "0" * 64}
    assert compute_content_hash(promoted) == base


def test_a_semantic_change_changes_the_hash():
    base = compute_content_hash(sample_ir_dict())
    changed = sample_ir_dict()
    changed["decision"]["severity"] = "medium"
    assert compute_content_hash(changed) != base


def test_hash_excludes_exactly_the_documented_keys():
    assert HASH_EXCLUDED_KEYS == frozenset(
        {"content_hash", "renders", "state", "compiled_at"}
    )


def test_a_tampered_document_is_refused_at_read():
    ir = hashed_ir_dict()
    ir["decision"]["severity"] = "low"  # someone edits the stored document
    with pytest.raises(PolicyValidationError, match="modified after hashing"):
        validate_ir(ir)


def test_a_well_formed_but_wrong_hash_is_refused():
    ir = hashed_ir_dict()
    ir["content_hash"] = "sha256:" + "f" * 64
    with pytest.raises(PolicyValidationError, match="does not match the recomputed"):
        validate_ir(ir)


def test_a_malformed_hash_string_is_refused():
    ir = sample_ir_dict()
    ir["content_hash"] = "md5:deadbeef"
    with pytest.raises(PolicyValidationError, match="content_hash"):
        validate_ir(ir)


# --- Render targets ----------------------------------------------------------


def test_an_unknown_render_target_in_the_document_is_refused():
    ir = sample_ir_dict()
    ir["renders"] = {"f5_bigip": "sha256:" + "0" * 64}
    with pytest.raises(PolicyValidationError) as exc:
        validate_ir(ir)
    assert "f5_bigip" in str(exc.value)
    assert "cannot represent" not in str(
        exc.value
    )  # phrasing: "not one the renderer set can represent"
    assert "renderer set" in str(exc.value)


def test_a_malformed_render_digest_is_refused():
    ir = sample_ir_dict()
    ir["renders"] = {"rego": "sha256:short"}
    with pytest.raises(PolicyValidationError, match="renders.rego"):
        validate_ir(ir)


# --- Mode mapping ------------------------------------------------------------


def test_shadow_and_suspended_evaluate_as_shadow_mode():
    assert mode_for_state("shadow") is PolicyMode.SHADOW
    assert mode_for_state("suspended") is PolicyMode.SHADOW


def test_active_evaluates_as_active_mode():
    assert mode_for_state("active") is PolicyMode.ACTIVE


@pytest.mark.parametrize("invisible_state", ["candidate", "retired"])
def test_candidate_and_retired_are_never_evaluated(invisible_state):
    with pytest.raises(ValueError, match="never evaluated"):
        mode_for_state(invisible_state)
