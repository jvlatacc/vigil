"""Blast-radius containment quotas: bounded containment volume per window (#944).

The third gate between the Responder's confidence and the actuator (spec
D3): machine-speed containment is bounded per subnet and globally, per
fixed minute/hour window. A soft breach sends the action to a person; the
hourly ceiling is the hard edge — its verdict carries a breaker trip
reason the guard chain hands to the circuit breaker when they are wired
together.

Counters follow the ``RedisDedupSet`` durability shape
(``core.ingestion.dedup``): Redis ``INCR`` keys namespaced
``vigil:containment:quota:{scope}:{window}`` with a TTL per window, and a
per-process in-memory fallback when Redis is unavailable — the transition
logged once in each direction, enforcement never degraded. The fallback is
per-process, so a multi-replica deployment needs Redis for shared
enforcement; counts made during an outage stay in memory and are not
merged back into Redis on recovery.

The quota is spent when an action is approved for auto-execution, which in
the guard chain is guard time: an action that pends on its own quota
verdict still consumed a slot, so the create-to-execute gap can overshoot
within one poll cycle. The spec accepts that overshoot and backs the hard
edge with the breaker.

Lives in ``core/`` because ``core`` must not import ``services``.
"""

from __future__ import annotations

import asyncio
import enum
import ipaddress
import logging
import time
from dataclasses import dataclass
from typing import Optional, Sequence, Union

from core.config import DEFAULT_REDIS_URL, get_settings
from core.platform.log_redaction import redact_url
from core.response.config import decision_rule
from core.response.guards_config import GuardConfig

logger = logging.getLogger(__name__)

MINUTE = 60
HOUR = 3600

# A window's key outlives the window by one window-length, so a reader
# straddling the boundary still sees the count, while every key stays
# TTL-bounded like all quota state.
MINUTE_TTL_SECONDS = 2 * MINUTE
HOUR_TTL_SECONDS = 2 * HOUR

# The dedup set's DEFAULT_MAX_SIZE: the fallback stays bounded the same way.
MAX_FALLBACK_WINDOWS = 10_000

Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class QuotaState(enum.Enum):
    """What one spend read back as."""

    OK = "ok"
    SOFT_EXCEEDED = "soft_exceeded"  # routes to human approval
    HARD_EXCEEDED = "hard_exceeded"  # trips the breaker


@dataclass(frozen=True)
class QuotaVerdict:
    """A spend and its judgment, rendered the way every decision is."""

    state: QuotaState
    rule: str  # decision_rule-style: response.quota_soft_exceeded=...
    detail: str  # the counts behind the verdict
    # Set on HARD_EXCEEDED: the reason the guard chain hands to
    # ContainmentBreaker.trip(). The quota emits the signal; the breaker
    # consumes it (guard-chain integration).
    breaker_trip_reason: Optional[str] = None


def _now() -> float:
    """The clock, in one place so tests can hold or step it."""
    return time.time()


def subnet_scope(target_ip: Optional[str], prefix: int) -> Optional[Network]:
    """The subnet a target's quota spends against, or None without an IP.

    There is no subnet registry (spec D3): the scope is the target IP
    masked at the configured prefix. The same prefix applies to IPv6, so a
    small prefix makes an IPv6 scope effectively unbounded — an operator
    tuning the prefix tunes both families.
    """
    if not target_ip:
        return None
    try:
        address = ipaddress.ip_address(target_ip)
    except ValueError:
        return None
    return ipaddress.ip_network(f"{address}/{prefix}", strict=False)


def _scope_key(network: Network) -> str:
    # A "/" reads fine in Redis but poorly in dashboards and shell tabs.
    return f"subnet:{network.network_address}_{network.prefixlen}"


def _window_key(scope: str, window: str, epoch: int) -> str:
    return f"vigil:containment:quota:{scope}:{window}:{epoch}"


def _usable_hosts(network: Network) -> int:
    # IPv4 reserves the network and broadcast addresses; IPv6 has none.
    hosts = network.num_addresses - (2 if network.version == 4 else 0)
    return max(hosts, 0)


def _subnet_limit(network: Network, pct_per_min: float) -> int:
    # 5% of a /24 is 12.7 -> 12 actions; a scope too small to carry hosts
    # (a /32) still floors at one action per window.
    return max(1, int(_usable_hosts(network) * pct_per_min / 100))


def _evaluate(
    subnet_count: Optional[int],
    minute_count: int,
    hour_count: int,
    network: Optional[Network],
    config: GuardConfig,
) -> QuotaVerdict:
    """Judge one spend. The hard edge dominates; detail names every breach."""
    hour_detail = f"global {hour_count}/{config.quota_global_per_hour} per hour"
    if hour_count > config.quota_global_per_hour:
        return QuotaVerdict(
            QuotaState.HARD_EXCEEDED,
            decision_rule("response.quota_hard_ceiling", hour_detail),
            hour_detail,
            breaker_trip_reason=f"quota hard ceiling: {hour_detail}",
        )
    soft: list[str] = []
    if network is not None and subnet_count is not None:
        subnet_limit = _subnet_limit(network, config.quota_subnet_pct_per_min)
        if subnet_count > subnet_limit:
            soft.append(
                f"subnet {network.with_prefixlen} {subnet_count}/{subnet_limit}"
                " per minute"
            )
    if minute_count > config.quota_global_per_min:
        soft.append(f"global {minute_count}/{config.quota_global_per_min} per minute")
    if soft:
        detail = "; ".join(soft)
        return QuotaVerdict(
            QuotaState.SOFT_EXCEEDED,
            decision_rule("response.quota_soft_exceeded", detail),
            detail,
        )
    parts = [
        f"global {minute_count}/{config.quota_global_per_min} per minute",
        hour_detail,
    ]
    if network is not None and subnet_count is not None:
        subnet_limit = _subnet_limit(network, config.quota_subnet_pct_per_min)
        parts.insert(
            0,
            f"subnet {network.with_prefixlen} {subnet_count}/{subnet_limit} per minute",
        )
    detail = "; ".join(parts)
    return QuotaVerdict(
        QuotaState.OK,
        decision_rule("response.quota_within_limits", detail),
        detail,
    )


class ContainmentQuota:
    """Per-subnet and global containment counters on the dedup-set shape.

    One instance per daemon process. Each ``record_and_check`` spends one
    slot on every applicable counter (one Redis round-trip) and judges the
    spend; ``check_only`` is the same judgment without the spend, for the
    executor re-check before dispatching.
    """

    def __init__(self, *, redis_url: Optional[str] = None):
        self.redis_url = redis_url or get_settings().redis_url or DEFAULT_REDIS_URL
        self._redis = None
        self._in_fallback = False
        self._lock = asyncio.Lock()
        # key -> (count, expires_at). The window lives in the key (the
        # epoch), so expiry here only bounds memory, not correctness.
        self._fallback: dict[str, tuple[int, float]] = {}

    # -- Redis plumbing, the RedisDedupSet shape ---------------------------

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            # Probe the connection so we fail fast here rather than per-call.
            await self._redis.ping()
            logger.info("ContainmentQuota connected to %s", redact_url(self.redis_url))
            if self._in_fallback:
                self._in_fallback = False
                logger.warning(
                    "ContainmentQuota Redis recovered; %d window(s) counted"
                    " during the outage exist only in memory and are not"
                    " merged into Redis",
                    len(self._fallback),
                )
        except Exception as e:
            self._warn_fallback(f"init failed: {e}")
            self._redis = None
        return self._redis

    def _warn_fallback(self, reason: str):
        """Log once per Redis -> fallback transition, not per failed call."""
        if not self._in_fallback:
            logger.error(
                "ContainmentQuota Redis unavailable, using in-memory fallback"
                " (%s); quota state will not survive restarts or be shared"
                " across processes",
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

    # -- counting ----------------------------------------------------------

    async def record_and_check(
        self, action_type: str, target_ip: Optional[str], config: GuardConfig
    ) -> QuotaVerdict:
        """Spend one slot on every applicable counter, then judge the spend.

        ``action_type`` rides the guard-chain call shape; spec D3 bounds
        actions per window, not per type. Quotas off is an operator's
        decision, rendered like any other rule.
        """
        if not config.quotas_enabled:
            return _disabled_verdict()
        network = subnet_scope(target_ip, config.subnet_scope_prefix)
        now = _now()
        counters = _counters(network, now)
        counts = await self._increment(counters)
        if counts is None:
            counts = self._fallback_increment(counters, now)
        return _evaluate(
            counts.get("subnet"), counts["minute"], counts["hour"], network, config
        )

    async def check_only(
        self, action_type: str, target_ip: Optional[str], config: GuardConfig
    ) -> QuotaVerdict:
        """The same judgment without spending: the executor's re-check.

        During a Redis outage it reads only outage-local counts — counts
        made before the outage are invisible until recovery, the same gap
        the dedup set documents for its fallback.
        """
        if not config.quotas_enabled:
            return _disabled_verdict()
        network = subnet_scope(target_ip, config.subnet_scope_prefix)
        now = _now()
        counters = _counters(network, now)
        r = await self._get_redis()
        if r is None:
            counts = self._fallback_read(counters, now)
        else:
            try:
                pipe = r.pipeline()
                for key, _, _ in counters:
                    pipe.get(key)
                values = await pipe.execute()
            except Exception as e:
                self._warn_fallback(f"get error: {e}")
                self._redis = None
                counts = self._fallback_read(counters, now)
            else:
                counts = {
                    name: int(v or 0) for (_, _, name), v in zip(counters, values)
                }
        return _evaluate(
            counts.get("subnet"), counts["minute"], counts["hour"], network, config
        )

    async def _increment(
        self, counters: Sequence[tuple[str, int, str]]
    ) -> Optional[dict[str, int]]:
        """One round-trip: INCR+EXPIRE each counter. None -> use the fallback."""
        r = await self._get_redis()
        if r is None:
            return None
        try:
            async with self._lock:
                pipe = r.pipeline()
                for key, ttl, _ in counters:
                    pipe.incr(key)
                    # Unconditional: an INCR that outlives its TTL would be
                    # an immortal counter, so the expiry rides every spend.
                    pipe.expire(key, ttl)
                results = await pipe.execute()
        except Exception as e:
            self._warn_fallback(f"incr error: {e}")
            self._redis = None
            return None
        return {
            name: int(results[index * 2]) for index, (_, _, name) in enumerate(counters)
        }

    def _fallback_increment(
        self, counters: Sequence[tuple[str, int, str]], now: float
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key, ttl, name in counters:
            count, expires_at = self._fallback.get(key, (0, 0.0))
            if expires_at <= now:
                count, expires_at = 0, now + ttl
            count += 1
            self._fallback[key] = (count, expires_at)
            counts[name] = count
        self._prune_fallback(now)
        return counts

    def _fallback_read(
        self, counters: Sequence[tuple[str, int, str]], now: float
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key, _, name in counters:
            count, expires_at = self._fallback.get(key, (0, 0.0))
            counts[name] = count if expires_at > now else 0
        return counts

    def _prune_fallback(self, now: float) -> None:
        """Bound the fallback the way the dedup set bounds its set."""
        if len(self._fallback) <= MAX_FALLBACK_WINDOWS:
            return
        live = {k: v for k, v in self._fallback.items() if v[1] > now}
        if len(live) > MAX_FALLBACK_WINDOWS:
            evict = sorted(live.items(), key=lambda item: item[1][1])[
                : len(live) - MAX_FALLBACK_WINDOWS
            ]
            for key, _ in evict:
                live.pop(key, None)
        self._fallback = live


def _disabled_verdict() -> QuotaVerdict:
    return QuotaVerdict(
        QuotaState.OK,
        decision_rule("response.quotas_enabled", False),
        "quotas disabled",
    )


def _counters(network: Optional[Network], now: float) -> list[tuple[str, int, str]]:
    """The (key, ttl, name) counters one spend touches, global first."""
    minute_epoch = int(now // MINUTE)
    hour_epoch = int(now // HOUR)
    counters = [
        (_window_key("global", "min", minute_epoch), MINUTE_TTL_SECONDS, "minute"),
        (_window_key("global", "hour", hour_epoch), HOUR_TTL_SECONDS, "hour"),
    ]
    if network is not None:
        counters.append(
            (
                _window_key(_scope_key(network), "min", minute_epoch),
                MINUTE_TTL_SECONDS,
                "subnet",
            )
        )
    return counters
