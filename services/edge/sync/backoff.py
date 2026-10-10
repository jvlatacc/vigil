"""Jittered exponential backoff (design spec: "Backoff with jitter" in the
sync client; "jittered backoff — no push fan-in to saturate" for the
reconciliation storm risk).

Equal-jitter: each attempt's delay is half wait, half coin-flip, so a fleet
of nodes that all lost the control plane at the same instant does not
reconnect in lockstep. Pure function with the rng injected — tests pin the
sequence; production passes ``random.random``.
"""

from __future__ import annotations

import random
from collections.abc import Callable

DEFAULT_BASE_SECONDS = 2.0
DEFAULT_MAX_SECONDS = 60.0


def next_delay(
    attempt: int,
    *,
    base_seconds: float = DEFAULT_BASE_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    rng: Callable[[], float] | None = None,
) -> float:
    """Delay before retry ``attempt`` (0-based).

    Half of the exponential window is deterministic (``base * 2**attempt /
    2``), the other half is uniform jitter, and the whole thing is capped at
    ``max_seconds`` — so the schedule grows exponentially but never
    synchronizes a fleet and never sleeps forever.
    """
    if attempt < 0:
        raise ValueError(f"attempt must be >= 0, got {attempt}")
    if base_seconds <= 0:
        raise ValueError(f"base_seconds must be positive, got {base_seconds}")
    coin = (rng or random.random)()
    window = min(max_seconds, base_seconds * (2**attempt))
    return window / 2.0 + coin * (window / 2.0)
