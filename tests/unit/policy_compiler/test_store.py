"""Store-layer tests for the policy fast path (DB-backed).

These exercise ``core.policy_compiler.store`` against a real Postgres — the
SQL, the CHECK constraints (mode/outcome pairing, agreement pairing), and the
FK to ``findings`` in one pass. Marked ``external_service``: CI's DB-backed
unit job selects them and ``tests/unit/conftest.py`` hands each one a
throwaway database built from the ORM models (a missing Postgres is an error,
never a skip — the conftest owns that rule).

The hook-level contract these rows serve is covered DB-free in
``tests/unit/daemon/test_policy_fast_path.py``.
"""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
from datetime import timedelta

import pytest
from sqlalchemy import text

from core.policy_compiler import store
from core.policy_compiler.compiler import archetype_policy_id
from core.policy_compiler.evaluator import evaluate
from core.policy_compiler.models import compute_content_hash
from core.storage.connection import get_db_manager
from core.storage.models import CompiledPolicy, CompiledPolicyDecision, Finding
from core.time import utcnow
from tests.unit.policy_compiler.fixtures.sample_ir import (
    POLICY_ID,
    sample_evidence,
    sample_ir_dict,
    sample_maturity,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.external_service,
    pytest.mark.database,
]


def _minted_id(workflow_suffix: str) -> str:
    """A compiler-minted id for a distinct archetype of the sample evidence.

    The IR validator only accepts minted ids (``^pol_[0-9a-f]{16}$``), so a
    store row that must LOAD cannot carry an invented id.
    """
    evidence = dataclass_replace(
        sample_evidence(), workflow_id=sample_evidence().workflow_id + workflow_suffix
    )
    return archetype_policy_id(evidence)


def _cleanup():
    """Blanket-clear the policy tables — the throwaway database is private to
    this pytest process (tests/unit/conftest.py), so there is nothing to keep.
    The sample POLICY_ID does not match a 'test-%' pattern, so the deletes
    cannot be narrowed by id prefix.
    """
    with get_db_manager().session_scope() as s:
        s.execute(text("DELETE FROM compiled_policy_decisions"))
        s.execute(text("DELETE FROM compiled_policies"))
        s.execute(text("DELETE FROM findings WHERE finding_id LIKE 'test-fnd-%'"))


@pytest.fixture(autouse=True)
def clean_policy_rows():
    _cleanup()
    yield
    _cleanup()


def _insert_finding(finding_id: str) -> str:
    with get_db_manager().session_scope() as s:
        s.add(
            Finding(
                finding_id=finding_id,
                data_source="okta.system_log",
                title="store test finding",
                timestamp=utcnow(),
            )
        )
    return finding_id


def _insert_policy(state: str, policy_id: str = POLICY_ID, version: int = 3):
    document = sample_ir_dict()
    document["policy_id"] = policy_id
    document["state"] = state
    document["version"] = version
    # The hash is over the final document, exactly as the compiler writes it.
    document["content_hash"] = compute_content_hash(document)
    row = CompiledPolicy(
        policy_id=policy_id,
        version=version,
        state=state,
        policy_ir=document,
        content_hash=document["content_hash"],
        maturity_evidence=sample_maturity(),
    )
    if state in ("active", "suspended"):
        row.promoted_at = utcnow()
        row.promoted_by = "test"
    if state == "suspended":
        row.suspended_at = utcnow()
        row.suspended_by = "test"
    if state == "retired":
        row.retired_at = utcnow()
        row.retired_by = "test"
    with get_db_manager().session_scope() as s:
        s.add(row)


def _matched_finding(finding_id: str) -> dict:
    return {
        "finding_id": finding_id,
        "data_source": "okta.system_log",
        "mitre_predictions": {"T1110.003": 0.9},
        "entity_context": {"src_ips": ["203.0.113.7"], "usernames": ["j"]},
    }


class TestLoadEvaluatingPolicies:
    def test_loads_only_evaluating_states_active_first(self):
        second, inert = _minted_id("_second"), _minted_id("_inert")
        _insert_policy("shadow")
        _insert_policy("active", policy_id=second)
        _insert_policy("candidate", policy_id=inert)
        _insert_policy("retired", policy_id=inert, version=2)

        loaded = store.load_evaluating_policies()

        assert [(p.policy_id, p.state) for p in loaded] == [
            (second, "active"),
            (POLICY_ID, "shadow"),
        ]
        # The typed view is pinned to the row's own lifecycle identity.
        for policy in loaded:
            assert policy.content_hash.startswith("sha256:")
            assert policy.state in ("active", "shadow")

    def test_higher_version_first_within_a_policy(self):
        _insert_policy("shadow", version=3)
        _insert_policy("shadow", version=4)

        loaded = store.load_evaluating_policies()
        assert [p.version for p in loaded] == [4, 3]


class TestRecordDecision:
    def test_an_active_hit_writes_an_applied_row(self):
        _insert_policy("active")
        finding_id = _insert_finding("test-fnd-hit")

        policies = store.load_evaluating_policies()
        hit = evaluate(policies, _matched_finding(finding_id))
        row_id = store.record_decision(finding_id, hit, 42)

        with get_db_manager().session_scope() as s:
            row = s.get(CompiledPolicyDecision, row_id)
            assert row.outcome == "applied"
            assert row.mode == "active"
            assert row.policy_id == POLICY_ID
            assert row.evaluation_us == 42
            assert row.decision["severity"] == hit.decision.severity
            assert row.agrees is None and row.actual_decision is None

    def test_a_shadow_hit_writes_a_shadow_logged_row(self):
        _insert_policy("shadow")
        finding_id = _insert_finding("test-fnd-shadow")
        evaluation = evaluate(
            store.load_evaluating_policies(), _matched_finding(finding_id)
        )
        row_id = store.record_decision(finding_id, evaluation, 7)

        with get_db_manager().session_scope() as s:
            row = s.get(CompiledPolicyDecision, row_id)
            assert row.outcome == "shadow_logged"
            assert row.mode == "shadow"

    def test_a_miss_writes_a_no_match_row(self):
        finding_id = _insert_finding("test-fnd-miss")
        row_id = store.record_decision(finding_id, None, 5)

        with get_db_manager().session_scope() as s:
            row = s.get(CompiledPolicyDecision, row_id)
            assert row.outcome == "no_match"
            assert row.mode is None
            assert row.policy_id is None
            assert row.decision is None

    def test_a_decision_for_an_unknown_finding_fails_the_fk(self):
        _insert_policy("shadow")
        evaluation = evaluate(
            store.load_evaluating_policies(), _matched_finding("test-fnd-any")
        )
        # The hook fails closed on this — an unloggable decision is not acted on.
        with pytest.raises(Exception):
            store.record_decision("test-fnd-does-not-exist", evaluation, 1)


class TestBackfillAndDrift:
    def test_backfill_fills_agreement_and_it_counts(self):
        _insert_policy("shadow")
        finding_id = _insert_finding("test-fnd-agree")
        evaluation = evaluate(
            store.load_evaluating_policies(), _matched_finding(finding_id)
        )
        row_id = store.record_decision(finding_id, evaluation, 7)

        store.backfill_llm_agreement(
            row_id,
            {"severity": "low", "recommended_action": "monitor"},
            False,
        )

        with get_db_manager().session_scope() as s:
            row = s.get(CompiledPolicyDecision, row_id)
            assert row.agrees is False
            assert row.agreement_source == "llm"
            assert row.actual_decision["severity"] == "low"

        assert (
            store.disagreements_in_window(
                POLICY_ID, evaluation.policy_version, window_days=30
            )
            == 1
        )

    def test_agreement_outside_the_window_is_not_counted(self):
        _insert_policy("shadow")
        finding_id = _insert_finding("test-fnd-old")
        evaluation = evaluate(
            store.load_evaluating_policies(), _matched_finding(finding_id)
        )
        row_id = store.record_decision(finding_id, evaluation, 7)
        store.backfill_llm_agreement(
            row_id, {"severity": "low", "recommended_action": "monitor"}, False
        )
        with get_db_manager().session_scope() as s:
            s.execute(
                text(
                    "UPDATE compiled_policy_decisions SET evaluated_at = :ts "
                    "WHERE id = :rid"
                ),
                {"ts": utcnow() - timedelta(days=31), "rid": row_id},
            )

        assert (
            store.disagreements_in_window(
                POLICY_ID, evaluation.policy_version, window_days=30
            )
            == 0
        )

    def test_suspend_for_drift_transitions_once(self):
        _insert_policy("shadow")
        assert store.suspend_for_drift(POLICY_ID, 3, "drift limit breached") is True
        with get_db_manager().session_scope() as s:
            row = s.get(CompiledPolicy, {"policy_id": POLICY_ID, "version": 3})
            assert row.state == "suspended"
            assert row.suspended_by == store.DRIFT_ACTOR

        # A second brake has nothing to transition — idempotent.
        assert store.suspend_for_drift(POLICY_ID, 3, "drift limit breached") is False


class TestStalenessRetirement:
    def test_a_shadow_policy_without_recent_decisions_is_retired(self):
        stale_id, fresh_id = _minted_id("_stale"), _minted_id("_fresh")
        _insert_policy("shadow", policy_id=stale_id)
        _insert_policy("active", policy_id=fresh_id)
        finding_id = _insert_finding("test-fnd-fresh")
        fresh_ir = next(
            p for p in store.load_evaluating_policies() if p.policy_id == fresh_id
        )
        evaluation = evaluate([fresh_ir], _matched_finding(finding_id))
        store.record_decision(finding_id, evaluation, 7)

        retired = store.retire_stale_policies(window_days=30)

        assert retired == [stale_id]
        with get_db_manager().session_scope() as s:
            stale = s.get(CompiledPolicy, {"policy_id": stale_id, "version": 3})
            assert stale.state == "retired"
            assert stale.retired_by == store.STALENESS_ACTOR
            fresh = s.get(CompiledPolicy, {"policy_id": fresh_id, "version": 3})
            assert fresh.state == "active"
