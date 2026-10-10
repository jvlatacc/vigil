"""The fast-path policy: a pure decision, with no LLM and no side effects.

Everything here runs inline in the daemon's processing path, between the
moment a finding is stored and the moment the slow path is enqueued. The
module imports the standard library and the domain's ``decision_rule``
renderer and nothing else: no provider, no queue, no database, no
``services`` import (``core`` must not import ``services``). The caller owns
the world — it hands in the triage result and the live speculative
population, and acts on the decision that comes back.

Two tiers, from the feature spec:

- **T1** (post-triage, the default tier): Gate 1's predicates — severity
  critical/high, or a recommended isolate/block — plus the review threshold
  on the triage confidence.
- **T0** (pre-triage, opt-in): source-native signals only — source
  severity, MITRE predictions, entity IPs — for the fastest possible first
  restriction. Narrower than T1 on purpose, because it acts on the
  weakest signal basis at the moment adjudication has least to work with.
  When enabled it also backstops a T1 refusal; the operator who turns it on
  has declared source-native critical signals actionable on their own.
"""

import ipaddress
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from core.response.config import decision_rule
from core.response.fastpath.config import FastPathConfig


@dataclass(frozen=True)
class TriageSignal:
    """The triage fields a T1 decision reads, as the processor stamps them.

    Triage in Vigil is one structured LLM call whose fields land on the
    finding (``severity``, ``triage_confidence``, ``recommended_action``) —
    there is no triage object to pass. The caller folds those fields into
    this record at the seam, so the policy never reads anything but what
    the triage call concluded.
    """

    severity: str
    confidence: float
    recommended_action: str


@dataclass(frozen=True)
class FastPathDecision:
    """A restriction the policy would apply, with the recipe to explain it.

    ``signals`` carries the fields the rule read, plus the finding id — it
    becomes the adjudicator's evidence. ``rule`` is the rendered deciding
    rule; decision sites render, never assemble (#917 discipline).
    """

    action_type: str
    target: str
    ttl_seconds: int
    rule: str
    signals: dict[str, Any]


def actionable_ip(value: Any) -> Optional[str]:
    """The host address in ``value``, or None for anything not worth acting on.

    The same discipline the daemon responder applies to ``entity_context``
    IPs: a routable unicast address or nothing. Loopback, unspecified,
    multicast, link-local, and reserved space is refused, and an
    IPv4-mapped IPv6 literal is unrolled to its IPv4 form. Reimplemented
    here rather than imported because ``core`` must not import ``services``.
    """
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if (
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_link_local
        or ip.is_reserved
    ):
        return None
    return str(ip)


def _fast_path_target(finding: Mapping[str, Any]) -> Optional[str]:
    """The finding's first routable unicast source IP, or None.

    IP-only by design: the responder's hostname fallback produces a
    proposal a person weighs; a speculative restriction fired in
    milliseconds does not resolve names.
    """
    entity_context = finding.get("entity_context") or {}
    for candidate in entity_context.get("src_ips") or []:
        ip = actionable_ip(candidate)
        if ip is not None:
            return ip
    return None


def _t1_decision(
    finding: Mapping[str, Any],
    triage: TriageSignal,
    target: str,
    config: FastPathConfig,
) -> Optional[FastPathDecision]:
    """The post-triage tier: Gate 1's predicates plus the review floor."""
    severity = triage.severity.strip().lower()
    recommended = triage.recommended_action.strip().lower()
    gate_one = severity in ("critical", "high") or recommended in (
        "isolate",
        "block",
    )
    if not gate_one:
        return None
    # A confidence is a probability. Anything else (5.0, NaN) is a caller
    # inflating the number, and must not read as "above the threshold".
    if not 0.0 <= triage.confidence <= 1.0:
        return None
    if triage.confidence < config.review_threshold:
        return None
    return FastPathDecision(
        action_type="rate_limit",
        target=target,
        ttl_seconds=config.default_ttl_seconds,
        rule=decision_rule(
            "fast_path.review_threshold", config.review_threshold, triage.confidence
        ),
        signals={
            "tier": "t1",
            "finding_id": finding.get("finding_id"),
            "severity": severity,
            "recommended_action": recommended,
            "confidence": triage.confidence,
        },
    )


def _t0_decision(
    finding: Mapping[str, Any],
    target: str,
    config: FastPathConfig,
) -> Optional[FastPathDecision]:
    """The pre-triage tier: source-native fields only, narrower than T1."""
    severity = str(finding.get("severity") or "").strip().lower()
    mitre_predictions = finding.get("mitre_predictions") or {}
    if severity != "critical" or not mitre_predictions:
        return None
    return FastPathDecision(
        action_type="rate_limit",
        target=target,
        ttl_seconds=config.default_ttl_seconds,
        rule=decision_rule("fast_path.pre_triage_source_severity", severity),
        signals={
            "tier": "t0",
            "finding_id": finding.get("finding_id"),
            "source_severity": severity,
            "mitre_predictions": dict(mitre_predictions),
        },
    )


def evaluate_fast_path(
    finding: Mapping[str, Any],
    triage: Optional[TriageSignal],
    config: FastPathConfig,
    active_speculative_by_target: Optional[Mapping[str, int]] = None,
) -> Optional[FastPathDecision]:
    """The fast-path decision, or None when nothing may be restricted.

    Pure: the same inputs always yield the same decision, and None is a
    refusal — the caller learns nothing and acts on nothing. Every guard
    passes through here: the master switch, the action-type allowlist, a
    routable unicast target, the per-target cap, then the tiers.

    Counting the live speculative population is a database read, so the
    caller supplies it as ``active_speculative_by_target`` (target -> count)
    and this module stays I/O-free.
    """
    if not config.enabled:
        return None
    if "rate_limit" not in config.allowed_action_types:
        return None
    target = _fast_path_target(finding)
    if target is None:
        return None
    active = (active_speculative_by_target or {}).get(target, 0)
    if active >= config.max_speculative_per_target:
        return None
    decision = None
    if triage is not None:
        decision = _t1_decision(finding, triage, target, config)
    # T0 is a net, not a ladder rung: when its tier is enabled it also
    # catches a T1 refusal, because the operator who turned it on has
    # declared source-native critical signals actionable on their own.
    if decision is None and config.pre_triage_enabled:
        decision = _t0_decision(finding, target, config)
    return decision
