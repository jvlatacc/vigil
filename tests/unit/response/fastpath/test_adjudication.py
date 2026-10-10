"""Slow-path adjudication — the responder lane's verdicts over live
leases, and the negative test that holds the autonomy line.

No database and no LLM: the verdicts are pure functions of the lease's
observed snapshot and the finding's current fields, and the orchestrator
runs against fakes — a fake ledger recording call order, a recording
executor, a MagicMock approval service — with candidate discovery
overridden by a subclass instead of patching. The SQL underneath is
exercised by the integration suite (test_fastpath_replay.py).

The tool-surface test enumerates the published MCP tools and holds that
the containment surface carries exactly two verbs, both demotions: read
the leases, undo one. ``escalate_case`` already exists as a
case-priority verb, so the promotion check is scoped to lease-scoped
names — the assertion is "no tool promotes a lease", not "no tool says
escalate anywhere".
"""

from __future__ import annotations

import re
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from core.response.fastpath import adjudication as adj
from core.response.fastpath import gate as gate_module
from core.response.fastpath.adjudication import (
    ACTOR_ADJUDICATOR,
    DOWNGRADED,
    FALSE_POSITIVE,
    AdjudicationAction,
    FastPathAdjudicator,
    adjudicate,
    entity_type_for_target,
    first_principal,
    principals_of,
)
from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.ledger import LeaseView, Transition
from core.time import utcnow

pytestmark = pytest.mark.unit

ENABLED = FastPathConfig(enabled=True, shadow_mode=False)
DISABLED = FastPathConfig(enabled=False)


def _lease(**overrides: Any) -> LeaseView:
    """An ``applied`` lease issued on a critical finding, undo payload live."""
    now = utcnow()
    fields: Dict[str, Any] = dict(
        id="lease-abc123",
        action_type="fp_rate_limit",
        entity_type="ip",
        entity_id="203.0.113.7",
        status="applied",
        idempotency_key="fp_rate_limit:ip:203.0.113.7",
        finding_id=None,
        decision_rule="fastpath.gate.issue severity=critical",
        observed={"severity": "critical", "confidence": 0.93, "detector": "ids"},
        undo_payload={"rule_id": "rule-1"},
        is_shadow=False,
        ttl_seconds=300,
        expires_at=now + timedelta(seconds=300),
        created_at=now,
    )
    fields.update(overrides)
    return LeaseView(**fields)


def _finding(**overrides: Any) -> Dict[str, Any]:
    """A responder candidate for the leased principal, post-triage."""
    finding: Dict[str, Any] = {
        "finding_id": "f-1",
        "detector": "ids",
        "severity": "high",
        "status": "open",
        "triage_confidence": 0.95,
        "entity_context": {"src_ips": ["203.0.113.7"]},
    }
    finding.update(overrides)
    return finding


class FakeLedger:
    """Records every mutator call in order; CAS results are programmable."""

    def __init__(
        self,
        leases: Optional[Dict[str, LeaseView]] = None,
        cas_result: Any = "transition",
    ) -> None:
        self.leases = leases or {}
        self.cas_result = cas_result
        self.calls: List[Tuple[str, ...]] = []

    def get(self, lease_id: str) -> Optional[LeaseView]:
        self.calls.append(("get", lease_id))
        return self.leases.get(lease_id)

    def mark_rolled_back(self, lease_id: str, reason: str, actor: str, evidence_version=None):  # type: ignore[no-untyped-def]
        self.calls.append(("mark_rolled_back", lease_id, reason, actor))
        if self.cas_result is None:
            return None
        return Transition(
            lease_id=lease_id,
            from_status="applied",
            to_status="rolled_back",
            actor=actor,
            evidence_version=evidence_version,
            reason=reason,
        )

    def mark_failed(self, lease_id: str, reason: str, actor: str, evidence_version=None):  # type: ignore[no-untyped-def]
        self.calls.append(("mark_failed", lease_id, reason, actor))
        return None


class RecordingExecutor:
    def __init__(self) -> None:
        self.apply_calls: List[Any] = []
        self.undo_calls: List[Tuple[str, Dict[str, Any]]] = []

    async def apply(self, lease: Any) -> Dict[str, Any]:
        self.apply_calls.append(lease)
        return {"rule_id": f"rule-for-{lease.lease_id}"}

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        self.undo_calls.append((lease_id, dict(undo_payload or {})))


class RecordingRegistry:
    def __init__(self, executor: Any = None) -> None:
        self._executor = executor
        self.asked_for: List[str] = []

    def get(self, action_type: str) -> Any:
        self.asked_for.append(action_type)
        return self._executor


class FixedCandidatesAdjudicator(FastPathAdjudicator):
    """Candidate discovery and churn replaced by fixed answers — the seam."""

    def __init__(self, leases, churn: int = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._fixed_leases = list(leases)
        self._fixed_churn = churn
        self.candidate_queries: List[Dict[str, Any]] = []

    def _candidate_leases(self, finding: Dict[str, Any]) -> List[LeaseView]:
        self.candidate_queries.append(finding)
        return list(self._fixed_leases)

    def _rolled_back_in_window(self, entity_type: str, entity_id: str) -> int:
        return self._fixed_churn


def _adjudicator(leases=(), churn: int = 0, config: FastPathConfig = ENABLED):
    ledger = FakeLedger({lease.id: lease for lease in leases})
    executor = RecordingExecutor()
    approvals = MagicMock()
    approvals.create_action.return_value = SimpleNamespace(action_id="approval-1")
    adjudicator = FixedCandidatesAdjudicator(
        leases=list(leases),
        churn=churn,
        approvals=approvals,
        ledger=ledger,
        registry=RecordingRegistry(executor),
        config=config,
    )
    return adjudicator, ledger, executor, approvals


# ----------------------------------------------------------------------
# Verdicts — pure, snapshot-driven
# ----------------------------------------------------------------------


class TestVerdictAgainstSnapshot:
    def test_a_closed_finding_rolls_back_as_false_positive(self):
        verdict = adjudicate(
            _lease(), _finding(status="closed"), ENABLED, rolled_back_in_window=0
        )
        assert verdict.action is AdjudicationAction.ROLLBACK
        assert verdict.reason == FALSE_POSITIVE
        assert "closed" in verdict.rule

    def test_a_severity_demotion_rolls_back_even_inside_the_band(self):
        # critical premise, high now: still in the band, still a demotion —
        # the critical mapping's containment outruns what high earns.
        verdict = adjudicate(
            _lease(),
            _finding(severity="high", triage_confidence=0.95),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK
        assert verdict.reason == DOWNGRADED

    def test_an_out_of_band_severity_rolls_back(self):
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.93}),
            _finding(severity="medium", triage_confidence=0.95),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK
        assert verdict.reason == DOWNGRADED

    def test_a_confidence_under_the_severity_floor_rolls_back(self):
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.95}),
            _finding(severity="high", triage_confidence=0.50),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK
        assert verdict.reason == DOWNGRADED

    def test_an_untagged_confidence_reads_as_half_and_rolls_back(self):
        # Same read the gate makes pre-triage: 0.5 under the high floor.
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.95}),
            _finding(severity="high", triage_confidence=None),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK

    def test_an_unparseable_confidence_rolls_back(self):
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.95}),
            _finding(severity="high", triage_confidence="high"),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK

    def test_churn_escalates_over_the_plain_holds_condition(self):
        # Confidence 0.85 sits between the high floor (0.80) and the observed
        # premise (0.90) — without churn this holds. Three completed
        # rollback cycles in the window make it a human question instead.
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.90}),
            _finding(severity="high", triage_confidence=0.85),
            ENABLED,
            rolled_back_in_window=3,
        )
        assert verdict.action is AdjudicationAction.ESCALATE
        assert "churn" in verdict.rule

    def test_evidence_at_least_as_strong_as_the_premise_escalates(self):
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.85}),
            _finding(severity="high", triage_confidence=0.92),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ESCALATE
        assert "evidence_holds" in verdict.rule

    def test_a_severity_raise_escalates(self):
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.85}),
            _finding(severity="critical", triage_confidence=0.95),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ESCALATE

    def test_evidence_weakened_within_the_band_holds(self):
        # Above the floor, below the premise: nothing to roll back, nothing
        # to promote — the lease runs out its TTL.
        verdict = adjudicate(
            _lease(observed={"severity": "high", "confidence": 0.90}),
            _finding(severity="high", triage_confidence=0.85),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.HOLD

    def test_a_missing_observed_confidence_never_escalates(self):
        # No premise recorded: "at least as strong as when issued" is
        # unknowable, so the verdict holds rather than promote on a guess.
        verdict = adjudicate(
            _lease(observed={"severity": "high"}),
            _finding(severity="high", triage_confidence=0.99),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.HOLD

    def test_the_verdict_reads_the_snapshot_not_the_mutated_record(self):
        # Triage rewrote the finding to high/0.55 after the gate fired on
        # critical/0.96. The downgrade verdict must cite what the gate saw.
        verdict = adjudicate(
            _lease(),
            _finding(severity="high", triage_confidence=0.55),
            ENABLED,
            rolled_back_in_window=0,
        )
        assert verdict.action is AdjudicationAction.ROLLBACK
        assert "critical" in verdict.rule  # the observed severity, not "high"


# ----------------------------------------------------------------------
# Entity extraction — the gate's ordering, shared
# ----------------------------------------------------------------------


class TestEntityParityAndExtraction:
    def test_principal_order_matches_the_gate(self):
        # first_principal must pick the same principal the gate leased —
        # otherwise adjudication could miss a live lease on its own target.
        assert [key for key, _ in adj.PRINCIPAL_ENTITY_TYPES] == list(
            gate_module._PRINCIPAL_KEYS
        )

    def test_entity_type_for_target_follows_the_gate_classes(self):
        # The function re-walks the finding's context to recover the entity
        # type of the principal the gate selected — absent targets stay None.
        finding = {
            "entity_context": {
                "src_ips": ["203.0.113.7"],
                "usernames": ["alice"],
                "hostnames": ["host.corp.example"],
                "domains": ["corp.example"],
            }
        }
        assert entity_type_for_target(finding, "203.0.113.7") == "ip"
        assert entity_type_for_target(finding, "alice") == "user"
        assert entity_type_for_target(finding, "host.corp.example") == "host"
        assert entity_type_for_target(finding, "corp.example") == "domain"
        assert entity_type_for_target(finding, "not a principal") is None
        assert entity_type_for_target(finding, None) is None

    def test_first_principal_prefers_the_gate_order(self):
        finding = {
            "entity_context": {
                "domains": ["corp.example"],
                "usernames": ["alice"],
                "src_ips": ["203.0.113.7"],
            }
        }
        assert first_principal(finding) == ("ip", "203.0.113.7")

    def test_principals_of_lists_every_principal_in_gate_order(self):
        finding = {
            "entity_context": {
                "domains": ["corp.example"],
                "usernames": ["alice"],
                "src_ips": ["203.0.113.7"],
            }
        }
        assert principals_of(finding) == [
            ("ip", "203.0.113.7"),
            ("user", "alice"),
            ("domain", "corp.example"),
        ]

    def test_a_finding_without_principals_has_no_candidates(self):
        assert first_principal({"entity_context": {}}) == (None, None)
        assert principals_of({}) == []


# ----------------------------------------------------------------------
# Orchestration — the responder lane's collaborator, fakes at the seams
# ----------------------------------------------------------------------


class TestAdjudicatorOrchestration:
    async def test_a_downgrade_rolls_back_through_the_driver(self):
        lease = _lease()
        adjudicator, ledger, executor, approvals = _adjudicator([lease])
        summary = await adjudicator.on_finding(
            _finding(severity="high", triage_confidence=0.95)
        )

        assert summary["rolled_back"] == 1
        assert ("mark_rolled_back", lease.id, "downgraded", ACTOR_ADJUDICATOR) in (
            ledger.calls
        )
        assert executor.undo_calls == [(lease.id, {"rule_id": "rule-1"})]
        approvals.create_action.assert_not_called()

    async def test_a_contested_cas_counts_as_contested_not_rolled_back(self):
        lease = _lease()
        adjudicator, ledger, executor, _ = _adjudicator([lease])
        ledger.cas_result = None  # the TTL sweeper's CAS won the race
        summary = await adjudicator.on_finding(
            _finding(severity="high", triage_confidence=0.95)
        )

        assert summary["contested"] == 1
        assert summary["rolled_back"] == 0

    async def test_a_missing_executor_is_not_recorded_as_a_rollback(self):
        lease = _lease()
        adjudicator, ledger, executor, _ = _adjudicator([lease])
        adjudicator._registry = RecordingRegistry(None)
        summary = await adjudicator.on_finding(
            _finding(severity="high", triage_confidence=0.95)
        )

        assert summary["skipped_no_executor"] == 1
        assert ledger.calls == []  # never closed as rolled back
        assert executor.undo_calls == []

    async def test_an_escalation_mints_human_only_and_leaves_the_lease(self):
        lease = _lease(observed={"severity": "high", "confidence": 0.85})
        adjudicator, ledger, executor, approvals = _adjudicator([lease])
        summary = await adjudicator.on_finding(
            _finding(severity="high", triage_confidence=0.92)
        )

        assert summary["escalated"] == 1
        approvals.create_action.assert_called_once()
        kwargs = approvals.create_action.call_args.kwargs
        assert kwargs["human_only"] is True
        assert kwargs["idempotency_key"] == f"fastpath-escalate:{lease.id}"
        assert kwargs["created_by"] == ACTOR_ADJUDICATOR
        # The lease stays applied and TTL-bounded until the pipeline resolves:
        assert ledger.calls == []  # no CAS, no close
        assert executor.undo_calls == []  # no undo

    async def test_the_escalation_mint_is_idempotent_per_lease(self):
        lease = _lease(observed={"severity": "high", "confidence": 0.85})
        adjudicator, _, _, approvals = _adjudicator([lease])
        finding = _finding(severity="high", triage_confidence=0.92)

        await adjudicator.on_finding(finding)
        await adjudicator.on_finding(finding)

        keys = [
            call.kwargs["idempotency_key"]
            for call in approvals.create_action.call_args_list
        ]
        assert keys == [
            f"fastpath-escalate:{lease.id}",
            f"fastpath-escalate:{lease.id}",
        ]

    async def test_a_hold_touches_nothing(self):
        lease = _lease(observed={"severity": "high", "confidence": 0.90})
        adjudicator, ledger, executor, approvals = _adjudicator([lease])
        summary = await adjudicator.on_finding(
            _finding(severity="high", triage_confidence=0.85)
        )

        assert summary["held"] == 1
        assert ledger.calls == []
        assert executor.undo_calls == []
        approvals.create_action.assert_not_called()

    async def test_a_disabled_fastpath_reads_nothing(self):
        lease = _lease()
        adjudicator, _, executor, approvals = _adjudicator([lease], config=DISABLED)
        summary = await adjudicator.on_finding(_finding())

        assert summary == {
            "examined": 0,
            "rolled_back": 0,
            "contested": 0,
            "escalated": 0,
            "held": 0,
            "skipped_no_executor": 0,
        }
        assert adjudicator.candidate_queries == []  # no DB read at all

    async def test_an_adjudication_failure_propagates(self):
        lease = _lease()
        adjudicator, ledger, _, _ = _adjudicator([lease])
        ledger.mark_rolled_back = MagicMock(side_effect=RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await adjudicator.on_finding(
                _finding(severity="high", triage_confidence=0.95)
            )


# ----------------------------------------------------------------------
# The agent tool surface — demotions only, held by a negative test
# ----------------------------------------------------------------------


class TestAgentToolSurface:
    def _published_names(self) -> set:
        from tools.mcp.vigil import mcp

        return {tool.name for tool in mcp._tool_manager.list_tools()}

    def test_the_two_lease_tools_are_published(self):
        names = self._published_names()
        assert "lease_list" in names
        assert "propose_rollback" in names

    def test_no_tool_promotes_a_lease(self):
        names = self._published_names()
        lease_scoped = {
            name
            for name in names
            if re.search(r"lease|contain|fastpath|rollback", name)
        }
        assert lease_scoped == {"lease_list", "propose_rollback"}, (
            "The containment lease surface grew a tool. Every verb there is a "
            "demotion — read or undo — because the system may only demote its "
            "own autonomy; promoting is a person's call through the approvals "
            f"queue. Offending tools: {sorted(lease_scoped)}"
        )
        promotive = {
            name
            for name in names
            if re.search(r"commit|promote|confirm|extend|durable|permanent", name)
        }
        assert promotive & lease_scoped == set()
        # escalate_case is a case-priority verb — fine on cases, never on leases.
        assert not {"escalate_case"} & lease_scoped

    def test_propose_rollback_takes_a_lease_and_nothing_to_promote(self):
        from tools.mcp.vigil import mcp

        tool = next(
            t for t in mcp._tool_manager.list_tools() if t.name == "propose_rollback"
        )
        params = set((tool.parameters or {}).get("properties") or {})
        assert "lease_id" in params
        assert not params & {"commit", "promote", "make_durable", "permanent"}
