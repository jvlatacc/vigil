"""The containment circuit breaker: a two-state governor on unattended response.

Where the never-quarantine invariants bound which target may be contained and
the blast-radius quotas bound how much, the breaker watches the shape of the
demand: containment volume, distinct-target churn and executor failure rate
that look like a storm rather than an incident. The canonical shape is a
rotating-spoofed-IP alert flood — one fresh auto-approved row per spoofed
finding, each passing on its own, because the per-target idempotency key
cannot see them as one. Tripped, auto-approval of containment suspends: every
containment row waits for a person at the gate and the executor skips the
rows already approved underneath it, until an operator resets. Investigating,
monitoring and every human workflow are untouched — the breaker only stops
what would run unattended.

State lives in ``system_config`` under ``response.breaker_state``, read at
each decision so a trip binds every process at once and a reset frees them
without a restart. This module is the pure decision; the read/write seams
live with the other DB seams in ``core.response.approval_service``.

Lives in ``core/`` because ``core`` must not import ``services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from core.response.config import ResponseConfig, decision_rule

BREAKER_CONFIG_KEY = "response.breaker_state"

STATE_OPEN = "open"
STATE_TRIPPED = "tripped"

# Who reset the breaker when no person did — the auto-resume write's audit
# identity in the stored row and in the transition log.
AUTO_RESUME = "auto-resume"

# The executor-failure sample a trip decision reads: the last N containment
# execution attempts, failed or not. A constant, not a knob, like
# CONTAINMENT_TICK_SECONDS — it follows the machinery rather than dialing it.
# The rate trips only on a full sample: the first failures of a brand-new
# integration are a misconfiguration to surface, not a storm to declare.
BREAKER_FAILURE_SAMPLE = 5


@dataclass(frozen=True)
class BreakerCounts:
    """The storm signature one trip decision reads.

    ``volume_hour`` — containment rows in the rolling hour, including the
    decision being made. ``distinct_targets_hour`` — distinct targets those
    rows name, including this decision's target: the rotating-spoofed-IP
    shape a per-target idempotency key misses. ``failures`` and ``attempts``
    — failed executions over the last ``BREAKER_FAILURE_SAMPLE`` containment
    execution attempts; the rate is judged only on a full sample.
    """

    volume_hour: int
    distinct_targets_hour: int
    failures: int = 0
    attempts: int = 0

    @property
    def failure_rate(self) -> float:
        return self.failures / self.attempts if self.attempts else 0.0


def breaker_decision(counts: BreakerCounts, cfg: ResponseConfig) -> Optional[str]:
    """None = the shape is within bounds; a rule string (#917) = trip.

    The row that completes a signature is the first one held: the counts
    include the decision being made, so the row that reaches a threshold is
    stopped by it rather than let through to watch the next one trip.
    """
    if counts.volume_hour >= cfg.breaker_volume_threshold:
        return (
            f"response.breaker_volume_threshold={cfg.breaker_volume_threshold}"
            f" met ({counts.volume_hour})"
        )
    if counts.distinct_targets_hour >= cfg.breaker_distinct_targets:
        return (
            f"response.breaker_distinct_targets={cfg.breaker_distinct_targets}"
            f" met ({counts.distinct_targets_hour})"
        )
    if counts.attempts >= BREAKER_FAILURE_SAMPLE:
        rate = counts.failure_rate
        if rate >= cfg.breaker_failure_rate:
            return decision_rule(
                "response.breaker_failure_rate", cfg.breaker_failure_rate, rate
            )
    return None


@dataclass(frozen=True)
class BreakerState:
    """The persisted breaker, as the row is stored and the settings read it.

    ``reason`` is the rule the trip fired on; on an open row it is the last
    trip's reason, so the settings card can show what happened before the
    reset. ``auto_resume_at`` is stamped at trip time when the operator set
    a cooldown; ``reset_at``/``reset_by`` mark the open row's write.
    """

    state: str = STATE_OPEN
    tripped_at: Optional[str] = None
    reason: str = ""
    counts: Optional[Dict[str, Any]] = None
    auto_resume_at: Optional[str] = None
    reset_at: Optional[str] = None
    reset_by: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"state": self.state}
        for field in (
            "tripped_at",
            "reason",
            "counts",
            "auto_resume_at",
            "reset_at",
            "reset_by",
        ):
            value = getattr(self, field)
            if value is not None and value != "":
                payload[field] = value
        return payload


def parse_state(raw: Any) -> BreakerState:
    """The stored row as a BreakerState; raises on a row the breaker cannot read.

    No row at all is armed: the breaker has nothing on record. A row without
    a ``state`` field was not written by the breaker (a foreign writer or an
    empty payload) and reads the same way. A state value the breaker does
    not know raises — a corrupted trip record must not read as an armed
    breaker, so the caller can fail closed on it.
    """
    if raw is None:
        return BreakerState()
    if not isinstance(raw, dict):
        raise ValueError(f"breaker state is {type(raw).__name__}, not an object")
    state = raw.get("state", STATE_OPEN)
    if state not in (STATE_OPEN, STATE_TRIPPED):
        raise ValueError(f"unknown breaker state: {state!r}")
    counts = raw.get("counts")
    return BreakerState(
        state=state,
        tripped_at=raw.get("tripped_at"),
        reason=str(raw.get("reason") or ""),
        counts=counts if isinstance(counts, dict) else None,
        auto_resume_at=raw.get("auto_resume_at"),
        reset_at=raw.get("reset_at"),
        reset_by=raw.get("reset_by"),
    )


def _parse_stamp(text: str) -> datetime:
    """A stored ISO stamp as a naive UTC datetime, like ``core.time.utcnow``."""
    return datetime.fromisoformat(str(text))


def resume_due(state: BreakerState, cfg: ResponseConfig, now: datetime) -> bool:
    """Whether an auto-resume cooldown has elapsed on a tripped breaker.

    The cooldown is stamped on the trip when the knob is set; a trip written
    before the operator set it resumes from the trip time anyway, so
    enabling auto-resume never leaves a trip immortal that the current
    config says should end. Raises on an unreadable stamp — the caller
    fails closed on it.
    """
    if state.state != STATE_TRIPPED or cfg.breaker_auto_resume_minutes <= 0:
        return False
    resume_at = state.auto_resume_at
    if resume_at is None and state.tripped_at is not None:
        resume_at = _parse_stamp(state.tripped_at) + timedelta(
            minutes=cfg.breaker_auto_resume_minutes
        )
    if resume_at is None:
        return False
    if isinstance(resume_at, str):
        resume_at = _parse_stamp(resume_at)
    return now >= resume_at


def opened_state(previous: BreakerState, reset_by: str, now: datetime) -> BreakerState:
    """The armed row a reset (or an auto-resume) writes.

    The trip's signature is kept as the last reason so the settings card can
    show what the breaker was tripped by when it opened.
    """
    return BreakerState(
        state=STATE_OPEN,
        reason=previous.reason,
        counts=previous.counts,
        reset_at=now.isoformat(),
        reset_by=reset_by,
    )


def tripped_state(
    counts: BreakerCounts, rule: str, cfg: ResponseConfig, now: datetime
) -> BreakerState:
    """The tripped row a trip writes, stamped with the auto-resume cooldown
    when the operator configured one."""
    cooldown = cfg.breaker_auto_resume_minutes
    return BreakerState(
        state=STATE_TRIPPED,
        tripped_at=now.isoformat(),
        reason=rule,
        counts={
            "volume_hour": counts.volume_hour,
            "distinct_targets_hour": counts.distinct_targets_hour,
            "failure_rate": round(counts.failure_rate, 4),
        },
        auto_resume_at=(
            (now + timedelta(minutes=cooldown)).isoformat() if cooldown > 0 else None
        ),
    )
