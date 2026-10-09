"""The confidence band for autonomous response, in one place (#916).

Every comparison against a confidence — the approval gate, the correlator's
recommendation ladder, the daemon's response queue and severity floors, and the
band text the agents are prompted with — reads a field here, so raising a
threshold in env moves every branch rather than one. Defaults are the literals
the code carried before, so a default install behaves as it did.

Lives in ``core/`` because ``core`` must not import ``services``;
``services.daemon.config`` re-exports it as part of ``DaemonConfig``.
"""

import ipaddress
from dataclasses import dataclass, field
from decimal import Decimal
from ipaddress import IPv4Network, IPv6Network
from typing import Any, List, Optional, Union

from core.config import Settings, get_settings
from core.storage.origin_trust import tier_rank

# The blast-radius subnet an address target is measured in, as a network.
ContainmentSubnet = Union[IPv4Network, IPv6Network]


def min_origin_trust_rank(tier: str) -> int:
    """The origin floor's rank for a tier name; an unknown name fails loudly.

    A typo'd ``DAEMON_MIN_ORIGIN_TRUST_FOR_AUTO_CONTAINMENT`` must not
    silently widen the floor: the daemon refuses to start on it.
    """
    rank = tier_rank(tier)
    if rank is None:
        raise ValueError(
            f"DAEMON_MIN_ORIGIN_TRUST_FOR_AUTO_CONTAINMENT={tier!r} names no "
            "tier (unverified < transport < signed)"
        )
    return rank


def decision_rule(field: str, value: Any, observed: Optional[float] = None) -> str:
    """Render the rule a decision fired on, keyed on the config field (#917).

    Numeric thresholds render as ``response.confidence_threshold=0.90 met (0.92)``
    — the field, the value it held when the decision was made, whether the
    observed confidence reached it, and that confidence. Branches with no
    comparison (``reversibility=irreversible``, ``approval.force_manual_approval=True``)
    render as ``field=value``. Every decision site calls this; none assembles
    the string itself, so a later slice can parse one shape.
    """
    if observed is None:
        return f"{field}={value}"
    verdict = "met" if observed >= value else "not met"
    return f"{field}={value:.2f} {verdict} ({observed:.2f})"


@dataclass
class ResponseConfig:
    auto_response_enabled: bool = True
    # Reversible actions at or above this auto-approve; below it they wait for
    # an analyst. The one knob DAEMON_CONFIDENCE_THRESHOLD has always named.
    confidence_threshold: float = 0.90
    # The "quick review" line: the correlator recommends isolation with
    # approval, and the processor queues a finding for response, at or above it.
    review_threshold: float = 0.85
    # Below this the recommendation is to keep monitoring rather than act.
    monitor_threshold: float = 0.70
    # Severity-conditioned floors the daemon responder applies even below
    # confidence_threshold: a critical finding is isolated, and a high one
    # investigated, at or above these.
    critical_action_floor: float = 0.70
    high_action_floor: float = 0.80
    force_manual_approval: bool = False
    # Never-quarantine invariants: the DAEMON_NEVER_QUARANTINE entries
    # (kind:value), parsed at each decision by core.response.protected_targets.
    # Operator rows in the protected_targets table can tighten this and never
    # loosen it.
    never_quarantine: List[str] = field(default_factory=list)
    # Blast-radius quotas: rolling-window caps on unattended containment
    # volume, decided by blast_bound_decision on counts the caller reads.
    # At most max_containment_per_tick containment attempts in an executor
    # tick (CONTAINMENT_TICK_SECONDS); a target's subnet is
    # containment_subnet_prefix wide for IPv4 and /64 for IPv6; one rolling
    # hour of containment in that subnet takes at most the share of its
    # addresses, floored by max_containment_per_subnet_hour so a tiny subnet
    # is bounded too. Overflow waits for a person; it is never dropped.
    max_containment_per_tick: int = 3
    containment_subnet_prefix: int = 24
    max_containment_share_per_hour: float = 0.10
    max_containment_per_subnet_hour: int = 10
    # Operator allow-list for the invoke boundary: MCP tool names an agent run
    # may call directly despite the destructive-verb gate (core.llm.tool_risk).
    # A shorter list is tighter; chat is never loosened by it.
    tool_risk_overrides: List[str] = field(default_factory=list)
    # Anti-spoofing circuit breaker: suspend auto-approval of containment
    # while the shape of the demand looks like a storm — rolling-hour
    # volume, distinct-target churn (the rotating-spoofed-IP signature a
    # per-target idempotency key misses), or the failure rate of the last
    # five containment executions. Lower is tighter on all three. The state
    # is persisted (response.breaker_state) and fail-closed; the decision
    # is core.response.breaker.
    breaker_volume_threshold: int = 10
    breaker_distinct_targets: int = 8
    breaker_failure_rate: float = 0.50
    # Minutes after a trip before the breaker resumes on its own. 0 (the
    # default) is manual reset only: resuming machine-speed containment
    # after an anomaly is a promoting decision, and promoting is yours.
    breaker_auto_resume_minutes: int = 0
    # The origin floor: the minimum tier rank (0=unverified, 1=transport,
    # 2=signed) a motivating finding must carry before unattended containment
    # acts on it, and the distinct-source corroboration that releases a
    # below-floor finding. Ranks, not tier strings, so the intent diff has a
    # number to compare; 1 names transport.
    min_origin_trust: int = 1
    min_corroboration_for_unverified: int = 2
    dry_run: bool = False  # Log actions without executing

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "ResponseConfig":
        s = settings or get_settings()
        return cls(
            auto_response_enabled=s.daemon_auto_response,
            confidence_threshold=s.daemon_confidence_threshold,
            review_threshold=s.daemon_review_threshold,
            monitor_threshold=s.daemon_monitor_threshold,
            critical_action_floor=s.daemon_critical_action_floor,
            high_action_floor=s.daemon_high_action_floor,
            force_manual_approval=s.daemon_force_approval,
            never_quarantine=list(s.daemon_never_quarantine),
            max_containment_per_tick=s.daemon_max_containment_per_tick,
            containment_subnet_prefix=s.daemon_containment_subnet_prefix,
            max_containment_share_per_hour=s.daemon_max_containment_share_per_hour,
            max_containment_per_subnet_hour=s.daemon_max_containment_per_subnet_hour,
            tool_risk_overrides=list(s.daemon_tool_risk_overrides),
            breaker_volume_threshold=s.daemon_breaker_volume_threshold,
            breaker_distinct_targets=s.daemon_breaker_distinct_targets,
            breaker_failure_rate=s.daemon_breaker_failure_rate,
            breaker_auto_resume_minutes=s.daemon_breaker_auto_resume_minutes,
            min_origin_trust=min_origin_trust_rank(
                s.daemon_min_origin_trust_for_auto_containment
            ),
            min_corroboration_for_unverified=s.daemon_min_corroboration_for_unverified,
            dry_run=s.daemon_dry_run,
        )


def response_action_decision(
    severity: str,
    confidence: float,
    recommended: str,
    config: ResponseConfig,
) -> Optional[tuple[str, str]]:
    """The finding-side response, or None when nothing would be acted on.

    Returns ``(action, rule)``. Auto-response off is a decision, not a
    precondition: a manifest that disables it reports every finding that
    would have acted as losing its action.
    """
    if not config.auto_response_enabled or not 0.0 <= confidence <= 1.0:
        return None
    if confidence >= config.confidence_threshold and recommended in (
        "isolate",
        "block",
    ):
        return recommended, decision_rule(
            "response.confidence_threshold", config.confidence_threshold, confidence
        )
    if severity == "critical" and confidence >= config.critical_action_floor:
        return "isolate", decision_rule(
            "response.critical_action_floor", config.critical_action_floor, confidence
        )
    if severity == "high" and confidence >= config.high_action_floor:
        return "investigate", decision_rule(
            "response.high_action_floor", config.high_action_floor, confidence
        )
    return None


def approval_requirement(
    force_manual_approval: bool,
    reversibility: Any,
    confidence: float,
    config: ResponseConfig,
) -> tuple[bool, str]:
    """Whether an approval row waits for a human, and the rule that decided it.

    ``reversibility`` is the enum the live path passes. Compared by ``.value``
    so this module does not import the service that calls it. An unknown
    value raises, unless force-manual already decided.
    """
    if force_manual_approval:
        return True, decision_rule("approval.force_manual_approval", True)
    value = getattr(reversibility, "value", None)
    if value == "irreversible":
        return True, decision_rule("reversibility", value)
    if value == "reversible":
        # A confidence is a probability. Anything else (5.0, NaN) is a caller
        # inflating the number, and must not read as "above the threshold".
        if not 0.0 <= confidence <= 1.0:
            return True, decision_rule("response.confidence_range", confidence)
        return confidence < config.confidence_threshold, decision_rule(
            "response.confidence_threshold", config.confidence_threshold, confidence
        )
    raise ValueError(f"Unknown reversibility: {reversibility}")


# ---------------------------------------------------------------------------
# Blast-radius quotas: rolling-window volume caps on unattended containment.
# Pure functions on counts the caller reads; the SQL lives with the callers.
# ---------------------------------------------------------------------------

# The executor tick the approved-actions loop runs on (services.daemon.
# responder re-polls every 30 seconds). The gate's rolling tick window
# mirrors that cadence; a constant, not a knob — it follows the executor
# rather than dialing it.
CONTAINMENT_TICK_SECONDS = 30

# IPv6 has no /24; the standard LAN analog is the subnet its blast radius
# is measured in.
IPV6_CONTAINMENT_PREFIX = 64


@dataclass(frozen=True)
class ContainmentCounts:
    """Rolling-window containment volume a quota decision reads.

    ``tick`` — containment rows in the executor-tick window ending now.
    ``subnet_hour`` — containment rows in the target's subnet over the
    rolling hour. ``subnet_size`` — the addresses the target's containment
    subnet spans; 0 when the target is not an address (a hostname), so the
    share cap cannot apply and the absolute cap governs alone.
    """

    tick: int
    subnet_hour: int
    subnet_size: int


def containment_subnet(
    target: str, cfg: "ResponseConfig"
) -> Optional[ContainmentSubnet]:
    """The subnet a containment target's blast radius is measured in.

    IPv4 subnets are ``cfg.containment_subnet_prefix`` wide and IPv6 uses
    the /64 analog; IPv4-mapped IPv6 normalises to its IPv4 address like
    the responder's target extraction and the protected-target matcher.
    ``None`` for a target that is not an address (a hostname): it counts in
    the tick window and in no subnet. A prefix wider than the address space
    raises — a failed read holds containment for a person rather than
    guessing.
    """
    try:
        addr = ipaddress.ip_address(str(target).strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    prefix = (
        cfg.containment_subnet_prefix
        if isinstance(addr, ipaddress.IPv4Address)
        else IPV6_CONTAINMENT_PREFIX
    )
    return ipaddress.ip_network(f"{addr}/{prefix}", strict=False)


def blast_bound_decision(
    counts: ContainmentCounts, cfg: ResponseConfig
) -> Optional[str]:
    """None = allow; a rule string (#917) = hold the row for a person.

    Two rolling-window caps, in the order they bite: the executor tick's
    containment volume, then the target subnet's rolling hour — the share
    of the subnet's addresses, floored at one address' worth and at the
    absolute ``max_containment_per_subnet_hour``. A subnet of unknown size
    (a hostname target) is bounded by the absolute cap alone.
    """
    effective = cfg.max_containment_per_subnet_hour
    if counts.subnet_size:
        # The share is an operator's decimal percentage: 0.29 of 100 is 29
        # and must not drift to 28 on the way through a float multiply.
        share_cap = int(
            Decimal(str(cfg.max_containment_share_per_hour)) * counts.subnet_size
        )
        effective = min(effective, max(share_cap, 1))
    if counts.tick >= cfg.max_containment_per_tick:
        return (
            f"response.max_containment_per_tick={cfg.max_containment_per_tick}"
            f" met ({counts.tick})"
        )
    if counts.subnet_hour >= effective:
        return (
            f"response.max_containment_per_subnet_hour={effective}"
            f" met ({counts.subnet_hour})"
        )
    return None
