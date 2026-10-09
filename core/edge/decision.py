"""The local decision ladder: the only path from a rule match to enforcement.

A pure function in the ``core/response/config.py`` style — no I/O, no clock
reads, no settings: every input is a value, including ``now`` and the hourly
budget, so a decision is reconstructible and testable under a controllable
clock. It refuses by default; the checks run in a fixed order and each
refusal carries a class (what the journal records and alerts on) plus a
rendered ``decision_rule`` (what the operator reads), mirroring the
``response_action_decision`` / ``approval_requirement`` rendering.

Three inputs deserve their why. The ``pack`` is the verified, version-gated
policy — the envelope comes from it, never from DB or env. The ``triage``
carries the confidence and where it came from: an SLM-sourced confidence has
no authority unless the signed envelope grants it (``allow_slm_decisions``),
so a disallowed SLM value refuses rather than silently downgrading to the
sensor channel — advisory ranking is the runtime's choice to make by passing
the sensor confidence, not the ladder's to paper over. The ``budget`` is the
in-process hourly cap derived from the envelope via
``envelope.budget_for``; the ladder re-checks it against the signed cap so a
mis-derived budget cannot widen the envelope.

Check order (each gate runs only if every earlier gate passed):

1. allowlist — the action type is in the envelope's signed allowlist
2. confidence — out of [0, 1] refuses (NaN/5.0 never read as high, the
   ``approval_requirement`` precedent), then the effective floor
   ``max(envelope.confidence_floor, rule.min_local_confidence)``
3. SLM authority — an SLM-sourced confidence without ``allow_slm_decisions``
4. reversibility — ``require_reversible`` against the known-reversible types
5. protected-target guard — before the cap, so refused decisions never
   burn budget
6. TTL ceiling
7. hourly cap — the one stateful gate
8. expiry — a stale policy never enforces, whatever the hour's budget said
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.edge.envelope import REVERSIBLE_ACTION_TYPES, HourlyBudget, action_allowed
from core.edge.policy import EdgeAction, EdgeRule, PolicyPack
from core.edge.target_guard import TargetGuard
from core.edge.wire import TS_FORMAT

__all__ = [
    "ACTION_NOT_IN_ENVELOPE",
    "BELOW_CONFIDENCE_FLOOR",
    "IRREVERSIBLE_NOT_ALLOWED",
    "POLICY_EXPIRED",
    "PROTECTED_TARGET",
    "RATE_CAP_REACHED",
    "SLM_DECISIONS_NOT_ALLOWED",
    "TTL_EXCEEDS_ENVELOPE",
    "EdgeDecision",
    "LocalTriage",
    "decide_local_action",
]

# Refusal classes — recorded as the journal's reason code, one per rung.
ACTION_NOT_IN_ENVELOPE = "action-not-in-envelope"
BELOW_CONFIDENCE_FLOOR = "below-confidence-floor"
SLM_DECISIONS_NOT_ALLOWED = "slm-decisions-not-allowed"
IRREVERSIBLE_NOT_ALLOWED = "irreversible-not-allowed"
PROTECTED_TARGET = "protected-target"
TTL_EXCEEDS_ENVELOPE = "ttl-exceeds-envelope"
RATE_CAP_REACHED = "rate-cap-reached"
POLICY_EXPIRED = "policy-expired"

TriageSource = Literal["sensor", "slm"]


@dataclass(frozen=True)
class LocalTriage:
    """What local triage concluded about one alert.

    ``confidence`` is the decision confidence in [0, 1] — the sensor/rule
    channel, or the SLM's when the SLM ran and is allowed to decide. The
    ladder refuses a confidence whose source is the SLM unless the signed
    envelope grants SLM decision authority; with ``allow_slm_decisions``
    false the SLM ranks advisory-only and the runtime passes the sensor
    confidence.
    """

    confidence: float
    source: TriageSource = "sensor"


@dataclass(frozen=True)
class EdgeDecision:
    """A decision that is safe by construction or nothing at all.

    A refusal carries ``code`` and ``decision_rule`` and nothing enforceable.
    An allowance carries what the journal records: the policy version it
    cites, the rule that fired, the action, the target, the triage, and the
    rendered rule.
    """

    allowed: bool
    decision_rule: str
    code: str | None = None
    policy_version: int | None = None
    rule_id: str | None = None
    action: EdgeAction | None = None
    target: str | None = None
    confidence: float | None = None
    triage_source: TriageSource | None = None

    @classmethod
    def refuse(cls, code: str, decision_rule: str) -> "EdgeDecision":
        return cls(allowed=False, code=code, decision_rule=decision_rule)

    @classmethod
    def allow(
        cls,
        *,
        pack: PolicyPack,
        rule: EdgeRule,
        triage: LocalTriage,
        target: str,
        decision_rule: str,
    ) -> "EdgeDecision":
        return cls(
            allowed=True,
            decision_rule=decision_rule,
            policy_version=pack.policy_version,
            rule_id=rule.rule_id,
            action=rule.action,
            target=target,
            confidence=triage.confidence,
            triage_source=triage.source,
        )


def _effective_floor(envelope_floor: float, rule_floor: float | None) -> float:
    """The confidence a match must reach: the envelope's floor raised to the
    rule's own minimum when the rule asks for more."""
    if rule_floor is None:
        return envelope_floor
    return max(envelope_floor, rule_floor)


def _at_least(field: str, value: float, observed: float) -> str:
    """Render ``field=value met/not met (observed)`` — the response-config
    comparison shape, so edge rules read like response rules."""
    verdict = "met" if observed >= value else "not met"
    return f"{field}={value:.2f} {verdict} ({observed:.2f})"


def _ts(moment: datetime) -> str:
    return moment.strftime(TS_FORMAT)


def decide_local_action(
    pack: PolicyPack,
    rule: EdgeRule,
    triage: LocalTriage,
    target: str,
    guard: TargetGuard,
    budget: HourlyBudget,
    *,
    now: datetime,
) -> EdgeDecision:
    """Decide one candidate enforcement, or refuse it.

    Every argument is a value — the verified pack, the matched rule, the
    triage, the alert-derived target, the node-configured guard, the hourly
    budget, and the instant — so the ladder performs no I/O and reads no
    clock. The budget is the ladder's only mutated input (``take``), which
    is why refused decisions that run before the cap leave it untouched.
    """
    envelope = pack.autonomy_envelope

    # 1. Allowlist: an action type the envelope never allowed cannot run,
    #    whatever a rule claims.
    if not action_allowed(envelope, rule.action.type):
        return EdgeDecision.refuse(
            ACTION_NOT_IN_ENVELOPE,
            f"edge.allowed_actions={','.join(envelope.allowed_actions)}"
            f" action={rule.action.type}",
        )

    # 2. Confidence. Range first: a confidence is a probability, and anything
    #    else (5.0, NaN) is a caller inflating the number — NaN's comparisons
    #    are all False, so without the range gate it would fall through every
    #    floor and read as high.
    if not 0.0 <= triage.confidence <= 1.0:
        return EdgeDecision.refuse(
            BELOW_CONFIDENCE_FLOOR,
            f"edge.confidence_range=0..1 observed={triage.confidence}",
        )
    floor = _effective_floor(envelope.confidence_floor, rule.min_local_confidence)
    if triage.confidence < floor:
        return EdgeDecision.refuse(
            BELOW_CONFIDENCE_FLOOR,
            _at_least("edge.confidence_floor", floor, triage.confidence),
        )

    # 3. SLM authority: advisory ranking is always fine; deciding is a signed
    #    opt-in. Refuse rather than re-label the confidence as sensor-sourced.
    if triage.source == "slm" and not envelope.allow_slm_decisions:
        return EdgeDecision.refuse(
            SLM_DECISIONS_NOT_ALLOWED,
            f"edge.allow_slm_decisions=False source=slm"
            f" confidence={triage.confidence:.2f}",
        )

    # 4. Reversibility: an action the node cannot undo never enforces while
    #    the envelope requires reversibility. Unknown types are not known
    #    reversible — the set is closed on purpose.
    if envelope.require_reversible and rule.action.type not in REVERSIBLE_ACTION_TYPES:
        return EdgeDecision.refuse(
            IRREVERSIBLE_NOT_ALLOWED,
            f"edge.require_reversible=True action={rule.action.type}",
        )

    # 5. Protected targets, before the cap: a flood of guard refusals must
    #    not exhaust the hour's budget for legitimate enforcement.
    reason = guard.check(target)
    if reason is not None:
        return EdgeDecision.refuse(PROTECTED_TARGET, f"edge.protected_target={reason}")

    # 6. TTL ceiling: a block may not outlive its authority by longer than
    #    the envelope allows.
    if rule.action.ttl_minutes > envelope.max_action_ttl_minutes:
        return EdgeDecision.refuse(
            TTL_EXCEEDS_ENVELOPE,
            f"edge.max_action_ttl_minutes={envelope.max_action_ttl_minutes}"
            f" action_ttl={rule.action.ttl_minutes}",
        )

    # 7. The hourly cap. A budget the runtime derived larger than the signed
    #    cap is the envelope being widened — refuse on the same class rather
    #    than trust the derivation.
    if budget.limit > envelope.max_actions_per_hour:
        return EdgeDecision.refuse(
            RATE_CAP_REACHED,
            f"edge.max_actions_per_hour={envelope.max_actions_per_hour}"
            f" budget={budget.limit}",
        )
    if not budget.take(now):
        return EdgeDecision.refuse(
            RATE_CAP_REACHED,
            f"edge.max_actions_per_hour={envelope.max_actions_per_hour}"
            f" taken={budget.taken}",
        )

    # 8. Expiry, judged by the injected clock: stale authority never
    #    enforces. At exactly not_after the pack is already dead.
    if now >= pack.not_after:
        return EdgeDecision.refuse(
            POLICY_EXPIRED,
            f"edge.policy_not_after={_ts(pack.not_after)} now={_ts(now)}",
        )

    return EdgeDecision.allow(
        pack=pack,
        rule=rule,
        triage=triage,
        target=target,
        decision_rule=(
            f"{rule.rule_id} met ({triage.source} {triage.confidence:.2f}"
            f" >= floor {floor:.2f}, ttl {rule.action.ttl_minutes}"
            f" <= {envelope.max_action_ttl_minutes},"
            f" cap {budget.taken}/{budget.limit})"
        ),
    )
