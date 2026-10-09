"""FastPathConfig — the blast-radius knobs of the speculative-containment Fast-Path.

Mirrors the ResponseConfig pattern (core.response.config): the defaults are
the spec's literals, ``from_settings()`` reads the pydantic Settings, and
``services.daemon.config`` re-exports the class onto ``DaemonConfig`` the
same way it re-exports ResponseConfig. Every field has a
``DAEMON_FASTPATH_*`` variable documented in ``env.example``.

The Fast-Path ships apply-disabled and in shadow mode. Turning it on is an
operator decision backed by shadow-replay data — never a deploy default:
the false-positive cost it waits on is only measurable from shadow rows.

The bands mirror ResponseConfig's but are separate knobs: the millisecond
path may need a higher bar than the deliberation loop it precedes, and
raising one must not silently raise the other.

Lives in ``core/`` because ``core`` must not import ``services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.config import Settings, get_settings


@dataclass
class FastPathConfig:
    """One place for every Fast-Path knob, the way ResponseConfig holds the
    confidence band. All defaults are the spec's literals."""

    # Global kill switch, checked before anything else can say yes. False is
    # the release default: no lease, no executor consideration, no matter
    # what a finding carries.
    enabled: bool = False
    # Shadow mode scores and records every verdict but applies nothing
    # downstream. The rollout default: the per-detector false-positive bar
    # the apply switch waits on is only measurable from these rows.
    shadow_mode: bool = True
    # Lease TTL. A fresh lease carries default_ttl_seconds, clamped into
    # [min_ttl_seconds, max_ttl_seconds] by the gate. The clamp makes the
    # three fields total: whatever an operator sets, a lease never outlives
    # max_ttl_seconds.
    default_ttl_seconds: int = 300
    min_ttl_seconds: int = 60
    max_ttl_seconds: int = 900
    # Blast-radius caps, enforced by the deterministic gate — never by the
    # judgment of whatever proposed the finding. Each blocks on its own.
    max_leases_per_entity: int = 1
    max_leases_per_window: int = 20
    window_seconds: int = 3600
    # Anti-flap floor: minimum seconds between a rollback and the next apply
    # against the same entity. Rapid apply/rollback churn is itself a signal
    # the gate refuses to manufacture.
    anti_flap_rollback_floor_seconds: int = 600
    # A pending lease intent older than this is stuck; the TTL sweeper's
    # reconciler (a later slice) retries the idempotent apply or aborts the
    # intent to failed.
    apply_timeout_seconds: int = 60
    # The confidence band, mirroring ResponseConfig (same defaults, separate
    # knobs — see the module docstring). The severity floors decide lease
    # eligibility per severity; the rest travel with the config so a verdict
    # can render the band it fired on.
    confidence_threshold: float = 0.90
    review_threshold: float = 0.85
    monitor_threshold: float = 0.70
    critical_action_floor: float = 0.70
    high_action_floor: float = 0.80
    # The severity band eligible for a lease. Only severities with a floor
    # (critical, high) can act regardless of what lands here; widening this
    # without a floor mapped is inert by construction.
    allowed_severities: frozenset = frozenset({"critical", "high"})
    # The v1 micro-containment vocabulary: the two Cloudflare built-ins plus
    # the four verbs of the signed edge-endpoint contract (tarpit, synthetic
    # latency, session pinning ride the edge service, never Vigil itself).
    allowed_action_types: frozenset = frozenset(
        {"challenge", "rate_limit", "tarpit", "latency_injection", "pin_session"}
    )
    # The critical-asset allowlist: principals the gate never leases against,
    # whatever the detection says — even a critical severity. Matched
    # case-insensitively: hosts and domains arrive case-ambiguous in
    # findings, and a fold can only over-protect, never under-protect.
    deny_targets: frozenset = frozenset()

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "FastPathConfig":
        s = settings or get_settings()
        return cls(
            enabled=s.daemon_fastpath_enabled,
            shadow_mode=s.daemon_fastpath_shadow_mode,
            default_ttl_seconds=s.daemon_fastpath_default_ttl_seconds,
            min_ttl_seconds=s.daemon_fastpath_min_ttl_seconds,
            max_ttl_seconds=s.daemon_fastpath_max_ttl_seconds,
            max_leases_per_entity=s.daemon_fastpath_max_leases_per_entity,
            max_leases_per_window=s.daemon_fastpath_max_leases_per_window,
            window_seconds=s.daemon_fastpath_window_seconds,
            anti_flap_rollback_floor_seconds=(
                s.daemon_fastpath_anti_flap_rollback_floor_seconds
            ),
            apply_timeout_seconds=s.daemon_fastpath_apply_timeout_seconds,
            confidence_threshold=s.daemon_fastpath_confidence_threshold,
            review_threshold=s.daemon_fastpath_review_threshold,
            monitor_threshold=s.daemon_fastpath_monitor_threshold,
            critical_action_floor=s.daemon_fastpath_critical_action_floor,
            high_action_floor=s.daemon_fastpath_high_action_floor,
            allowed_severities=frozenset(s.daemon_fastpath_allowed_severities),
            allowed_action_types=frozenset(s.daemon_fastpath_allowed_action_types),
            deny_targets=frozenset(s.daemon_fastpath_deny_targets),
        )
