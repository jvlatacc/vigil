"""Backoff schedule: exponential, jittered, capped, and pure — the rng is
injected so a fleet's reconnection pattern is testable and reproducible."""

from __future__ import annotations

import pytest

from services.edge.sync.backoff import next_delay


def test_first_attempt_is_half_deterministic_half_jitter() -> None:
    low = next_delay(0, base_seconds=2.0, max_seconds=60.0, rng=lambda: 0.0)
    high = next_delay(0, base_seconds=2.0, max_seconds=60.0, rng=lambda: 1.0)
    assert low == pytest.approx(1.0)  # half of the 2s window
    assert high == pytest.approx(2.0)  # the full window


def test_window_doubles_each_attempt_until_the_cap() -> None:
    window = [
        next_delay(attempt, base_seconds=2.0, max_seconds=60.0, rng=lambda: 1.0)
        for attempt in range(8)
    ]
    assert window[0] == pytest.approx(2.0)
    assert window[1] == pytest.approx(4.0)
    assert window[2] == pytest.approx(8.0)
    assert all(value == pytest.approx(60.0) for value in window[5:])  # capped


def test_delay_never_exceeds_the_cap_even_with_full_jitter() -> None:
    for attempt in range(12):
        assert (
            next_delay(attempt, base_seconds=2.0, max_seconds=7.0, rng=lambda: 1.0)
            <= 7.0
        )


def test_negative_attempt_is_rejected() -> None:
    with pytest.raises(ValueError, match="attempt"):
        next_delay(-1)


def test_nonpositive_base_is_rejected() -> None:
    with pytest.raises(ValueError, match="base_seconds"):
        next_delay(0, base_seconds=0.0)
