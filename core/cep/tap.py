"""Non-blocking tap on the daemon's finding queue (spec ACs 1 and 5).

The daemon's finding flow is one bounded asyncio queue: poller, Kafka, the
scheduler and federation all put, and only ``FindingProcessor`` gets — it
alone settles the per-item stored-acks (``core.ingestion.ack``). The CEP
layer must watch that flow without ever sitting in it.

``FindingTeeQueue`` is the producer-facing queue with a tap: it subclasses
``asyncio.Queue`` so producers keep the exact contract they had (same
maxsize, same blocking ``put``, same ack futures — the processor still drains
and settles as before), while every finding that enters is mirrored into the
engine's own bounded queue via ``CepTap.observe``. The mirror never blocks
and never raises: on overflow the newest event (the one arriving) is dropped,
counted in ``cep_dropped_total``, and the degraded flag is raised until the
queue has headroom again.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from core.telemetry import get_meter

logger = logging.getLogger(__name__)

# Log the drop transition, then every 100th drop — a saturated tap under
# overload must stay visible without flooding the log; the counters remain
# the durable record either way.
_DROP_LOG_EVERY = 100


class CepTap:
    """The second leg of the tee: the engine's bounded, never-blocking queue.

    Owns the tap queue, the drop/degraded accounting, and the OTEL mirrors of
    the counters. Instruments are created on first record rather than at
    import (the ``ProbeMetrics`` pattern in ``services.daemon.metrics``), so
    they bind to the real meter once ``init_telemetry`` has run and to the
    no-op one when it has not.
    """

    def __init__(self, queue_max: int = 1000) -> None:
        self.queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=max(1, queue_max))
        # Surfaced verbatim through MetricsServer._collect_metrics and the
        # /status JSON — the names the spec and ACs call for. cep_degraded is
        # the degraded gauge: 1 while the tap has dropped (until the queue
        # has headroom again).
        self.stats: Dict[str, Any] = {
            "cep_events_seen": 0,
            "cep_dropped_total": 0,
            "cep_degraded": 0,
        }
        self._logged_drops = 0
        self._events_counter: Any = None
        self._dropped_counter: Any = None
        self._instruments_ready = False

    def observe(self, item: Any) -> None:
        """Mirror one finding into the tap queue. Never blocks, never raises."""
        self.stats["cep_events_seen"] += 1
        # Room right now is evidence the engine consumer has drained since
        # the last drop, so the tap is keeping up again (checked before the
        # put: at maxsize=1 a successful put leaves the queue exactly full).
        if self.queue.qsize() < self.queue.maxsize:
            self.stats["cep_degraded"] = 0
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop the newest event = the one arriving; the spine is untouched.
            self._on_drop()
            return
        self._record(self._events_counter)

    def _on_drop(self) -> None:
        self.stats["cep_dropped_total"] += 1
        self.stats["cep_degraded"] = 1
        self._record(self._dropped_counter)
        total = self.stats["cep_dropped_total"]
        if total == 1 or total - self._logged_drops >= _DROP_LOG_EVERY:
            self._logged_drops = total
            logger.warning(
                "CEP tap queue full: %d event(s) dropped; the finding spine is "
                "unaffected and the tap stays degraded until the queue drains",
                total,
            )

    def _ensure_instruments(self) -> None:
        if self._instruments_ready:
            return
        self._instruments_ready = True
        try:
            meter = get_meter("vigil.daemon")
            self._events_counter = meter.create_counter(
                name="vigil.cep.events",
                description="Findings seen by the CEP tap on the daemon finding queue",
                unit="1",
            )
            self._dropped_counter = meter.create_counter(
                name="vigil.cep.dropped",
                description="Findings dropped from the CEP tap queue on overflow",
                unit="1",
            )
        except Exception as _err:
            logger.debug("OTEL CEP instruments unavailable: %s", _err)

    def _record(self, counter: Any) -> None:
        self._ensure_instruments()
        try:
            if counter is not None:
                counter.add(1)
        except Exception as _err:
            logger.debug("OTEL CEP record failed (non-fatal): %s", _err)


class FindingTeeQueue(asyncio.Queue):
    """The daemon's finding queue with a non-blocking CEP tap.

    A subclass, not a wrapper, so the blocking leg IS the processor's input
    queue: identical bound, identical backpressure, identical ack flow —
    only the mirror is added. ``put_nowait`` alone is overridden because
    ``asyncio.Queue.put`` is implemented on top of it (wait for room, then
    ``put_nowait``), so one override mirrors each item exactly once for both
    producer call shapes.
    """

    def __init__(self, *, tap: CepTap, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize)
        self._tap = tap

    def put_nowait(self, item: Any) -> None:
        # Mirror only after the spine accepted the item: one that raises
        # QueueFull never entered the daemon queue and must not count as
        # seen. No await sits between enqueue and mirror, so nothing can
        # observe the item in between.
        super().put_nowait(item)
        if isinstance(item, dict) and item.get("type") == "finding":
            self._tap.observe(item)
