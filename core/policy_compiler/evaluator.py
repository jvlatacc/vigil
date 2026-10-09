"""Pure in-process evaluation: policies in, first match out, no I/O.

This is the fast path's hot loop — the code that runs before any LLM call.
It touches only pre-LLM finding fields (data source, technique predictions,
entity-context shapes, explicit workflow identity) and never mutates the
finding; the daemon hook applies what a match returns. Determinism is the
contract: the same finding against the same policy sequence yields the same
decision bit for bit — the only quantity that varies is ``evaluation_us``.

Workflow identity has grounded semantics: no polled finding carries a
workflow field (services/daemon/poller.py writes none; the scheduler's only
``workflow_id`` is its own hunt-steering injection), so ``match.workflow_id``
is the archetype's origin, provenance the match clause names. When a finding
does claim a workflow explicitly — a future intake path or workflow-created
finding — it must be the archetype's own workflow for the policy to fire;
when absent, the observable predicates decide.

Field-access rules are fail-closed:

- a missing, null, or non-string ``data_source`` matches no data-source clause;
- ``mitre_predictions`` contributes techniques only as the canonical
  ``{technique_id: confidence}`` mapping the poller normalizes to
  (services/daemon/poller.py ``normalize_mitre_predictions``) — anything else
  carries no techniques;
- an entity-context key contributes its type only when its value is non-empty
  (a list with entries, a non-empty string); empty and null values claim
  nothing, and keys the daemon has never written pass through verbatim.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, NamedTuple, Optional, Sequence, Union

from core.policy_compiler.models import (
    ENTITY_CONTEXT_TYPE_BY_KEY,
    EntityTypeSet,
    MatchClause,
    PolicyIR,
    PolicyMode,
    TechniqueSet,
    mode_for_state,
)

_PredicateSet = Union[TechniqueSet, EntityTypeSet]


@dataclass(frozen=True)
class TriageDecision:
    """The triage a matching policy replays — the LLM key set, compiled.

    Validation pins every field at compile time, so an applied decision
    always writes the complete key set: the downstream contract is
    "indistinguishable from the LLM path, except faster and cheaper."
    """

    severity: str
    confidence: float
    recommended_action: str
    category: str
    reasoning: str
    actions_human_only: bool = True

    def as_triage_result(self) -> dict[str, Any]:
        """The inner ``ai_triage.result`` block — the LLM triage_result keys."""
        return {
            "severity": self.severity,
            "confidence": self.confidence,
            "category": self.category,
            "recommended_action": self.recommended_action,
            "reasoning": self.reasoning,
        }


class PolicyEvaluation(NamedTuple):
    """What the fast path needs to act: the matched policy and its decision."""

    policy_id: str
    policy_version: int
    content_hash: str
    mode: PolicyMode
    decision: TriageDecision
    evaluation_us: int

    def as_finding_fields(self) -> dict[str, Any]:
        """The finding-dict fields the LLM triage path writes
        (services/daemon/processor.py ``_apply_triage_result``)."""
        return {
            "severity": self.decision.severity,
            "triage_confidence": self.decision.confidence,
            "category": self.decision.category,
            "recommended_action": self.decision.recommended_action,
            "triage_reasoning": self.decision.reasoning,
        }

    def as_ai_triage_block(self, timestamp: str) -> dict[str, Any]:
        """The ``ai_triage`` metadata block plus the provenance the spec pins.

        ``timestamp`` is the caller's clock (the hook's ``utcnow().isoformat()``)
        — this module reads no wall clock of its own.
        """
        return {
            "timestamp": timestamp,
            "result": self.decision.as_triage_result(),
            "source": "jit_policy",
            "policy_id": self.policy_id,
            "version": self.policy_version,
            "content_hash": self.content_hash,
            "evaluation_us": self.evaluation_us,
        }


def _has_content(value: Any) -> bool:
    """Whether a finding field value claims presence (empty claims nothing)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, frozenset, Mapping)):
        return len(value) > 0
    return True


def _observed_entity_types(entity_context: Any) -> frozenset[str]:
    """The entity-context key TYPES the finding actually carries."""
    if not isinstance(entity_context, Mapping):
        return frozenset()
    types = set()
    for key, value in entity_context.items():
        if _has_content(value):
            types.add(ENTITY_CONTEXT_TYPE_BY_KEY.get(str(key), str(key)))
    return frozenset(types)


def _observed_techniques(mitre_predictions: Any) -> frozenset[str]:
    """The technique ids predicted for the finding.

    Presence is the signal (the per-technique confidence is a ranking input,
    not a matching one). Only the canonical mapping form counts; a list or
    other shape was never normalized and carries no techniques.
    """
    if not isinstance(mitre_predictions, Mapping):
        return frozenset()
    return frozenset(str(technique) for technique in mitre_predictions)


def _as_token(value: Any) -> Optional[str]:
    """The field as a matchable token, or None when it cannot be one."""
    if isinstance(value, str) and value:
        return value
    return None


def _single_value_matches(
    expected: Optional[tuple[str, ...]], value: Optional[str]
) -> bool:
    """A single-valued field (data_source) against its any-of list."""
    if expected is None:
        return True
    if value is None:
        return False
    return value in expected


def _set_matches(
    expected_any_of: tuple[str, ...],
    expected_all_of: tuple[str, ...],
    observed: frozenset[str],
) -> bool:
    """A set-valued field against any_of (intersection) and all_of (subset)."""
    if expected_any_of and not observed.intersection(expected_any_of):
        return False
    if expected_all_of and not set(expected_all_of).issubset(observed):
        return False
    return True


def _group_of(
    predicate: Optional[_PredicateSet],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (predicate.any_of, predicate.all_of) if predicate is not None else ((), ())


def _matches(policy: PolicyIR, finding: Mapping[str, Any]) -> bool:
    match: MatchClause = policy.match

    claimed_workflow = _as_token(finding.get("workflow_id"))
    if claimed_workflow is not None and claimed_workflow != match.workflow_id:
        return False

    if not _single_value_matches(
        match.data_source, _as_token(finding.get("data_source"))
    ):
        return False

    tech_any_of, tech_all_of = _group_of(match.techniques)
    if not _set_matches(
        tech_any_of,
        tech_all_of,
        _observed_techniques(finding.get("mitre_predictions")),
    ):
        return False

    type_any_of, type_all_of = _group_of(match.entity_context_types)
    if not _set_matches(
        type_any_of, type_all_of, _observed_entity_types(finding.get("entity_context"))
    ):
        return False

    return True


def _decision_of(policy: PolicyIR) -> TriageDecision:
    decision = policy.decision
    return TriageDecision(
        severity=decision.severity,
        confidence=decision.confidence,
        recommended_action=decision.recommended_action,
        category=decision.category,
        reasoning=decision.reasoning,
        actions_human_only=decision.actions_human_only,
    )


def evaluate(
    policies: Sequence[PolicyIR], finding: Mapping[str, Any]
) -> Optional[PolicyEvaluation]:
    """First matching policy wins. Pure function over pre-LLM finding fields.

    Same finding + same policy sequence => same decision, bit for bit. The
    caller supplies the order (the hook loads the evaluating rows in its
    documented order); ``candidate`` and ``retired`` policies are never
    evaluated and raise here — filter them before calling.

    ``evaluation_us`` measures the whole scan (match loop included), taken
    just before returning. A miss returns None — the hook times the call
    itself for the no-match decision row.
    """
    started_ns = time.perf_counter_ns()
    matched: Optional[tuple[PolicyIR, str]] = None
    for policy in policies:
        content_hash = policy.content_hash
        if content_hash is None:
            raise ValueError(
                f"policy {policy.policy_id}: no content hash — an unpinned "
                "policy cannot be trusted or recorded"
            )
        if _matches(policy, finding):
            matched = (policy, content_hash)
            break
    evaluation_us = (time.perf_counter_ns() - started_ns) // 1000
    if matched is None:
        return None
    policy, content_hash = matched
    return PolicyEvaluation(
        policy_id=policy.policy_id,
        policy_version=policy.version,
        content_hash=content_hash,
        mode=mode_for_state(policy.state),
        decision=_decision_of(policy),
        evaluation_us=evaluation_us,
    )
