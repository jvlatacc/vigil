"""The breaker trips on all three conditions, forces humans while OPEN,
escalates once per period, closes without flapping, and decays its counters
(#944, spec D4).

These tests exercise the in-memory fallback path (Redis unreachable) because
that's what runs deterministically in CI without a live Redis — the same
choice ``tests/unit/ingestion/test_dedup.py`` makes. A Redis-backed
integration test belongs under tests/integration with the ``integration``
marker.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from core.response.breaker import ContainmentBreaker
from core.response.guards_config import GuardConfig

pytestmark = pytest.mark.unit

DEAD_REDIS = "redis://127.0.0.1:1/0"


class Clock:
    """A controllable clock: the breaker's cooldowns are its whole story."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _breaker(clock: Clock, **overrides) -> ContainmentBreaker:
    config = GuardConfig(**overrides) if overrides else GuardConfig()
    return ContainmentBreaker(
        config,
        redis_url=DEAD_REDIS,
        namespace=f"test-{clock.now:.0f}",
        clock=clock,
    )


async def test_a_fresh_breaker_is_closed():
    breaker = _breaker(Clock())
    assert await breaker.is_open() is False
    status = await breaker.status()
    assert status.state == "closed"
    assert status.reason is None
    assert status.escalation_fired is False


async def test_three_invariant_blocks_within_the_window_trip():
    clock = Clock()
    breaker = _breaker(clock)
    assert await breaker.note_invariant_block() is None
    assert await breaker.note_invariant_block() is None
    assert await breaker.is_open() is False

    rule = await breaker.note_invariant_block()
    assert rule is not None
    assert rule.startswith("response.breaker_invariant_probe_trip=")
    assert "met" in rule
    assert await breaker.is_open() is True
    status = await breaker.status()
    assert status.state == "open"
    assert "protected-asset probe run" in (status.reason or "")


async def test_two_probes_are_noise_not_a_trip():
    clock = Clock()
    breaker = _breaker(clock)
    await breaker.note_invariant_block()
    await breaker.note_invariant_block()
    assert await breaker.is_open() is False


async def test_ten_origin_unverified_blocks_trip():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(9):
        assert await breaker.note_origin_unverified() is None
    assert await breaker.is_open() is False

    rule = await breaker.note_origin_unverified()
    assert rule is not None
    assert rule.startswith("response.breaker_origin_flood_trip=")
    status = await breaker.status()
    assert status.state == "open"
    assert "origin-unverified flood" in (status.reason or "")


async def test_a_quota_hard_ceiling_signal_trips_immediately():
    clock = Clock()
    breaker = _breaker(clock)
    signal = SimpleNamespace(detail="global/hour 201 > 200")
    rule = await breaker.trip_on_quota(signal)
    assert rule.startswith("response.quota_hard_ceiling=")
    assert "global/hour 201 > 200" in rule
    status = await breaker.status()
    assert status.state == "open"
    assert "quota hard ceiling" in (status.reason or "")


async def test_the_trip_window_is_ten_minutes():
    clock = Clock()
    breaker = _breaker(clock)
    # Two probes, then the window slides past them before two more arrive:
    # never three within any trailing 10 minutes, so never a trip.
    await breaker.note_invariant_block()
    await breaker.note_invariant_block()
    clock.advance(601.0)
    await breaker.note_invariant_block()
    await breaker.note_invariant_block()
    assert await breaker.is_open() is False


async def test_the_breaker_auto_closes_after_the_cooldown():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()
    assert await breaker.is_open() is True

    clock.advance(899.0)
    assert await breaker.is_open() is True
    status = await breaker.status()
    assert status.seconds_left is not None and 1 <= status.seconds_left <= 2

    clock.advance(2.0)
    assert await breaker.is_open() is False
    assert (await breaker.status()).state == "closed"


async def test_auto_close_leaves_the_counters_decayed():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()

    # Halfway through the cooldown the counters have decayed to half their
    # trip-time weight; the full decay horizon is twice the cooldown.
    clock.advance(450.0)
    status = await breaker.status()
    assert status.state == "open"
    assert status.counters["invariant_probe"]["recent"] == 3.0
    assert status.counters["invariant_probe"]["decayed"] == pytest.approx(2.25)

    clock.advance(460.0)
    status = await breaker.status()
    assert status.state == "closed"
    # The evidence that tripped the breaker decayed past half-life during
    # the cooldown and is dropped at close — the counters read zero.
    assert status.counters["invariant_probe"]["recent"] == 0.0
    assert status.counters["invariant_probe"]["decayed"] == 0.0


async def test_a_closed_breaker_does_not_flap_on_stale_evidence():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()
    clock.advance(900.0)
    assert await breaker.is_open() is False

    # No new events: the breaker stays closed through the decay horizon.
    for _ in range(6):
        clock.advance(300.0)
        assert await breaker.is_open() is False


async def test_fresh_probing_after_close_retrips_immediately():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()
    clock.advance(900.0)
    assert await breaker.is_open() is False

    # New evidence, new trip — no grace period after close.
    await breaker.note_invariant_block()
    await breaker.note_invariant_block()
    assert await breaker.is_open() is False
    rule = await breaker.note_invariant_block()
    assert rule is not None
    assert await breaker.is_open() is True


async def test_exactly_one_escalation_fires_per_open_period():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()

    claims = [await breaker.claim_escalation() for _ in range(10)]
    assert claims == [True] + [False] * 9
    assert (await breaker.status()).escalation_fired is True


async def test_a_retrip_while_open_does_not_reset_the_escalation_period():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()
    assert await breaker.claim_escalation() is True

    # A second burst while OPEN re-arms the cooldown but is the same period.
    clock.advance(100.0)
    for _ in range(3):
        await breaker.note_invariant_block()
    assert await breaker.claim_escalation() is False

    # A new OPEN period after the cooldown claims fresh.
    clock.advance(900.0)
    assert await breaker.is_open() is False
    for _ in range(3):
        await breaker.note_invariant_block()
    assert await breaker.claim_escalation() is True


async def test_claiming_escalation_on_a_closed_breaker_is_false():
    breaker = _breaker(Clock())
    assert await breaker.claim_escalation() is False


async def test_reset_clears_state_and_counters():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()
    await breaker.claim_escalation()

    before = await breaker.reset()
    assert before.state == "open"
    status = await breaker.status()
    assert status.state == "closed"
    assert status.escalation_fired is False
    assert status.counters["invariant_probe"]["recent"] == 0.0
    assert status.counters["origin_flood"]["recent"] == 0.0
    # A reset breaker is genuinely closed: a single new probe is noise again.
    await breaker.note_invariant_block()
    assert await breaker.is_open() is False


async def test_the_counters_are_independent():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_origin_unverified()
    # Three origin events do not trip the origin flood yet, and they are
    # not invariant-probe evidence — that counter reads zero throughout.
    assert await breaker.is_open() is False
    assert (await breaker.status()).counters["invariant_probe"]["recent"] == 0.0


async def test_the_fallback_transition_is_logged_once(caplog):
    clock = Clock()
    breaker = _breaker(clock)
    with caplog.at_level(logging.ERROR, logger="core.response.breaker"):
        for _ in range(3):
            await breaker.is_open()
            await breaker.note_invariant_block()
    fallback_logs = [
        record
        for record in caplog.records
        if "in-memory fallback" in record.getMessage()
    ]
    assert len(fallback_logs) == 1
    assert (await breaker.status()).store == "memory"


async def test_status_counts_decay_over_twice_the_cooldown():
    clock = Clock()
    breaker = _breaker(clock)
    for _ in range(3):
        await breaker.note_invariant_block()

    clock.advance(600.0)
    status = await breaker.status()
    assert status.state == "open"
    # Three events at age 600 of a 1800 horizon: 3 x (1 - 600/1800).
    assert status.counters["invariant_probe"]["decayed"] == pytest.approx(2.0)
