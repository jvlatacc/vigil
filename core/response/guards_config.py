"""The blast-bound knobs for autonomous response, bridged once (#944).

Feature 7's guard chain — never-quarantine invariants, containment quotas,
the circuit breaker, origin trust — reads these fields instead of reaching
into ``Settings`` at each site, the way the confidence band reads
``ResponseConfig``. Nothing consumes this yet; the guard slices wire it in.

An operator's numbers are validated here, at the use site, the way
``approval_requirement`` validates the confidence range: a value that cannot
be honored raises rather than quietly reading as valid, because guessed
blast bounds are not blast bounds. There is no action yet to hold, so the
safe branch is refusing the configuration; a caller that must keep running
catches :class:`GuardConfigError` and suspends auto-response instead. Seed
entry schemas (match kinds, key material) are the protected-assets and
origin modules' contracts, enforced where those build their indexes.

Lives in ``core/`` because ``core`` must not import ``services``; the
daemon slices consume it through their config bridge.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from core.config import Settings, get_settings
from core.response.config import decision_rule


class GuardConfigError(ValueError):
    """A blast-bound knob cannot be honored as configured (#944).

    A ``ValueError`` so callers that treat one as "configuration error,
    suspend machine-speed response" need no second except clause.
    """


def _invalid(field: str, value: Any, expected: str) -> GuardConfigError:
    # Rendered like every other decision rule ("field=value"), so a boot log
    # reads the same shape the action rationales will.
    return GuardConfigError(f"{decision_rule(field, value)}: expected {expected}")


def _at_least(field: str, value: Any, floor: int, expected: str) -> int:
    # A bool is an int in Python; a scope of True is not a count.
    if isinstance(value, bool) or not isinstance(value, int) or value < floor:
        raise _invalid(field, value, expected)
    return value


def _json_entries(field: str, raw: Any) -> tuple[dict, ...]:
    """One seed list as a read-only tuple, refusing what would read as empty."""
    if raw is None:
        return ()
    value: Any = raw
    if isinstance(value, str):
        if not value.strip():
            return ()
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GuardConfigError(f"{field}: not valid JSON ({exc})") from exc
    if not isinstance(value, list):
        raise _invalid(field, value, "a JSON array of objects")
    if not all(isinstance(item, dict) for item in value):
        raise GuardConfigError(f"{field}: every entry must be a JSON object")
    return tuple(value)


@dataclass
class GuardConfig:
    # Quotas on: 5% of a /24 per minute, 30/min and 200/hour global.
    quotas_enabled: bool = True
    # Quota scope derives from the target IP at this prefix length.
    subnet_scope_prefix: int = 24
    quota_subnet_pct_per_min: float = 5.0
    quota_global_per_min: int = 30
    # The hourly ceiling is the breaker trip, not just a pend.
    quota_global_per_hour: int = 200
    # The breaker opens for this long, then auto-closes.
    breaker_cooldown_seconds: int = 900
    breaker_invariant_probe_trip: int = 3
    breaker_origin_flood_trip: int = 10
    # Boot seeds. protected_assets feeds the never-quarantine index;
    # trusted_origins lists the Ed25519 roots findings attest with.
    protected_assets: tuple[dict, ...] = ()
    trusted_origins: tuple[dict, ...] = ()

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "GuardConfig":
        s = settings or get_settings()

        prefix = s.daemon_subnet_scope_prefix
        if (
            isinstance(prefix, bool)
            or not isinstance(prefix, int)
            or not 0 <= prefix <= 32
        ):
            raise _invalid(
                "daemon_subnet_scope_prefix",
                prefix,
                "an IPv4 prefix length in 0..32",
            )

        pct = s.daemon_containment_quota_subnet_pct_per_min
        # NaN fails the comparison on purpose: a caller inflating the number
        # must not read as a percentage. Zero is not a quota but a shutdown —
        # the off switch is daemon_containment_quotas_enabled.
        if (
            isinstance(pct, bool)
            or not isinstance(pct, (int, float))
            or not 0.0 < float(pct) <= 100.0
        ):
            raise _invalid(
                "daemon_containment_quota_subnet_pct_per_min",
                pct,
                "a percentage in (0, 100] — turn quotas off with"
                " DAEMON_CONTAINMENT_QUOTAS_ENABLED instead",
            )

        return cls(
            quotas_enabled=s.daemon_containment_quotas_enabled,
            subnet_scope_prefix=prefix,
            quota_subnet_pct_per_min=float(pct),
            quota_global_per_min=_at_least(
                "daemon_containment_quota_global_per_min",
                s.daemon_containment_quota_global_per_min,
                1,
                "at least 1 action per minute",
            ),
            quota_global_per_hour=_at_least(
                "daemon_containment_quota_global_per_hour",
                s.daemon_containment_quota_global_per_hour,
                1,
                "at least 1 action per hour",
            ),
            breaker_cooldown_seconds=_at_least(
                "daemon_breaker_cooldown_seconds",
                s.daemon_breaker_cooldown_seconds,
                1,
                "at least 1 second — 0 would flap open and shut",
            ),
            breaker_invariant_probe_trip=_at_least(
                "daemon_breaker_invariant_probe_trip",
                s.daemon_breaker_invariant_probe_trip,
                1,
                "at least 1 protected-asset probe",
            ),
            breaker_origin_flood_trip=_at_least(
                "daemon_breaker_origin_flood_trip",
                s.daemon_breaker_origin_flood_trip,
                1,
                "at least 1 unverified-origin block",
            ),
            protected_assets=_json_entries(
                "daemon_protected_assets", s.daemon_protected_assets
            ),
            trusted_origins=_json_entries(
                "daemon_trusted_origins", s.daemon_trusted_origins
            ),
        )
