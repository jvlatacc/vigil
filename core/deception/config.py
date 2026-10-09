"""Deception settings, in one place.

Every comparison against a honey-routing knob reads a field here, the same
way :mod:`core.response.config` holds the confidence band: ``core`` must not
import ``services``, and ``services.daemon.config`` re-exports what the
daemon needs. Defaults are inert — the posture is off, the backend is
dry-run — so a default install behaves exactly as before feature 5.
"""

import ipaddress
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# The system_config row the console kill-switch toggle writes; read per
# decision so a long-lived daemon sees the change without a restart (the
# ``approval.force_manual_approval`` precedent). The env override never
# depends on the DB: either source alone trips the switch.
KILL_SWITCH_CONFIG_KEY = "deception.kill_switch"

# The system_config row the Settings › Deception section writes, so flipping
# a knob does not wait for a restart — the ``ai_operations.settings``
# pattern (core/platform/runtime_config.py): the stored row wins per key,
# the env var is the fallback, the dataclass default is the last resort.
# Reads go through a short in-process cache because the per-finding decision
# path builds configs here. A failed read answers env values: the shipped
# defaults are inert, so env is the fail-safe answer.
SETTINGS_CONFIG_KEY = "deception.settings"
OVERRIDE_CACHE_TTL_SECONDS = 60

# The steering backends build_backend accepts; anything else in a stored row
# is stale and falls back to env rather than failing at the next steer.
VALID_BACKENDS = ("dry_run", "controller")

_override_lock = threading.Lock()
_override_cache: Dict[str, Any] = {}
_override_cache_expires_at = 0.0


def _stored_overrides() -> Dict[str, Any]:
    """The stored ``deception.settings`` row, cached for one TTL."""
    global _override_cache, _override_cache_expires_at
    with _override_lock:
        if time.monotonic() < _override_cache_expires_at:
            return _override_cache
    try:
        from core.storage.config_service import get_config_service

        value = get_config_service().read_system_config(SETTINGS_CONFIG_KEY)
    except Exception as e:  # noqa: BLE001 — a failed read falls back to env
        logger.error("Cannot read the deception settings row; using env values: %s", e)
        value = None
    stored = value if isinstance(value, dict) else {}
    with _override_lock:
        _override_cache = stored
        _override_cache_expires_at = time.monotonic() + OVERRIDE_CACHE_TTL_SECONDS
    return stored


def clear_settings_cache() -> None:
    """Drop the cached overrides. Called after a Settings write and by tests."""
    global _override_cache, _override_cache_expires_at
    with _override_lock:
        _override_cache = {}
        _override_cache_expires_at = 0.0


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return fallback


def _coerce_float(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return fallback


def _coerce_str(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def allowlist_errors(entries: str) -> List[str]:
    """The allowlist entries :mod:`ipaddress` cannot parse.

    The Settings write refuses these (a typo must not store an exemption
    list that silently drops it); the predicate's own parse path
    (:func:`parse_allowlist_entries`) skips them loudly instead, so a
    hand-edited row degrades without blocking the posture.
    """
    errors: List[str] = []
    for raw in (entries or "").split(","):
        value = raw.strip()
        if not value:
            continue
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            errors.append(value)
    return errors


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
        stored = _stored_overrides()
        backend = stored.get("backend")
        return cls(
            enabled=_coerce_bool(stored.get("enabled"), s.daemon_deception_enabled),
            backend=(
                backend
                if backend in VALID_BACKENDS
                else _coerce_str(s.daemon_deception_backend, "dry_run")
            ),
            honey_route_floor=_coerce_float(
                stored.get("honey_route_floor"), s.daemon_honey_route_floor
            ),
            ttl_seconds=_coerce_int(stored.get("ttl_seconds"), s.daemon_honey_route_ttl),
            max_duration_seconds=_coerce_int(
                stored.get("max_duration_seconds"), s.daemon_honey_route_max_duration
            ),
            min_observations=_coerce_int(
                stored.get("min_observations"), s.daemon_honey_route_min_observations
            ),
            window_seconds=_coerce_int(
                stored.get("window_seconds"), s.daemon_honey_route_window
            ),
            kill_switch=s.daemon_deception_kill_switch,
            allowlist=_coerce_str(stored.get("allowlist"), s.daemon_deception_allowlist),
        )

    def allowlist_networks(self) -> tuple:
        """The configured exemptions as parsed networks."""
        return parse_allowlist_entries(self.allowlist)
