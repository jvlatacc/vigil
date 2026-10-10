"""The fast path's runtime orchestration: load, evaluate, record, brake.

The daemon hook (``services/daemon/processor.py``) is async and must stay
thin; this module owns the synchronous workflow around the pure evaluator:

1. load the evaluating policies (TTL-cached — the policy set changes only
   through lifecycle transitions, and a per-finding load query would pay a
   round trip to save one),
2. evaluate the finding against them and record EVERY evaluation — hit or
   miss, shadow or active — to ``compiled_policy_decisions``,
3. after a shadow hit's LLM triage lands, backfill the row's agreement with
   the eventual LLM result, and
4. brake: when a policy's recorded disagreements reach the drift limit, the
   same rows the audit sees suspend it (active/shadow -> suspended), so a
   policy that silently rots stops being trusted before a human looks.

Tunables resolve through the runtime-config keys (``core.policy_compiler.config``)
with the same DB → env → default chain the maturity thresholds use.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, List, Mapping, NamedTuple, Optional

from core.platform import runtime_config
from core.policy_compiler import config as pc_config
from core.policy_compiler import store
from core.policy_compiler.evaluator import PolicyEvaluation, TriageDecision, evaluate
from core.policy_compiler.models import PolicyIR

logger = logging.getLogger(__name__)

# How long the loaded policy set may serve before re-reading the table. A
# lifecycle transition (promote/suspend/retire) is visible within this window,
# matching the runtime-config cache's freshness contract.
LOAD_TTL_SECONDS = 60


class FastPathOutcome(NamedTuple):
    """What one fast-path pass hands back to the daemon hook.

    ``evaluation`` is None on a miss (or when no policies evaluate). The row
    id is kept so the hook can backfill the shadow agreement onto the same
    row after the LLM triage lands — one finding, one decision row.
    """

    evaluation: Optional[PolicyEvaluation]
    decision_row_id: Optional[int]
    evaluation_us: int


def decisions_agree(
    policy_decision: TriageDecision, actual_result: Mapping[str, Any]
) -> Optional[bool]:
    """Behavior-relevant agreement between a policy's replay and the LLM.

    Compares the fields that change downstream behavior — ``severity`` and
    ``recommended_action``, whose vocabularies are shared (the IR restates
    the daemon's own vocabularies) and which drive ``_evaluate_for_response``
    and the approval bands. ``category`` is excluded: the policy's category
    names the compiled archetype (a closure token, e.g. ``credential_stuffing``)
    while the LLM's names the triage prompt's taxonomy (e.g.
    ``credential_theft``) — a vocabulary mismatch, not drift. ``confidence``
    is excluded: a measured agreement rate against a model's self-report
    differs by construction, and the consumption bands absorb small deltas.

    Returns None when nothing is comparable (the LLM wrote neither field) —
    an inconclusive comparison backfills nothing, rather than guessing.
    """
    comparable: List[bool] = []
    for field_name in ("severity", "recommended_action"):
        actual = actual_result.get(field_name)
        if isinstance(actual, str) and actual:
            comparable.append(actual.lower() == getattr(policy_decision, field_name))
    if not comparable:
        return None
    return all(comparable)


class PolicyFastPath:
    """One daemon processor's fast path: cached policies, recorded decisions."""

    def __init__(self, load_ttl_seconds: int = LOAD_TTL_SECONDS):
        self._load_ttl_seconds = load_ttl_seconds
        self._policies: Optional[List[PolicyIR]] = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _evaluating_policies(self) -> List[PolicyIR]:
        """The evaluating policy set, re-read at most once per TTL."""
        with self._lock:
            if (
                self._policies is not None
                and time.monotonic() - self._loaded_at < self._load_ttl_seconds
            ):
                return self._policies
            policies = store.load_evaluating_policies()
            self._policies = policies
            self._loaded_at = time.monotonic()
            return policies

    def evaluate_and_record(self, finding: Mapping[str, Any]) -> FastPathOutcome:
        """Evaluate one finding and record the decision row; never the LLM.

        ``evaluation_us`` is the evaluator's own scan measure on a hit; on a
        miss the caller's wall-clock around the (empty) scan stands in — the
        evaluator returns None without a duration. Recording is not optional:
        a decision row that cannot be written raises, and the hook fails
        closed to the LLM path — an unlogged decision is not trusted.
        """
        policies = self._evaluating_policies()
        started_ns = time.perf_counter_ns()
        evaluation = evaluate(policies, finding)
        scan_us = (time.perf_counter_ns() - started_ns) // 1_000
        evaluation_us = evaluation.evaluation_us if evaluation else scan_us

        finding_id = str(finding.get("finding_id") or "")
        row_id = store.record_decision(finding_id, evaluation, evaluation_us)
        return FastPathOutcome(
            evaluation=evaluation,
            decision_row_id=row_id,
            evaluation_us=evaluation_us,
        )

    def record_llm_outcome(
        self, outcome: FastPathOutcome, actual_result: Mapping[str, Any]
    ) -> None:
        """Backfill a shadow hit's agreement with the LLM triage; brake on drift.

        The daemon calls this after the LLM path ran over a shadow-matched
        finding. Only a comparable, recorded disagreement moves the drift
        counter; reaching the limit suspends the policy version that drifted.
        """
        evaluation = outcome.evaluation
        if evaluation is None or outcome.decision_row_id is None:
            return

        agrees = decisions_agree(evaluation.decision, actual_result)
        if agrees is None:
            return

        store.backfill_llm_agreement(outcome.decision_row_id, actual_result, agrees)
        if agrees:
            return

        drift_limit = int(
            runtime_config.get_ai_operations_setting(
                pc_config.DRIFT_LIMIT_KEY, pc_config.DRIFT_LIMIT_DEFAULT
            )
        )
        window_days = int(
            runtime_config.get_ai_operations_setting(
                pc_config.WINDOW_DAYS_KEY, pc_config.WINDOW_DAYS_DEFAULT
            )
        )
        disagreements = store.disagreements_in_window(
            evaluation.policy_id, evaluation.policy_version, window_days
        )
        if disagreements < drift_limit:
            return

        store.suspend_for_drift(
            evaluation.policy_id,
            evaluation.policy_version,
            reason=(
                f"{disagreements} disagreements with the eventual LLM triage in "
                f"the {window_days}-day window (drift limit {drift_limit})"
            ),
        )
