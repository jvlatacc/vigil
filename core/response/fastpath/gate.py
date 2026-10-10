"""The deterministic Fast-Path policy gate.

A pure predicate over the finding dict: no clock, no database, no model.
The same finding, config and counters always produce the same decision.
The daemon calls it at the evaluate step (``processor._evaluate_for_response``,
a later slice's wiring), post-store and pre-triage — the one point in the
pipeline where nothing slower than the finding itself has queued ahead.

Precedence, first match wins; the allowlist outranks severity, severity
outranks the caps' wording but not the allowlist:

1. deny_targets   — the gate never leases against a protected principal,
                    whatever the detection says, even critical.
2. enabled=False  — the kill switch: no lease, no executor consideration.
3. shadow_mode    — a stamp on the outcome, not a shortcut: every verdict
                    below carries ``is_shadow=True`` and nothing downstream
                    may apply a shadow lease. Caps and eligibility still
                    run — a shadow run that bypassed them would record
                    would-be leases the real gate never issues, and the
                    false-positive bar the rollout waits on would be
                    unmeasurable.
4. caps           — per-entity, then per-window, then the anti-flap floor.
5. eligibility    — a known principal to contain, a severity with a
                    confidence floor, the confidence to clear it, and an
                    action type this config still allows.
6. issue lease    — the severity-mapped action, TTL clamped into bounds.

Every verdict names the rule that decided it and freezes the observed
values at fire time: LLM triage rewrites severity minutes later, and
adjudication must read what the gate saw, not the mutated record.

Rule rendering: threshold comparisons reuse ``decision_rule``'s
``field=value met/not met (observed)`` shape — for a floor, the direction
is the helper's own. Caps invert the direction (reaching the cap blocks),
so they render the blocking fact plainly instead of borrowing a shape
whose "met" would read backwards in a lease ledger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from core.response.config import decision_rule
from core.response.fastpath.config import FastPathConfig
from core.telemetry import get_meter

logger = logging.getLogger(__name__)


class FastPathVerdict(str, Enum):
    """What the gate decided.

    ``issue_lease`` means "this finding earns a lease" — whether anything
    is applied is then shadow_mode's and the ledger's business, not the
    gate's.
    """

    ISSUE_LEASE = "issue_lease"
    NO_ACTION = "no_action"


# The micro-containment each eligible severity maps to. Severity-keyed and
# total for the band the config allows: the gate has no model to reason
# about recommended_action, only this table. Critical gets the stronger of
# the two v1 built-ins, high the milder friction first.
ACTION_BY_SEVERITY: Dict[str, str] = {
    "critical": "rate_limit",
    "high": "challenge",
}

# Containable principals, in selection order: the acting IP, then the
# acting user, then the implicated host, then the domain. dst_ips and
# file_hashes are not principals — they are what something was done to.
_PRINCIPAL_KEYS: tuple[str, ...] = ("src_ips", "usernames", "hostnames", "domains")


@dataclass(frozen=True)
class FastPathDecision:
    """One gate verdict, immutable and complete on its own.

    ``observed`` is the telemetry mirror frozen at fire time: the exact
    severity, confidence, detector and recommended_action the gate saw, not
    what triage later made of them (``_update_finding`` rewrites severity
    post-hoc; adjudication compares against this, never the mutated record).
    """

    verdict: FastPathVerdict
    decision_rule: str
    is_shadow: bool
    action_type: Optional[str] = None
    target: Optional[str] = None
    ttl_seconds: Optional[int] = None
    observed: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateCounters:
    """Live lease state the caller reads from the ledger (a later slice).

    The gate itself never touches the database — wiring hands the numbers
    in, which is what keeps this module importable without one.
    """

    active_leases_for_entity: int = 0
    leases_in_window: int = 0
    seconds_since_last_rollback: Optional[float] = None


def _first_str(value: Any) -> Optional[str]:
    """First usable string of an entity_context field, else None.

    Tolerates a bare string where a list was promised; findings come from
    vendors, not from schema validators.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _no_action(
    config: FastPathConfig, observed: Dict[str, Any], rule: str
) -> FastPathDecision:
    """A blocked verdict carrying the rule that decided it."""
    return FastPathDecision(
        verdict=FastPathVerdict.NO_ACTION,
        decision_rule=rule,
        is_shadow=config.shadow_mode,
        observed=observed,
    )


def evaluate(
    finding: Dict[str, Any],
    config: FastPathConfig,
    counters: Optional[GateCounters] = None,
) -> FastPathDecision:
    """Decide whether this finding earns a containment lease.

    Pure and total: the same inputs give the same verdict, nothing here
    reads a clock or a database, and no input shape raises. Live lease
    counts arrive as ``counters``; without one, the gate sees an empty
    slate.
    """
    counters = counters or GateCounters()

    severity = str(finding.get("severity") or "").strip().lower()
    # The processor reads the same field with the same default (0.5): a
    # finding that has not been triaged carries its absence.
    try:
        confidence = float(finding.get("triage_confidence", 0.5))
    except (TypeError, ValueError):
        confidence = None
    detector = str(finding.get("detector") or finding.get("data_source") or "")
    recommended = str(finding.get("recommended_action") or "").strip().lower()

    entities = finding.get("entity_context") or {}
    if not isinstance(entities, dict):
        entities = {}
    target: Optional[str] = None
    for key in _PRINCIPAL_KEYS:
        candidate = _first_str(entities.get(key))
        if candidate is not None:
            target = candidate
            break

    observed: Dict[str, Any] = {
        "severity": severity,
        "confidence": confidence,
        "detector": detector,
        "recommended_action": recommended,
        "finding_id": finding.get("finding_id"),
        "target": target,
    }

    # (a) The critical-asset allowlist outranks every detection: no lease
    # against a protected principal, even on a critical severity. The check
    # is on the lease target — the principal the action would touch —
    # matched case-insensitively (see FastPathConfig.deny_targets).
    if target is not None:
        deny_lowered = {denied.lower() for denied in config.deny_targets}
        if target.lower() in deny_lowered:
            return _no_action(
                config, observed, decision_rule("fastpath.deny_targets", target)
            )

    # (b) Kill switch. A disabled gate reports disabled — a decision, not a
    # silence (the auto_response precedent).
    if not config.enabled:
        return _no_action(config, observed, decision_rule("fastpath.enabled", False))

    # (c) Shadow mode stamps everything below (see module docstring).
    # (d) Blast-radius caps, each blocking on its own. The counts arrived
    # from the ledger; the gate renders which one fired.
    if counters.active_leases_for_entity >= config.max_leases_per_entity:
        return _no_action(
            config,
            observed,
            f"fastpath.max_leases_per_entity={config.max_leases_per_entity}"
            f" reached ({counters.active_leases_for_entity} active)",
        )
    if counters.leases_in_window >= config.max_leases_per_window:
        return _no_action(
            config,
            observed,
            f"fastpath.max_leases_per_window={config.max_leases_per_window}"
            f" reached ({counters.leases_in_window} in"
            f" {config.window_seconds}s)",
        )
    if counters.seconds_since_last_rollback is not None and (
        counters.seconds_since_last_rollback < config.anti_flap_rollback_floor_seconds
    ):
        return _no_action(
            config,
            observed,
            f"fastpath.anti_flap_rollback_floor_seconds="
            f"{config.anti_flap_rollback_floor_seconds} not met"
            f" ({counters.seconds_since_last_rollback:.0f}s since rollback)",
        )

    # (e) Eligibility: a known principal, a severity with a floor, the
    # confidence to clear it, and an action type this config still allows.
    if target is None:
        # An unknown or unclassified entity gets the lowest-impact action:
        # none.
        return _no_action(config, observed, "fastpath.entity_class=unknown")

    floor = {
        "critical": config.critical_action_floor,
        "high": config.high_action_floor,
    }.get(severity)
    if floor is None or severity not in config.allowed_severities:
        return _no_action(
            config,
            observed,
            f"fastpath.severity={severity or 'unset'} not in allowed_severities",
        )
    if confidence is None or not 0.0 <= confidence <= 1.0:
        # A confidence is a probability. Anything else (5.0, NaN) is a
        # caller inflating the number and must not read as "above the
        # floor" (the approval_requirement precedent).
        return _no_action(config, observed, f"fastpath.confidence_range={confidence}")
    if confidence < floor:
        return _no_action(
            config,
            observed,
            decision_rule(f"fastpath.{severity}_action_floor", floor, confidence),
        )
    action_type = ACTION_BY_SEVERITY[severity]
    if action_type not in config.allowed_action_types:
        return _no_action(
            config,
            observed,
            f"fastpath.action_type={action_type} not in allowed_action_types",
        )

    # (f) The lease earns itself. The TTL is the configured default clamped
    # into bounds: whatever the settings say, no lease outlives
    # max_ttl_seconds.
    ttl = min(
        max(config.default_ttl_seconds, config.min_ttl_seconds), config.max_ttl_seconds
    )
    return FastPathDecision(
        verdict=FastPathVerdict.ISSUE_LEASE,
        decision_rule=decision_rule(
            f"fastpath.{severity}_action_floor", floor, confidence
        ),
        is_shadow=config.shadow_mode,
        action_type=action_type,
        target=target,
        ttl_seconds=ttl,
        observed=observed,
    )


# Same ceiling as every other response-domain instrument: created on first
# use, because ``get_meter`` before ``init_telemetry`` is a permanent no-op
# and this module is imported at daemon boot.
_verdicts_counter: Any = None


def _verdicts() -> Any:
    """The verdict counter, created on first use."""
    global _verdicts_counter
    if _verdicts_counter is None:
        _verdicts_counter = get_meter("vigil.response.fastpath").create_counter(
            "vigil.fastpath.verdicts",
            description="Fast-Path gate verdicts, by verdict and shadow flag",
            unit="1",
        )
    return _verdicts_counter


def record_decision(decision: FastPathDecision) -> None:
    """Count one verdict; fire/skip/shadow roll up from the attributes.

    Best-effort: a telemetry failure is logged and dropped, never raised —
    the decision already happened, and the caller must not lose it to a
    metric.
    """
    try:
        _verdicts().add(
            1,
            {"verdict": decision.verdict.value, "shadow": str(decision.is_shadow)},
        )
    except Exception as exc:  # telemetry is best-effort; see docstring
        logger.debug("fastpath verdict counter failed: %s", exc)
