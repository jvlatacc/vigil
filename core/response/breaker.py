"""The containment circuit breaker: auto-response suspends itself rather
than over-contains (#944, spec D4).

A shared two-state breaker — CLOSED / OPEN — between the Responder's
confidence and the containment actuator. While OPEN, every automated action
becomes a pending human approval and exactly one escalation event fires for
the whole period, not one per action. The failure mode is the safe one: an
adversary can trip the breaker and force human mode, but cannot force bad
containment.

Trips on three conditions (spec D4):

* a quota hard ceiling — the containment-quotas slice reports its hourly
  ceiling crossed, as a typed signal (:class:`QuotaTripSignal`);
* >= ``breaker_invariant_probe_trip`` protected-asset block attempts within
  10 minutes — someone is probing the never-quarantine set;
* >= ``breaker_origin_flood_trip`` origin-unverified blocks within 10
  minutes — a spoofing flood, which also protects the human queue.

State lives in Redis (``vigil:containment:{namespace}:state``, ``SET ...
EX cooldown`` — the TTL expiry IS the auto-close) with an in-memory fallback
modeled on ``RedisDedupSet``: namespaced keys, TTL-bounded, degradation
logged once per transition. Trip counters keep every event's birth timestamp
and decay over twice the cooldown: the cooldown consumes the first half of
that decay, so at auto-close the evidence that tripped the breaker is gone
and a closed breaker does not re-trip on it (no flapping) — while genuinely
fresh probing re-trips immediately.

A read of the shared state that fails mid-flight (Redis was reachable and
died) is answered as OPEN: an unanswerable "am I open?" must not read as
"closed, machine-speed ahead". Redis-unreachable-since-init is the ordinary
per-process fallback mode, with the same trade-off ``RedisDedupSet``
documents — multi-replica deployments need Redis for shared enforcement.

Lives in ``core/`` because ``core`` must not import ``services``; the guard
chain consumes this beside ``ResponseConfig`` and ``GuardConfig``.
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from core.config import DEFAULT_REDIS_URL, get_settings
from core.platform.log_redaction import redact_url
from core.response.config import decision_rule
from core.response.guards_config import GuardConfig

logger = logging.getLogger(__name__)

# The spec's trip windows: >=3 invariant-block attempts within 10 minutes,
# >=10 origin-unverified blocks within 10 minutes.
TRIP_WINDOW_SECONDS = 600.0

# Trip-counter identifiers; also the decision_rule field fragment
# ("response.breaker_{counter}_trip") and the counter zset suffix.
INVARIANT_PROBE = "invariant_probe"
ORIGIN_FLOOD = "origin_flood"

CLOSED = "closed"
OPEN = "open"


class QuotaTripSignal(Protocol):
    """The quotas module's hard-ceiling signal, consumed structurally (#944).

    The concrete type lands with the containment-quotas slice; declaring the
    shape here keeps this module importable before (and independent of) that
    sibling — no slice imports another.
    """

    detail: str


@dataclass(frozen=True)
class BreakerStatus:
    """One observation of the breaker, for the API surface and the audit log."""

    state: str
    reason: Optional[str] = None
    rule: Optional[str] = None
    opened_at: Optional[float] = None
    seconds_left: Optional[int] = None
    escalation_fired: bool = False
    store: str = "redis"  # "redis" | "memory"
    counters: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "rule": self.rule,
            "opened_at": self.opened_at,
            "seconds_left": self.seconds_left,
            "escalation_fired": self.escalation_fired,
            "store": self.store,
            "counters": dict(self.counters),
        }


class ContainmentBreaker:
    """Shared CLOSED/OPEN state with trip counters that decay (#944, D4).

    One instance per process; the state is shared through Redis, so the
    daemon's guard chain and this API surface agree without knowing each
    other. Constructed with the same :class:`GuardConfig` the guard chain
    bridges, so an operator's cooldown and trip thresholds move everywhere
    at once.
    """

    def __init__(
        self,
        config: Optional[GuardConfig] = None,
        *,
        redis_url: Optional[str] = None,
        namespace: str = "breaker",
        clock: Optional[Callable[[], float]] = None,
    ):
        self._config = config or GuardConfig()
        self._cooldown = float(self._config.breaker_cooldown_seconds)
        self._horizon = 2.0 * self._cooldown
        self._clock = clock or time.time

        self._state_key = f"vigil:containment:{namespace}:state"
        self._counter_keys = {
            INVARIANT_PROBE: f"vigil:containment:{namespace}:invariant_probe",
            ORIGIN_FLOOD: f"vigil:containment:{namespace}:origin_flood",
        }
        self._thresholds = {
            INVARIANT_PROBE: self._config.breaker_invariant_probe_trip,
            ORIGIN_FLOOD: self._config.breaker_origin_flood_trip,
        }

        self.redis_url = redis_url or get_settings().redis_url or DEFAULT_REDIS_URL
        self._redis = None
        self._in_fallback = False
        self._ever_connected = False

        # In-memory fallback mirrors of the Redis state. Per process: another
        # instance (daemon, API worker) does not see them.
        self._fallback_state: Optional[Dict[str, Any]] = None
        self._fallback_deadline: float = 0.0
        self._fallback_counters: Dict[str, List[float]] = {
            INVARIANT_PROBE: [],
            ORIGIN_FLOOD: [],
        }

    # -- Redis plumbing (the RedisDedupSet shape) ---------------------------

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._ever_connected = True
            logger.info(
                "ContainmentBreaker[%s] connected to %s",
                self._state_key,
                redact_url(self.redis_url),
            )
            if self._in_fallback:
                self._in_fallback = False
                logger.warning(
                    "ContainmentBreaker[%s] Redis recovered; state written to"
                    " the in-memory fallback during the outage is not in Redis",
                    self._state_key,
                )
        except Exception as e:
            self._warn_fallback(f"init failed: {e}")
            self._redis = None
        return self._redis

    def _warn_fallback(self, reason: str) -> None:
        """Log once per Redis -> fallback transition, not per failed call."""
        if not self._in_fallback:
            logger.error(
                "ContainmentBreaker[%s] Redis unavailable, using in-memory"
                " fallback (%s); breaker state will not be shared across"
                " processes or survive restarts",
                self._state_key,
                reason,
            )
            self._in_fallback = True

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None

    # -- Reading the state ---------------------------------------------------

    async def is_open(self) -> bool:
        """True while auto-response is suspended.

        A mid-flight read failure of the shared state counts as open: the
        safe branch of an unanswerable question is a person, not machine
        speed. A breaker in fallback mode answers from its own mirror.
        """
        state, _, degraded = await self._read_state(self._clock())
        return degraded or state is not None

    async def _read_state(
        self, now: float
    ) -> tuple[Optional[Dict[str, Any]], Optional[int], bool]:
        """(state, seconds_left, degraded); state None + not degraded = closed.

        ``degraded`` means the shared store was reachable before and just
        failed — the caller must fail safe rather than trust the local
        mirror, which may be empty or stale.
        """
        r = await self._get_redis()
        if r is not None:
            try:
                raw = await r.get(self._state_key)
                ttl_ms = await r.pttl(self._state_key)
                seconds_left = (
                    max(1, int(math.ceil(ttl_ms / 1000.0))) if ttl_ms > 0 else None
                )
                if raw is None:
                    return None, None, False
                state = json.loads(raw)
                if not isinstance(state, dict):  # corrupt: fail safe
                    return None, None, True
                return state, seconds_left, False
            except Exception as e:
                self._warn_fallback(f"state read error: {e}")
                self._redis = None
                if self._ever_connected:
                    return None, None, True
        return self._fallback_read(now), self._fallback_seconds_left(now), False

    # -- Recording trips -----------------------------------------------------

    async def trip_on_quota(self, signal: QuotaTripSignal) -> str:
        """Trip on the quotas module's hard-ceiling signal (#944, D3/D4).

        Returns the decision_rule-style rationale the guard chain renders.
        """
        rule = decision_rule("response.quota_hard_ceiling", signal.detail)
        await self._trip(reason=f"quota hard ceiling: {signal.detail}", rule=rule)
        return rule

    async def note_invariant_block(self) -> Optional[str]:
        """Record one protected-asset block; trip on the configured run.

        Returns the trip rule when this call tripped the breaker, else None.
        """
        return await self._note(INVARIANT_PROBE, "protected-asset probe run")

    async def note_origin_unverified(self) -> Optional[str]:
        """Record one origin-unverified block; trip on the configured flood."""
        return await self._note(ORIGIN_FLOOD, "origin-unverified flood")

    async def _note(self, counter: str, label: str) -> Optional[str]:
        now = self._clock()
        r = await self._get_redis()
        if r is not None:
            try:
                await r.zadd(self._counter_keys[counter], {uuid.uuid4().hex: now})
            except Exception as e:
                self._warn_fallback(f"zadd error: {e}")
                self._redis = None
                self._fallback_note(counter, now)
        else:
            self._fallback_note(counter, now)
        return await self._evaluate(counter, label, now)

    async def _evaluate(self, counter: str, label: str, now: float) -> Optional[str]:
        ages = await self._counter_ages(counter, now)
        threshold = self._thresholds[counter]
        recent = sum(1 for age in ages if age <= TRIP_WINDOW_SECONDS)
        if recent < threshold:
            return None
        rule = decision_rule(
            f"response.breaker_{counter}_trip", threshold, float(recent)
        )
        await self._trip(
            reason=f"{label}: {recent} within {int(TRIP_WINDOW_SECONDS)}s",
            rule=rule,
        )
        return rule

    async def _trip(self, reason: str, rule: str) -> None:
        """Open the breaker, or re-arm the cooldown of an already-open one.

        A re-trip while OPEN keeps the original opened_at and escalation
        claim (the period is one story) and re-arms the TTL: the breaker
        closes a full cooldown after the last trip signal.
        """
        now = self._clock()
        r = await self._get_redis()
        if r is not None:
            try:
                state = {
                    "state": OPEN,
                    "reason": reason,
                    "rule": rule,
                    "opened_at": now,
                    "escalated": False,
                }
                existing = await r.get(self._state_key)
                if existing:
                    prior = json.loads(existing)
                    state["opened_at"] = prior.get("opened_at", state["opened_at"])
                    state["escalated"] = bool(prior.get("escalated"))
                    state["reason"] = prior.get("reason", reason)
                    state["rule"] = prior.get("rule", rule)
                    logger.warning(
                        "containment breaker re-tripped while OPEN (%s);"
                        " cooldown re-armed, first cause kept: %s",
                        reason,
                        prior.get("reason"),
                    )
                await r.set(
                    self._state_key,
                    json.dumps(state),
                    ex=max(1, int(math.ceil(self._cooldown))),
                )
                logger.error(
                    "containment breaker OPEN: %s (%s) — every action now"
                    " waits for a person until %ds after the last trip signal",
                    reason,
                    rule,
                    int(self._cooldown),
                )
                return
            except Exception as e:
                self._warn_fallback(f"state write error: {e}")
                self._redis = None
        self._fallback_trip(reason, rule, now)

    async def claim_escalation(self) -> bool:
        """True exactly once per OPEN period — fire the escalation on True.

        The guard chain calls this when it converts an action to pending
        while OPEN; the first caller fires the Slack/PagerDuty event and the
        rest of the period's actions pend silently.
        """
        now = self._clock()
        r = await self._get_redis()
        if r is not None:
            try:
                raw = await r.get(self._state_key)
                if raw is None:
                    return False
                state = json.loads(raw)
                if state.get("escalated"):
                    return False
                state["escalated"] = True
                ttl_ms = await r.pttl(self._state_key)
                ttl = (
                    max(1, int(math.ceil(ttl_ms / 1000.0)))
                    if ttl_ms > 0
                    else max(1, int(math.ceil(self._cooldown)))
                )
                await r.set(self._state_key, json.dumps(state), ex=ttl)
                logger.warning(
                    "containment breaker escalation claimed once for the OPEN"
                    " period started at %s",
                    state.get("opened_at"),
                )
                return True
            except Exception as e:
                self._warn_fallback(f"escalation claim error: {e}")
                self._redis = None
                if self._ever_connected:
                    return False
        return self._fallback_claim(now)

    # -- Counters ------------------------------------------------------------

    async def _counter_ages(self, counter: str, now: float) -> List[float]:
        """Ages of the surviving events for one counter, oldest first.

        Events decay over the horizon (twice the cooldown). While the
        breaker is closed, events older than the cooldown are dropped
        eagerly: their 10-minute trip window is long past and stale trip
        evidence must not re-trip a closed breaker.
        """
        state, _, _ = await self._read_state(now)
        is_open_now = state is not None
        max_age = self._horizon if is_open_now else self._cooldown
        r = await self._get_redis()
        if r is not None:
            try:
                await r.zremrangebyscore(self._counter_keys[counter], 0, now - max_age)
                entries = await r.zrange(
                    self._counter_keys[counter], 0, -1, withscores=True
                )
                return [max(0.0, now - float(score)) for _, score in entries]
            except Exception as e:
                self._warn_fallback(f"counter read error: {e}")
                self._redis = None
                if self._ever_connected:
                    return []  # fail safe: no counter evidence while degraded
        events = self._fallback_counters[counter]
        events[:] = [ts for ts in events if now - ts <= max_age]
        return [max(0.0, now - ts) for ts in events]

    def _decayed_count(self, ages: List[float], now: float) -> float:
        """Linear decay over the horizon: full at birth, zero at 2×cooldown."""
        if self._horizon <= 0:
            return 0.0
        return sum(
            max(0.0, 1.0 - age / self._horizon) for age in ages if age <= self._horizon
        )

    # -- Status, reset -------------------------------------------------------

    async def status(self) -> BreakerStatus:
        """One observation of the breaker for operators and the audit log."""
        now = self._clock()
        state, seconds_left, degraded = await self._read_state(now)
        counters: Dict[str, Dict[str, float]] = {}
        for counter in self._counter_keys:
            ages = await self._counter_ages(counter, now)
            counters[counter] = {
                "recent": float(sum(1 for age in ages if age <= TRIP_WINDOW_SECONDS)),
                "decayed": round(self._decayed_count(ages, now), 3),
            }
        if degraded:
            return BreakerStatus(
                state=OPEN,
                reason="shared breaker state unreadable (Redis error);"
                " failing safe — every action waits for a person",
                rule=decision_rule("response.breaker_state_unreadable", "degraded"),
                seconds_left=None,
                escalation_fired=False,
                store="redis",
                counters=counters,
            )
        if state is None:
            return BreakerStatus(
                state=CLOSED,
                store=self._store_name(),
                counters=counters,
            )
        return BreakerStatus(
            state=OPEN,
            reason=state.get("reason"),
            rule=state.get("rule"),
            opened_at=state.get("opened_at"),
            seconds_left=seconds_left,
            escalation_fired=bool(state.get("escalated")),
            store=self._store_name(),
            counters=counters,
        )

    def _store_name(self) -> str:
        return "memory" if self._in_fallback else "redis"

    async def reset(self) -> BreakerStatus:
        """Manually close the breaker and clear the trip counters.

        Returns the pre-reset snapshot; the API layer writes it to
        ``config_audit_log``. Resetting a breaker that is already closed is
        honest and idempotent — the audit row records that too.
        """
        before = await self.status()
        r = await self._get_redis()
        if r is not None:
            try:
                await r.delete(self._state_key, *self._counter_keys.values())
            except Exception as e:
                self._warn_fallback(f"reset error: {e}")
                self._redis = None
                self._fallback_reset()
        else:
            self._fallback_reset()
        logger.warning(
            "containment breaker manually reset: state and trip counters"
            " cleared (was: %s)",
            before.state,
        )
        return before

    # -- In-memory fallback mirrors ------------------------------------------

    def _fallback_read(self, now: float) -> Optional[Dict[str, Any]]:
        if self._fallback_state is None:
            return None
        if now >= self._fallback_deadline:
            self._fallback_state = None
            return None
        return dict(self._fallback_state)

    def _fallback_seconds_left(self, now: float) -> Optional[int]:
        if self._fallback_state is None:
            return None
        return max(0, int(math.ceil(self._fallback_deadline - now)))

    def _fallback_note(self, counter: str, now: float) -> None:
        self._fallback_counters[counter].append(now)

    def _fallback_trip(self, reason: str, rule: str, now: float) -> None:
        existing = self._fallback_read(now)
        if existing is not None:
            logger.warning(
                "containment breaker re-tripped while OPEN (%s); cooldown"
                " re-armed, first cause kept: %s",
                reason,
                existing.get("reason"),
            )
            self._fallback_deadline = now + self._cooldown
            return
        self._fallback_state = {
            "state": OPEN,
            "reason": reason,
            "rule": rule,
            "opened_at": now,
            "escalated": False,
        }
        self._fallback_deadline = now + self._cooldown
        logger.error(
            "containment breaker OPEN: %s (%s) — every action now waits for"
            " a person until %ds after the last trip signal",
            reason,
            rule,
            int(self._cooldown),
        )

    def _fallback_claim(self, now: float) -> bool:
        state = self._fallback_read(now)
        if state is None or state.get("escalated"):
            return False
        state["escalated"] = True
        self._fallback_state = state
        logger.warning(
            "containment breaker escalation claimed once for the OPEN period"
            " started at %s",
            state.get("opened_at"),
        )
        return True

    def _fallback_reset(self) -> None:
        self._fallback_state = None
        self._fallback_deadline = 0.0
        for events in self._fallback_counters.values():
            events.clear()


def open_state_rule(seconds_left: Optional[int]) -> str:
    """The rationale a guard renders for every action gated while OPEN."""
    return decision_rule("response.breaker_open", seconds_left)
