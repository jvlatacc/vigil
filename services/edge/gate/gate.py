"""The decision gate — the only component that can authorize action.

Deterministic authority: the rule match and the signed bands dispose; the SLM
verdict is advisory confidence that can lower, never raise (design spec,
"Decision gate — the deterministic spine"). Malformed model output degrades to
deterministic-only. A held decision is a Decision with outcome HOLD —
journaled, never dropped: the drift report must show the near-misses, not
only the fires.

Pure function, no I/O: the daemon classifies first and hands the verdict in,
so tests drive every branch without a model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from services.edge.gate.tiers import AutonomyTier
from services.edge.observations.base import Observation
from services.edge.policy.model import SEVERITIES, Bundle

SEVERITY_CONFIDENCE: dict[str, float] = {
    # Deterministic floors for a signed rule's severity_floor. high (0.95)
    # crosses the spec's example auto-act band (0.92); medium (0.85) lands in
    # its escalate band (0.85) — hold, on purpose, until the operator signs a
    # lower band or a higher floor.
    "critical": 0.98,
    "high": 0.95,
    "medium": 0.85,
    "low": 0.70,
}
assert set(SEVERITY_CONFIDENCE) == set(SEVERITIES)


class Outcome(StrEnum):
    EXECUTE = "execute"
    HOLD = "hold"
    JOURNAL_ONLY = "journal_only"


@dataclass(frozen=True)
class SlmVerdict:
    """A structured advisory classification. Malformed model output never
    becomes a usable verdict — the advisor returns one with wellformed=False
    and the gate runs deterministic-only (W: model output is untrusted
    input)."""

    confidence: float
    model_id: str
    model_digest: str
    classification: str
    evidence: str
    wellformed: bool = True


@dataclass(frozen=True)
class Action:
    action_type: str
    executor: str
    target: str
    ttl_seconds: int


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    rule_string: str
    actor: str
    tier: AutonomyTier
    confidence: float | None = None
    action: Action | None = None
    reason: str = ""


class CapsView(Protocol):
    """What the gate needs to know about live caps. The journal implements
    this; tests use an in-memory view. Caps are read from the signed bundle,
    never from the environment."""

    def executed_in_last_hour(self, action_type: str, now: datetime) -> int: ...

    def active_blocks(self, now: datetime) -> int: ...


def decision_rule_string(
    *, rule_id: str | None, tier: AutonomyTier, confidence: float | None, reason: str
) -> str:
    """Parseable decision rule, the house pattern of core.response's
    decision_rule(): fixed space-separated key=value tokens analysts and
    tests can match on."""
    label = f"edge.{rule_id}" if rule_id else "edge.observe"
    parts = [label, f"tier=tier{tier.value}"]
    if confidence is not None:
        parts.append(f"conf={confidence:.2f}")
    if reason:
        parts.append(f"reason={reason}")
    return " ".join(parts)


def decide(
    observation: Observation,
    bundle: Bundle,
    verdict: SlmVerdict | None,
    *,
    caps: CapsView,
    node_id: str,
    now: datetime | None = None,
) -> Decision:
    """One observation, one decision. The bundle's tier, bands, caps, TTLs
    and action list are the whole authority; the SLM verdict is confidence
    that may only lower the deterministic floor."""
    at = now or datetime.now(UTC)
    tier = bundle.effective_tier(at)
    actor = f"edge:{node_id}@v{bundle.version}"

    # 1. Trust + validity: expired or never-trusted bundle -> Tier 0,
    #    journal, return (the cache normally screens this first).
    if tier is AutonomyTier.TIER_0:
        return Decision(
            outcome=Outcome.JOURNAL_ONLY,
            rule_string=decision_rule_string(
                rule_id=None, tier=tier, confidence=None, reason="tier0"
            ),
            actor=actor,
            tier=tier,
            reason="tier0",
        )

    # 2. Deterministic rule match first — rules alone may act at their floor.
    rule = bundle.match(observation)
    if rule is None:
        return Decision(
            outcome=Outcome.JOURNAL_ONLY,
            rule_string=decision_rule_string(
                rule_id=None, tier=tier, confidence=None, reason="no_rule_match"
            ),
            actor=actor,
            tier=tier,
            reason="no_rule_match",
        )

    # 3. The SLM refines: it may lower, never raise. At Tier 1 the model is
    #    not consulted at all — exact bundle IOCs only. Malformed output is
    #    ignored wholesale (deterministic-only).
    confidence = SEVERITY_CONFIDENCE[rule.severity_floor]
    if (
        bundle.autonomy_tier >= AutonomyTier.TIER_2
        and verdict is not None
        and verdict.wellformed
    ):
        confidence = min(confidence, _clamp01(verdict.confidence))

    # 4. Bands, read from the signed bundle.
    policy = bundle.decision
    if confidence < policy.escalate_confidence:
        return _hold(rule, tier, confidence, actor, "below_escalate_band")
    if confidence < policy.auto_act_confidence:
        return _hold(rule, tier, confidence, actor, "below_auto_act_band")

    # 5. Action selection: the rule's dest kind picks the action type; the
    #    bundle's allowed_actions picks the executor and bounds the TTL.
    action_type = "block_ip" if rule.dest_kind == "ip" else "block_domain"
    target = observation.dest_ip if rule.dest_kind == "ip" else observation.dest_domain
    if not target:
        return _hold(rule, tier, confidence, actor, "missing_target")
    allowed = next(
        (a for a in bundle.allowed_actions if a.action_type == action_type), None
    )
    if allowed is None:
        return _hold(rule, tier, confidence, actor, "no_allowed_action")
    ttl = policy.default_block_ttl_seconds
    if allowed.max_ttl_seconds is not None:
        ttl = min(ttl, allowed.max_ttl_seconds)

    # 6. Caps: exhaustion holds the decision — the near-miss is journaled and
    #    shows up in the drift report; the observation is never dropped.
    if caps.executed_in_last_hour(action_type, at) >= policy.max_actions_per_hour:
        return _hold(rule, tier, confidence, actor, "cap_exhausted")
    if caps.active_blocks(at) >= policy.max_active_blocks:
        return _hold(rule, tier, confidence, actor, "cap_exhausted")

    action = Action(
        action_type=action_type,
        executor=allowed.executor,
        target=target,
        ttl_seconds=ttl,
    )
    return Decision(
        outcome=Outcome.EXECUTE,
        rule_string=decision_rule_string(
            rule_id=rule.rule_id, tier=tier, confidence=confidence, reason=""
        ),
        actor=actor,
        tier=tier,
        confidence=confidence,
        action=action,
    )


def _hold(
    rule, tier: AutonomyTier, confidence: float, actor: str, reason: str
) -> Decision:
    return Decision(
        outcome=Outcome.HOLD,
        rule_string=decision_rule_string(
            rule_id=rule.rule_id, tier=tier, confidence=confidence, reason=reason
        ),
        actor=actor,
        tier=tier,
        confidence=confidence,
        reason=reason,
    )


def _clamp01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return min(1.0, max(0.0, value))
