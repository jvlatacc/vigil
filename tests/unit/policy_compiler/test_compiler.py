"""Tests for the deterministic compiler.

The property the spec pins: same evidence in, byte-identical IR out — no
wall-clock reads (the clock is injected), no randomness, no I/O. The policy id
is the archetype's stable identity; the version carries the recompile history;
the content hash is clock-stable so a recompile of unchanged evidence
reproduces it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.policy_compiler.compiler import (
    ArchetypeEvidence,
    CompileError,
    archetype_policy_id,
    compile_policy,
    next_version,
)
from core.policy_compiler.models import PolicyIR, canonical_json, validate_ir
from tests.unit.policy_compiler.fixtures.sample_ir import (
    hashed_ir_dict,
    sample_evidence,
    sample_ir_dict,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 9, 20, 0, 0, tzinfo=timezone.utc)


def with_fields(evidence: ArchetypeEvidence, **changes) -> ArchetypeEvidence:
    return ArchetypeEvidence(**{**evidence.__dict__, **changes})


# --- The determinism property ------------------------------------------------


def test_the_same_evidence_compiles_byte_identically():
    first = compile_policy(sample_evidence(), now=NOW)
    second = compile_policy(sample_evidence(), now=NOW)
    assert canonical_json(first.ir) == canonical_json(second.ir)
    assert first.content_hash == second.content_hash


def test_a_naive_clock_and_its_utc_equivalent_compile_identically():
    naive = datetime(2026, 10, 9, 20, 0, 0)
    assert (
        compile_policy(sample_evidence(), now=NOW).ir
        == compile_policy(sample_evidence(), now=naive).ir
    )


def test_the_content_hash_is_clock_stable():
    earlier = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert (
        compile_policy(sample_evidence(), now=NOW).content_hash
        == compile_policy(sample_evidence(), now=earlier).content_hash
    )


def test_a_recompile_at_a_bumped_version_reproduces_the_hash():
    # Version is row identity, not content: the recompile that issues
    # version 2 of unchanged evidence pins the same content hash.
    first = compile_policy(sample_evidence(), now=NOW)
    second = compile_policy(sample_evidence(), now=NOW, previous_version=first.version)
    assert second.version == first.version + 1
    assert second.content_hash == first.content_hash


def test_a_recompiled_unchanged_archetype_reproduces_the_hash():
    # The stored-form sample and the compiler must agree on what the
    # wf_hunt_cred_stuffing archetype's document hashes to.
    fresh = compile_policy(sample_evidence(), now=NOW)
    assert fresh.content_hash == hashed_ir_dict()["content_hash"]


def test_the_compiled_document_matches_the_spec_sample_shape():
    fresh = compile_policy(sample_evidence(), now=NOW)
    sample = sample_ir_dict()
    assert set(fresh.ir) == set(sample) | {"content_hash"}
    assert fresh.ir["match"] == sample["match"]
    assert fresh.ir["decision"] == sample["decision"]
    assert fresh.ir["maturity"] == sample["maturity"]


# --- Identity, version, validation -------------------------------------------


def test_the_policy_id_is_stable_across_evidence_that_only_changes_the_decision():
    changed = with_fields(sample_evidence(), observed_severity="critical")
    assert archetype_policy_id(changed) == archetype_policy_id(sample_evidence())


def test_a_different_archetype_mints_a_different_policy_id():
    other = with_fields(sample_evidence(), workflow_id="wf_other_hunt")
    assert archetype_policy_id(other) != archetype_policy_id(sample_evidence())


def test_the_minted_id_carries_the_pol_prefix_and_hex_body():
    minted = archetype_policy_id(sample_evidence())
    body = minted.removeprefix("pol_")
    assert len(minted) == 4 + 16
    assert all(c in "0123456789abcdef" for c in body)


def test_version_bumps_from_the_store_head_and_starts_at_one():
    assert next_version(None) == 1
    assert next_version(1) == 2
    assert next_version(9) == 10
    with pytest.raises(CompileError, match="previous_version"):
        next_version(0)


def test_a_compile_with_the_store_head_takes_the_next_version():
    fresh = compile_policy(sample_evidence(), now=NOW, previous_version=3)
    assert fresh.version == 4
    assert fresh.ir["version"] == 4


def test_structurally_impossible_evidence_is_refused():
    with pytest.raises(CompileError, match="no closed cases"):
        compile_policy(with_fields(sample_evidence(), outcomes={}), now=NOW)
    with pytest.raises(CompileError, match="data_sources"):
        compile_policy(with_fields(sample_evidence(), data_sources=[]), now=NOW)
    with pytest.raises(CompileError, match="techniques"):
        compile_policy(with_fields(sample_evidence(), techniques=[]), now=NOW)


def test_an_incoherent_observed_decision_is_refused_by_the_validation_gate():
    # The compiler feeds the same validation gate the evaluator and renderers
    # lean on: a bad token in the evidence cannot become a stored policy.
    incoherent = with_fields(sample_evidence(), observed_severity="meh")
    with pytest.raises(CompileError, match="severity"):
        compile_policy(incoherent, now=NOW)


def test_an_archetype_without_entity_types_omits_the_clause():
    unconstrained = with_fields(sample_evidence(), entity_context_types=[])
    fresh = compile_policy(unconstrained, now=NOW)
    assert "entity_context_types" not in fresh.ir["match"]


def test_the_compiled_state_is_candidate_and_human_only():
    fresh = compile_policy(sample_evidence(), now=NOW)
    assert fresh.ir["state"] == "candidate"
    assert fresh.ir["decision"]["actions_human_only"] is True


def test_the_reasoning_sentence_reports_the_evidence_honestly():
    fresh = compile_policy(sample_evidence(), now=NOW)
    assert fresh.ir["decision"]["reasoning"] == (
        "Compiled from 15 closed cases of wf_hunt_cred_stuffing: 14/15 "
        "resolved consistently, no analyst overrides in the 30-day window."
    )
    overridden = compile_policy(
        with_fields(sample_evidence(), analyst_overrides=2), now=NOW
    )
    assert (
        "2 analyst overrides in the 30-day window"
        in overridden.ir["decision"]["reasoning"]
    )


# --- The row seam ------------------------------------------------------------


def test_as_row_carries_the_candidate_columns():
    fresh = compile_policy(sample_evidence(), now=NOW)
    row = fresh.as_row()
    assert row["policy_id"] == fresh.policy_id
    assert row["version"] == fresh.version
    assert row["state"] == "candidate"
    assert row["policy_ir"] is fresh.ir
    assert row["content_hash"] == fresh.content_hash
    assert row["maturity_evidence"] == fresh.ir["maturity"]


def test_the_stored_document_survives_a_validation_round_trip():
    # What the compiler emits is what a reader (evaluator, console, renderer)
    # can re-validate: hash pinned, document intact.
    fresh = compile_policy(sample_evidence(), now=NOW)
    assert validate_ir(dict(fresh.ir)) == fresh.ir
    assert PolicyIR.from_dict(fresh.ir).content_hash == fresh.content_hash
