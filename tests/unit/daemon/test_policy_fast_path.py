"""Daemon-hook tests for the compiled-policy fast path (docs/adr/0001).

The spec's property — an ACTIVE hit is indistinguishable downstream from an
LLM triage, except faster and cheaper — is pinned here at the hook layer:

- an active hit writes the LLM triage key set (plus provenance) and the LLM
  is never called;
- the response pipeline sees exactly what it always saw;
- a shadow hit logs its decision and writes no triage keys;
- a miss (or a fast-path failure, or the flag off) leaves the LLM path
  byte-for-byte the code path it always was.

The store layer is faked at the ``core.policy_compiler.store`` seam: the
hook's contract with it (load / record / backfill / count / suspend) is the
unit under test, not the SQL (covered DB-backed in
``tests/unit/policy_compiler/test_store.py``).
"""

from __future__ import annotations

import pytest

from core.platform import runtime_config
from core.policy_compiler import fast_path as fast_path_module
from core.policy_compiler import store
from core.policy_compiler.evaluator import TriageDecision
from core.policy_compiler.models import PolicyIR, PolicyMode, compute_content_hash
from services.daemon.config import ProcessingConfig
from services.daemon.processor import FindingProcessor
from tests.unit.policy_compiler.fixtures.sample_ir import (
    POLICY_ID,
    sample_evidence,
    sample_policy_ir,
)

pytestmark = pytest.mark.unit


def shadow_policy():
    """The sample policy pinned to the shadow state (hash excludes state)."""
    document = sample_policy_ir().to_dict()
    document["state"] = "shadow"
    document["content_hash"] = compute_content_hash(document)
    return PolicyIR.from_dict(document)


def active_policy():
    """The sample policy pinned to the active state."""
    document = sample_policy_ir().to_dict()
    document["state"] = "active"
    document["content_hash"] = compute_content_hash(document)
    return PolicyIR.from_dict(document)


def finding(**overrides):
    """A pre-LLM finding the sample policy matches (poller-normalized shapes)."""
    base = {
        "finding_id": "fnd_20261009_0001",
        "data_source": "okta.system_log",
        "title": "Sign-in anomaly",
        "description": "Impossible-travel pattern from the SIEM.",
        "mitre_predictions": {"T1110.003": 0.9},
        "entity_context": {
            "src_ips": ["203.0.113.7"],
            "usernames": ["jvanlowe"],
        },
        "severity": "low",
        "status": "new",
    }
    return {**base, **overrides}


def llm_reply(severity: str = "high") -> str:
    """A well-formed triage reply with the sample policy's decision values."""
    return (
        f"SEVERITY: {severity}\nCONFIDENCE: 0.82\nCATEGORY: malware\n"
        "RECOMMENDED_ACTION: investigate\nREASONING: model said so"
    )


class HookHarness:
    """A processor with the fast path's store seam faked and paths recorded."""

    def __init__(self, monkeypatch, policies, flag=True):
        self.config = ProcessingConfig(
            jit_fast_path_enabled=flag,
            auto_triage_enabled=True,
            auto_enrich_enabled=False,
        )
        self.processor = FindingProcessor(self.config)
        self.llm_calls = 0
        self.persisted = []
        self.response_findings = []
        self.decision_rows = []
        self.backfills = []
        self.suspensions = []
        self._row = 0

        monkeypatch.setattr(store, "load_evaluating_policies", lambda: list(policies))

        def fake_record(finding_id, evaluation, evaluation_us):
            self._row += 1
            self.decision_rows.append(
                {
                    "row_id": self._row,
                    "finding_id": finding_id,
                    "evaluation": evaluation,
                    "evaluation_us": evaluation_us,
                }
            )
            return self._row

        monkeypatch.setattr(store, "record_decision", fake_record)
        monkeypatch.setattr(
            store,
            "backfill_llm_agreement",
            lambda row_id, actual, agrees: self.backfills.append(
                {"row_id": row_id, "actual": dict(actual), "agrees": agrees}
            ),
        )
        monkeypatch.setattr(
            store,
            "suspend_for_drift",
            lambda policy_id, version, reason: self.suspensions.append(
                {"policy_id": policy_id, "version": version, "reason": reason}
            ),
        )

        async def fake_llm(prompt):
            self.llm_calls += 1
            return llm_reply(), None

        monkeypatch.setattr(self.processor, "_get_ai_triage", fake_llm)

        async def fake_update(f):
            self.persisted.append(dict(f))
            return True

        monkeypatch.setattr(self.processor, "_update_finding", fake_update)

        async def fake_response(f):
            self.response_findings.append(dict(f))

        monkeypatch.setattr(self.processor, "_evaluate_for_response", fake_response)

    async def run(self, f=None):
        return await self.processor._enrich_in_background(f or finding())


def _tuning(monkeypatch, drift_limit=3, window_days=30):
    """Pin the drift-brake tunables away from the DB/env chain."""
    settings = {
        fast_path_module.pc_config.DRIFT_LIMIT_KEY: drift_limit,
        fast_path_module.pc_config.WINDOW_DAYS_KEY: window_days,
    }
    monkeypatch.setattr(
        runtime_config,
        "get_ai_operations_setting",
        lambda key, default: settings.get(key, default),
    )


class TestActiveHit:
    async def test_an_active_hit_skips_the_llm_and_writes_the_triage_key_set(
        self, monkeypatch
    ):
        harness = HookHarness(monkeypatch, [active_policy()])
        await harness.run()

        # The acceptance evidence the spec pins: the model is never reached.
        assert harness.llm_calls == 0
        # The finding keys are exactly the LLM path's key set...
        f = harness.response_findings[0]
        assert f["severity"] == "high"
        assert f["triage_confidence"] == pytest.approx(0.93)
        assert f["category"] == "credential_stuffing"
        assert f["recommended_action"] == "investigate"
        assert f["triage_reasoning"].startswith("Compiled from 15")
        # ...persisted exactly as the LLM path persists...
        assert harness.persisted and harness.persisted[0]["severity"] == "high"
        # ...and the response pipeline was reached with the triaged finding.
        assert len(harness.response_findings) == 1

    async def test_the_provenance_block_names_the_deciding_policy(self, monkeypatch):
        harness = HookHarness(monkeypatch, [active_policy()])
        await harness.run()

        f = harness.response_findings[0]
        provenance = f["ai_triage"]
        assert provenance["source"] == "jit_policy"
        assert provenance["policy_id"] == POLICY_ID
        assert provenance["version"] == 3
        assert provenance["content_hash"].startswith("sha256:")
        assert provenance["evaluation_us"] >= 0
        assert provenance["result"]["severity"] == "high"

    async def test_triage_keys_are_byte_identical_to_the_llm_path_key_set(
        self, monkeypatch
    ):
        """Same semantic decision, same finding keys — the fast path does not
        invent a shape the downstream pipeline has never seen. The LLM side
        runs through the real hook with the flag off, so its duration
        instrumentation is exercised too."""
        llm_harness = HookHarness(monkeypatch, [active_policy()], flag=False)
        await llm_harness.run()
        llm_finding = llm_harness.response_findings[0]

        policy_harness = HookHarness(monkeypatch, [active_policy()])
        await policy_harness.run()
        policy_finding = policy_harness.response_findings[0]

        llm_block = llm_finding["ai_triage"]
        policy_block = policy_finding["ai_triage"]
        # The finding-level key set and the inner result keys are identical;
        # the metadata differs only by the provenance the policy adds and the
        # duration the LLM adds.
        assert set(k for k in llm_finding if k in policy_finding) >= {
            "severity",
            "triage_confidence",
            "category",
            "recommended_action",
            "triage_reasoning",
            "ai_triage",
        }
        assert set(llm_block["result"]) == set(policy_block["result"])
        # The LLM side carries its model time going forward (docs/adr/0001).
        assert "duration_ms" in llm_block and llm_block["duration_ms"] >= 0
        assert {
            "timestamp",
            "result",
            "source",
            "policy_id",
            "version",
            "content_hash",
            "evaluation_us",
        } <= set(policy_block)

    async def test_every_evaluation_is_recorded_with_its_latency(self, monkeypatch):
        harness = HookHarness(monkeypatch, [active_policy()])
        await harness.run()

        assert len(harness.decision_rows) == 1
        row = harness.decision_rows[0]
        assert row["finding_id"] == "fnd_20261009_0001"
        assert row["evaluation"].mode is PolicyMode.ACTIVE
        assert row["evaluation"].policy_id == POLICY_ID
        assert row["evaluation_us"] > 0


class TestShadowHit:
    async def test_a_shadow_hit_writes_no_triage_keys_but_logs_the_decision(
        self, monkeypatch
    ):
        harness = HookHarness(monkeypatch, [shadow_policy()])
        _tuning(monkeypatch)
        await harness.run()

        # The LLM ran (shadow observes, never acts)...
        assert harness.llm_calls == 1
        f = harness.response_findings[0]
        # ...and the policy wrote nothing: the finding's triage keys are the
        # LLM's own reply, not the policy's decision.
        assert f["severity"] == "high" and f["category"] == "malware"
        assert f["ai_triage"]["result"]["confidence"] == pytest.approx(0.82)
        assert "policy_id" not in f["ai_triage"]
        # The decision row exists either way.
        assert len(harness.decision_rows) == 1
        assert harness.decision_rows[0]["evaluation"].mode is PolicyMode.SHADOW

    async def test_a_shadow_hit_backfills_its_agreement_with_the_llm(self, monkeypatch):
        harness = HookHarness(monkeypatch, [shadow_policy()])
        _tuning(monkeypatch)
        await harness.run()

        assert len(harness.backfills) == 1
        backfill = harness.backfills[0]
        # The LLM agreed on severity and action (both "high"/"investigate").
        assert backfill["agrees"] is True
        assert backfill["actual"]["severity"] == "high"
        assert backfill["actual"]["recommended_action"] == "investigate"


class TestMissAndFlag:
    async def test_a_miss_runs_the_llm_path_exactly_as_today(self, monkeypatch):
        harness = HookHarness(monkeypatch, [active_policy()])
        mismatched = finding(data_source="crowdstrike.detects")
        await harness.run(mismatched)

        # The model decided, the reply was applied, the row was recorded.
        assert harness.llm_calls == 1
        f = harness.response_findings[0]
        assert f["category"] == "malware"  # the LLM's category, not the policy's
        assert len(harness.decision_rows) == 1
        assert harness.decision_rows[0]["evaluation"] is None  # a miss row

    async def test_a_record_failure_fails_closed_to_the_llm(self, monkeypatch):
        harness = HookHarness(monkeypatch, [active_policy()])

        def broken_record(finding_id, evaluation, evaluation_us):
            raise RuntimeError("db down")

        monkeypatch.setattr(store, "record_decision", broken_record)
        await harness.run()

        # The evaluation could not be logged, so its decision is not acted
        # on: the LLM path runs instead and the error is counted.
        assert harness.llm_calls == 1
        assert harness.processor.stats["policy_fast_path_errors"] == 1

    async def test_the_flag_off_is_zero_behavior_change(self, monkeypatch):
        harness = HookHarness(monkeypatch, [active_policy()], flag=False)

        def no_store(*args, **kwargs):
            raise AssertionError("the store must not be touched with the flag off")

        monkeypatch.setattr(store, "load_evaluating_policies", no_store)
        monkeypatch.setattr(store, "record_decision", no_store)
        await harness.run()

        assert harness.llm_calls == 1
        assert harness.decision_rows == []
        f = harness.response_findings[0]
        assert f["category"] == "malware"


class TestDriftBrake:
    async def test_a_drift_breach_auto_suspends_the_policy(self, monkeypatch):
        harness = HookHarness(monkeypatch, [shadow_policy()])
        _tuning(monkeypatch, drift_limit=3)
        # The policy disagrees with the LLM on severity (policy high, LLM low).
        monkeypatch.setattr(
            harness.processor, "_get_ai_triage", _llm_reply_fn(severity="low")
        )
        # Two disagreements are already on record; this one is the third.
        monkeypatch.setattr(store, "disagreements_in_window", lambda *a, **k: 3)
        await harness.run()

        assert len(harness.suspensions) == 1
        suspension = harness.suspensions[0]
        assert suspension["policy_id"] == POLICY_ID
        assert suspension["version"] == 3
        assert "disagreements" in suspension["reason"]

    async def test_below_the_drift_limit_nothing_suspends(self, monkeypatch):
        harness = HookHarness(monkeypatch, [shadow_policy()])
        _tuning(monkeypatch, drift_limit=3)
        monkeypatch.setattr(
            harness.processor, "_get_ai_triage", _llm_reply_fn(severity="low")
        )
        monkeypatch.setattr(store, "disagreements_in_window", lambda *a, **k: 1)
        await harness.run()

        assert harness.suspensions == []
        assert len(harness.backfills) == 1
        assert harness.backfills[0]["agrees"] is False


def _llm_reply_fn(severity: str):
    async def fake_llm(prompt):
        return llm_reply(severity=severity), None

    return fake_llm


class TestAgreementSemantics:
    def test_agreement_compares_the_behavior_relevant_fields(self):
        decision = TriageDecision(
            severity="high",
            confidence=0.93,
            recommended_action="investigate",
            category="credential_stuffing",
            reasoning="",
        )
        assert (
            fast_path_module.decisions_agree(
                decision, {"severity": "high", "recommended_action": "investigate"}
            )
            is True
        )
        # Case differences are presentation, not disagreement.
        assert (
            fast_path_module.decisions_agree(
                decision, {"severity": "HIGH", "recommended_action": "Investigate"}
            )
            is True
        )
        assert (
            fast_path_module.decisions_agree(
                decision, {"severity": "low", "recommended_action": "investigate"}
            )
            is False
        )
        assert (
            fast_path_module.decisions_agree(
                decision, {"severity": "high", "recommended_action": "isolate"}
            )
            is False
        )
        # Category is a vocabulary mismatch, not drift; confidence is a
        # measured rate vs a self-report. Neither counts either way.
        assert (
            fast_path_module.decisions_agree(
                decision,
                {
                    "severity": "high",
                    "recommended_action": "investigate",
                    "category": "x",
                },
            )
            is True
        )
        # Nothing comparable -> inconclusive, not disagreement.
        assert fast_path_module.decisions_agree(decision, {}) is None


class TestProvenanceContent:
    def test_the_sample_evidence_drives_the_policy_identity(self):
        evidence = sample_evidence()
        assert evidence.workflow_id == "wf_hunt_cred_stuffing"
        assert evidence.consistency == pytest.approx(0.93)
