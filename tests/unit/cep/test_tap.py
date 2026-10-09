"""Unit tests for the CEP finding-queue tee (spec ACs 1 and 5).

The contract under test: the tap mirrors every finding that enters the
daemon's finding queue, never blocks a producer, never settles an ack, and
degrades (drop newest + count) instead of growing or stalling under load.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from core.cep.tap import CepTap, FindingTeeQueue
from core.ingestion.ack import new_ack, settle_ack


def _finding_item(finding_id: str = "f-1", **extra: Any) -> Dict[str, Any]:
    """A queue item in the exact shape the daemon's producers put."""
    item: Dict[str, Any] = {
        "type": "finding",
        "source": "test",
        "data": {"finding_id": finding_id},
        "timestamp": "2026-10-09T00:00:00+00:00",
        "dedup": None,
        "dedup_key": None,
    }
    item.update(extra)
    return item


async def test_tee_mirrors_findings_to_tap_and_primary():
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=10)
    for i in range(3):
        await tee.put(_finding_item(f"f-{i}"))

    assert tee.qsize() == 3  # blocking leg intact: everything reaches the processor
    assert tap.queue.qsize() == 3  # engine leg saw every finding
    assert tap.stats["cep_events_seen"] == 3
    assert tap.stats["cep_dropped_total"] == 0
    assert tap.stats["cep_degraded"] == 0


async def test_saturated_tap_never_blocks_producers():
    """AC 5: a full CEP queue must not stall a producer whose spine has room."""
    tap = CepTap(queue_max=2)
    tee = FindingTeeQueue(tap=tap, maxsize=100)
    for i in range(2):
        await tee.put(_finding_item(f"fill-{i}"))
    assert tap.queue.qsize() == 2  # tap saturated

    # Would hang (and fail the wait_for) if the tap leg ever blocked.
    await asyncio.wait_for(tee.put(_finding_item("overflow")), timeout=1.0)

    assert tee.qsize() == 3  # spine received everything
    assert tap.stats["cep_dropped_total"] == 1
    assert tap.stats["cep_degraded"] == 1


async def test_overflow_drops_newest_and_keeps_oldest():
    tap = CepTap(queue_max=2)
    tee = FindingTeeQueue(tap=tap, maxsize=100)
    for i in range(5):
        await tee.put(_finding_item(f"f-{i}"))

    assert tap.stats["cep_events_seen"] == 5
    assert tap.stats["cep_dropped_total"] == 3
    assert tap.queue.qsize() == 2
    kept = [tap.queue.get_nowait()["data"]["finding_id"] for _ in range(2)]
    assert kept == ["f-0", "f-1"]


async def test_degraded_clears_when_tap_has_headroom():
    tap = CepTap(queue_max=1)
    tee = FindingTeeQueue(tap=tap, maxsize=100)
    await tee.put(_finding_item("a"))
    await tee.put(_finding_item("b"))  # tap full -> drop, degraded
    assert tap.stats["cep_degraded"] == 1

    tap.queue.get_nowait()  # the engine consumer drains
    await tee.put(_finding_item("c"))  # headroom again
    assert tap.stats["cep_degraded"] == 0


async def test_non_finding_items_are_not_mirrored():
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=10)

    await tee.put({"type": "response_candidate", "finding": {}})

    assert tap.stats["cep_events_seen"] == 0
    assert tap.queue.qsize() == 0
    assert tee.qsize() == 1  # still reaches the processor untouched


async def test_ack_settles_only_via_processor():
    """AC 5: the tee never settles an ack; the processor settles exactly once."""
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=10)
    ack = new_ack()
    await tee.put(_finding_item("f-1", ack=ack))

    assert not ack.done()  # mirroring must not have touched the ack

    item = tee.get_nowait()
    settle_ack(item["ack"], True)
    assert ack.done() and ack.result() is True
    settle_ack(item["ack"], False)  # a second settle is a no-op
    assert ack.result() is True


async def test_concurrent_producers_on_saturated_tap():
    """AC 5 under contention: producers racing on a full tap queue with a
    consumer on the spine — nobody hangs, every ack settles exactly once."""
    tap = CepTap(queue_max=2)
    tee = FindingTeeQueue(tap=tap, maxsize=3)
    acks: List["asyncio.Future[bool]"] = []

    async def producer(n: int) -> None:
        for i in range(10):
            ack = new_ack()
            acks.append(ack)
            await tee.put(_finding_item(f"p{n}-{i}", ack=ack))

    async def consumer() -> None:
        for _ in range(50):
            item = await tee.get()
            settle_ack(item["ack"], True)

    await asyncio.wait_for(
        asyncio.gather(
            consumer(), *(producer(n) for n in range(5)), return_exceptions=False
        ),
        timeout=10.0,
    )

    assert tee.qsize() == 0
    assert tap.stats["cep_events_seen"] == 50
    # The tap queue was never drained, so what it holds plus what it dropped
    # is exactly what it saw.
    assert tap.stats["cep_dropped_total"] + tap.queue.qsize() == 50
    assert all(ack.done() and ack.result() is True for ack in acks)


async def test_put_nowait_rejected_by_spine_is_not_counted():
    """An item the primary queue rejects never entered the daemon queue, so
    the tap must not count it as seen."""
    tap = CepTap(queue_max=10)
    tee = FindingTeeQueue(tap=tap, maxsize=1)
    await tee.put(_finding_item("a"))

    with pytest.raises(asyncio.QueueFull):
        tee.put_nowait(_finding_item("b"))

    assert tap.stats["cep_events_seen"] == 1
    assert tap.queue.qsize() == 1


def test_metrics_server_collects_cep_stats():
    """AC 8 (counters): the tap's stats surface through MetricsServer."""
    from services.daemon.config import MetricsConfig
    from services.daemon.metrics import MetricsServer

    server = MetricsServer(MetricsConfig())

    # CEP disabled: the tap is absent and /health reports it disabled,
    # never unhealthy.
    assert server.cep is None
    assert server._component_state("cep", None) == "disabled"

    # CEP enabled: the tap's counters flow into the collected metrics and
    # the health state is running.
    tap = CepTap(queue_max=4)
    tap.observe({"type": "finding", "data": {}})
    tap.observe({"type": "finding", "data": {}})
    server.cep = tap

    collected = server._collect_metrics()
    assert collected["cep"] == {
        "cep_events_seen": 2,
        "cep_dropped_total": 0,
        "cep_degraded": 0,
    }
    assert server._component_state("cep", tap) == "running"
