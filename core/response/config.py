"""The confidence band for autonomous response, in one place (#916).

Every comparison against a confidence — the approval gate, the correlator's
recommendation ladder, the daemon's response queue and severity floors, and the
band text the agents are prompted with — reads a field here, so raising a
threshold in env moves every branch rather than one. Defaults are the literals
the code carried before, so a default install behaves as it did.

Beside it, never on top of it, lives the MTD band (``MtdConfig`` and
``mtd_route_decision``): the honey-routing floor is its own numbers with its
own decision-rule keys, so widening one band can never widen the other.

Lives in ``core/`` because ``core`` must not import ``services``;
``services.daemon.config`` re-exports both as part of ``DaemonConfig``.
"""

import ipaddress
from dataclasses import dataclass
from typing import Any, Optional

from core.config import Settings, get_settings


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


# --- The MTD band ------------------------------------------------------------


@dataclass(frozen=True)
class MtdConfig:
    """The honey-routing band, deliberately beside the response band.

    The floors are independent on purpose: a recon probe is a candidate for
    deception well below the containment line, so this band's numbers must
    never move because a containment threshold moved — and raising the
    response band must never widen what may be decoyed. Default off:
    enabling MTD is a human configuration act, consistent with only humans
    promoting autonomy.
    """

    enabled: bool = False
    # Proposal floor for decoying a recon probe; its own band, independent
    # of the isolate/block thresholds above in this module.
    confidence_floor: float = 0.60
    # How long an approved routing may hold before the daemon releases it.
    session_ttl_seconds: int = 3600
    # Only probes aimed at internal destinations are candidates: a probe of
    # public space is not touching an internal host, so there is nothing a
    # decoy would be protecting.
    internal_destinations_only: bool = True

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "MtdConfig":
        s = settings or get_settings()
        return cls(
            enabled=s.daemon_mtd_enabled,
            confidence_floor=s.daemon_mtd_confidence_floor,
            session_ttl_seconds=s.daemon_mtd_session_ttl_seconds,
            internal_destinations_only=s.daemon_mtd_internal_only,
        )


# Destinations a probe may be diverted from, as far as MTD is concerned:
# RFC 1918 private space plus loopback and link-local, and their IPv6
# counterparts (unique-local, loopback, link-local). Spelled out rather than
# read from ``ipaddress``.is_private so the answer cannot drift with the
# stdlib's registry — documentation ranges (TEST-NET, ::/8) stay external.
_INTERNAL_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_internal(dest_ip: str) -> bool:
    """Whether dest_ip names a host on one of ours; unparseable is not."""
    try:
        addr = ipaddress.ip_address(dest_ip)
    except ValueError:
        return False
    return any(
        addr.version == net.version and addr in net for net in _INTERNAL_NETWORKS
    )


def mtd_route_decision(
    recommended: str,
    confidence: float,
    dest_ip: Optional[str],
    config: MtdConfig,
    is_excluded: bool,
) -> tuple[Optional[str], str]:
    """Whether a probe may be honey-routed, and the rule that decided.

    Returns ``(action, rule)`` on every path: ``"honey_route"`` only when
    every gate passes, and even a refusal names the rule it refused on —
    the same audit contract as :func:`response_action_decision`, except that
    a refusal still carries its rule, because "we chose not to deceive" is
    an audit line too. Gates in order: MTD on, destination internal per
    config, not on the never-route list, the ``deceive`` verb recommended,
    the confidence a probability, the confidence at or above this band's
    floor. A refusal routes nothing; the probe falls back to the normal
    response path.
    """
    if not config.enabled:
        return None, decision_rule("mtd.enabled", False)
    if dest_ip is None or (
        config.internal_destinations_only and not _is_internal(dest_ip)
    ):
        return None, decision_rule("mtd.dest_not_internal", dest_ip)
    if is_excluded:
        return None, decision_rule("mtd.exclusion_list", dest_ip)
    if recommended != "deceive":
        return None, decision_rule("mtd.no_deceive_verb", recommended)
    if not 0.0 <= confidence <= 1.0:
        return None, decision_rule("mtd.confidence_range", confidence)
    if confidence < config.confidence_floor:
        return None, decision_rule(
            "mtd.confidence_floor", config.confidence_floor, confidence
        )
    return "honey_route", decision_rule(
        "mtd.confidence_floor met", config.confidence_floor, confidence
    )
