"""Deception settings, in one place.

Every comparison against a honey-routing knob reads a field here, the same
way :mod:`core.response.config` holds the confidence band: ``core`` must not
import ``services``, and ``services.daemon.config`` re-exports what the
daemon needs. Defaults are inert — the posture is off, the backend is
dry-run — so a default install behaves exactly as before feature 5.
"""

import ipaddress
import logging
from dataclasses import dataclass
from typing import Optional

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# The system_config row the console kill-switch toggle writes; read per
# decision so a long-lived daemon sees the change without a restart (the
# ``approval.force_manual_approval`` precedent). The env override never
# depends on the DB: either source alone trips the switch.
KILL_SWITCH_CONFIG_KEY = "deception.kill_switch"


def parse_allowlist_entries(entries: str) -> tuple:
    """Parse a comma-separated list of IPs/CIDRs into networks.

    An entry the :mod:`ipaddress` module cannot parse is skipped loudly in
    the log rather than silently ignored — a typo in an allowlist must be
    visible, but must not keep the rest of the list from working.
    """
    networks = []
    for raw in (entries or "").split(","):
        value = raw.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.warning("Ignoring unparseable deception allowlist entry: %s", value)
    return tuple(networks)


@dataclass
class DeceptionConfig:
    """The honey-routing band and its safety rails, read from Settings."""

    enabled: bool = False
    backend: str = "dry_run"
    # Auto-approve floor for honey_route rows: transparent + reversible
    # justifies acting below the 0.90 deny bar. The system demotes its
    # autonomy; only humans promote it.
    honey_route_floor: float = 0.80
    # One redirect lease. The lease, not the approval row, is what expires.
    ttl_seconds: int = 3600
    # Hard ceiling on a lease's total lifetime (renewals included): a lease
    # may be extended, never made open-ended.
    max_duration_seconds: int = 86400
    # Distinct corroborating probes a source needs inside the window before
    # the posture may fire — one recon finding is not evidence of intent.
    min_observations: int = 3
    window_seconds: int = 3600
    kill_switch: bool = False
    # Comma-separated IPs/CIDRs exempt from steering: sanctioned scanners,
    # shared-NAT ranges pending stronger evidence.
    allowlist: str = ""

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DeceptionConfig":
        s = settings or get_settings()
        return cls(
            enabled=s.daemon_deception_enabled,
            backend=s.daemon_deception_backend,
            honey_route_floor=s.daemon_honey_route_floor,
            ttl_seconds=s.daemon_honey_route_ttl,
            max_duration_seconds=s.daemon_honey_route_max_duration,
            min_observations=s.daemon_honey_route_min_observations,
            window_seconds=s.daemon_honey_route_window,
            kill_switch=s.daemon_deception_kill_switch,
            allowlist=s.daemon_deception_allowlist,
        )

    def allowlist_networks(self) -> tuple:
        """The configured exemptions as parsed networks."""
        return parse_allowlist_entries(self.allowlist)
