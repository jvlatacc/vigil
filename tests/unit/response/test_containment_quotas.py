"""Quota windows that fail toward people, not silence (spec Verification row 4).

Twelve of twelve slots execute on a /24 at 5%/min and the thirteenth reads
SOFT; the window resets; the global caps enforce independently of the
subnet scope; the hourly ceiling carries the breaker trip; and with Redis
down the in-memory fallback keeps enforcing, logging the degradation once
per transition. A stub Redis mirrors the dedup tests; fakeredis is not a
dev dependency.
"""

from __future__ import annotations

import logging

import pytest

import core.response.quotas as quotas
from core.response.guards_config import GuardConfig
from core.response.quotas import ContainmentQuota, QuotaState

pytestmark = pytest.mark.unit


class _StubRedis:
    """Counter subset of redis.asyncio: incr/expire/get pipelines."""

    def __init__(self):
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def ping(self):
        return True

    def pipeline(self):
        return _StubPipeline(self)

    async def close(self):
        pass


class _StubPipeline:
    def __init__(self, redis: _StubRedis):
        self._redis = redis
        self._ops: list[tuple] = []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    def get(self, key):
        self._ops.append(("get", key))

    async def execute(self):
        out = []
        for op, key, *args in self._ops:
            if op == "incr":
                self._redis.counters[key] = self._redis.counters.get(key, 0) + 1
                out.append(self._redis.counters[key])
            elif op == "expire":
                self._redis.ttls[key] = args[0]
                out.append(True)
            else:
                out.append(self._redis.counters.get(key))
        self._ops = []
        return out


@pytest.fixture
def stub_redis(monkeypatch):
    import redis.asyncio as aioredis

    stubs: list[_StubRedis] = []

    def from_url(url, decode_responses=True):
        stubs.append(_StubRedis())
        return stubs[-1]

    monkeypatch.setattr(aioredis, "from_url", from_url)
    return stubs


@pytest.fixture
def dead_redis(monkeypatch):
    """Redis configured but unreachable: every init fails into the fallback."""
    import redis.asyncio as aioredis

    def from_url(url, decode_responses=True):
        raise ConnectionError("redis down")

    monkeypatch.setattr(aioredis, "from_url", from_url)


class _Clock:
    def __init__(self):
        self.now = 1_760_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    held = _Clock()
    monkeypatch.setattr(quotas, "_now", held)
    return held


async def _spend(quota: ContainmentQuota, target_ip, config):
    return await quota.record_and_check("isolate_host", target_ip, config)


async def test_twelve_slots_execute_and_the_thirteenth_pends(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig()  # a /24 at 5%/min floors out at 12 slots
    for _ in range(12):
        verdict = await _spend(quota, "10.0.0.53", config)
        assert verdict.state is QuotaState.OK
    thirteenth = await _spend(quota, "10.0.0.53", config)
    assert thirteenth.state is QuotaState.SOFT_EXCEEDED
    assert thirteenth.rule.startswith("response.quota_soft_exceeded=")
    assert "subnet 10.0.0.0/24 13/12" in thirteenth.detail
    # Soft is a pend, not a trip: the breaker signal is the hard edge's.
    assert thirteenth.breaker_trip_reason is None


async def test_the_minute_window_resets(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig()
    for _ in range(13):
        await _spend(quota, "10.0.0.53", config)
    clock.advance(61)  # past the minute window
    verdict = await _spend(quota, "10.0.0.53", config)
    assert verdict.state is QuotaState.OK


async def test_a_scope_is_the_whole_subnet_not_the_host(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig()
    for _ in range(12):
        await _spend(quota, "10.0.0.53", config)
    # Same /24, different host: the scope is shared, so it pends too.
    sibling = await _spend(quota, "10.0.0.54", config)
    assert sibling.state is QuotaState.SOFT_EXCEEDED
    # The neighbouring /24 carries its own counter.
    fresh = await _spend(quota, "10.0.1.53", config)
    assert fresh.state is QuotaState.OK


async def test_the_global_minute_cap_enforces_independently(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    # A /8 scope never pends on its own; the global minute cap does it.
    config = GuardConfig(subnet_scope_prefix=8, quota_global_per_min=3)
    for ip in ("10.0.0.53", "10.0.0.54", "10.0.0.55"):
        assert (await _spend(quota, ip, config)).state is QuotaState.OK
    fourth = await _spend(quota, "10.0.0.56", config)
    assert fourth.state is QuotaState.SOFT_EXCEEDED
    assert "global 4/3 per minute" in fourth.detail


async def test_the_hourly_ceiling_carries_the_breaker_trip(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig(
        subnet_scope_prefix=8, quota_global_per_min=100, quota_global_per_hour=5
    )
    for _ in range(5):
        assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK
    sixth = await _spend(quota, "10.0.0.53", config)
    assert sixth.state is QuotaState.HARD_EXCEEDED
    assert sixth.rule.startswith("response.quota_hard_ceiling=")
    assert "global 6/5 per hour" in sixth.detail
    # The trip signal the guard chain hands to the breaker.
    assert sixth.breaker_trip_reason == "quota hard ceiling: global 6/5 per hour"


async def test_a_hard_ceiling_dominates_a_soft_one(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig(
        subnet_scope_prefix=8, quota_global_per_min=3, quota_global_per_hour=5
    )
    for _ in range(5):
        await _spend(quota, "10.0.0.53", config)
    sixth = await _spend(quota, "10.0.0.53", config)
    # The minute cap is breached too, but the hard edge decides.
    assert sixth.state is QuotaState.HARD_EXCEEDED
    assert sixth.breaker_trip_reason is not None


async def test_window_keys_carry_window_ttls(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    await _spend(quota, "10.0.0.53", GuardConfig())
    ttls = stub_redis[0].ttls
    assert len(ttls) == 3  # global minute, global hour, subnet minute
    for key, ttl in ttls.items():
        expected = (
            quotas.HOUR_TTL_SECONDS if ":hour:" in key else quotas.MINUTE_TTL_SECONDS
        )
        assert ttl == expected
    assert any("global:hour" in key for key in ttls)


async def test_with_redis_down_the_fallback_still_enforces_and_logs(
    dead_redis, clock, caplog
):
    with caplog.at_level(logging.INFO, logger="core.response.quotas"):
        quota = ContainmentQuota(redis_url="redis://dead/0")
        config = GuardConfig()
        for _ in range(12):
            assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK
        thirteenth = await _spend(quota, "10.0.0.53", config)
    assert thirteenth.state is QuotaState.SOFT_EXCEEDED
    assert "subnet 10.0.0.0/24 13/12" in thirteenth.detail
    # Degradation logs on the transition, once — not once per failed call.
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "in-memory fallback" in errors[0].getMessage()


async def test_the_fallback_window_resets(dead_redis, clock):
    quota = ContainmentQuota(redis_url="redis://dead/0")
    config = GuardConfig()
    for _ in range(13):
        await _spend(quota, "10.0.0.53", config)
    clock.advance(61)
    assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK


async def test_recovery_is_logged_and_outage_counts_are_not_merged(
    monkeypatch, clock, caplog
):
    import redis.asyncio as aioredis

    state = {"down": True}
    stubs: list[_StubRedis] = []

    def from_url(url, decode_responses=True):
        if state["down"]:
            raise ConnectionError("redis down")
        stubs.append(_StubRedis())
        return stubs[-1]

    monkeypatch.setattr(aioredis, "from_url", from_url)

    with caplog.at_level(logging.INFO, logger="core.response.quotas"):
        quota = ContainmentQuota(redis_url="redis://flaky/0")
        config = GuardConfig()
        assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK
        assert quota._in_fallback is True
        state["down"] = False
        assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK
        assert quota._in_fallback is False

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(errors) == 1 and "in-memory fallback" in errors[0].getMessage()
    assert len(warnings) == 1 and "recovered" in warnings[0].getMessage()
    # The outage's count stayed in memory: Redis restarted from zero.
    assert all(count == 1 for count in stubs[0].counters.values())


@pytest.mark.parametrize("target", [None, "not-an-ip", "10.0.0.999"])
async def test_a_target_without_a_usable_ip_still_spends_globally(
    stub_redis, clock, target
):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    verdict = await _spend(quota, target, GuardConfig())
    assert verdict.state is QuotaState.OK
    assert "global 1/30 per minute" in verdict.detail
    # No subnet scope: no subnet counter was touched.
    assert not any(
        key.startswith("vigil:containment:quota:subnet")
        for key in stub_redis[0].counters
    )


async def test_quotas_disabled_reads_ok(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    verdict = await _spend(quota, "10.0.0.53", GuardConfig(quotas_enabled=False))
    assert verdict.state is QuotaState.OK
    assert verdict.rule == "response.quotas_enabled=False"
    # Off means off: no slot spent, no Redis contacted at all.
    assert stub_redis == []


async def test_check_only_reads_without_spending(stub_redis, clock):
    quota = ContainmentQuota(redis_url="redis://stub/0")
    config = GuardConfig(quota_global_per_min=2)
    for _ in range(2):
        assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.OK
    at_limit = await quota.check_only("isolate_host", "10.0.0.53", config)
    assert at_limit.state is QuotaState.OK  # at the cap is not over it
    assert (await _spend(quota, "10.0.0.53", config)).state is QuotaState.SOFT_EXCEEDED
    over = await quota.check_only("isolate_host", "10.0.0.53", config)
    assert over.state is QuotaState.SOFT_EXCEEDED
    before = dict(stub_redis[0].counters)
    await quota.check_only("isolate_host", "10.0.0.53", config)
    assert stub_redis[0].counters == before
