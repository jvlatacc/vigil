"""Canary-credential rotation: the scheduler tick's contract.

The task's semantics, no database involved: one credential write per
DISTINCT ``canary_credential_ref`` (rows sharing a ref share a credential
and rotate together), ``rotated_at`` stamped only after the store write
succeeds — a rotation that did not happen is never recorded as one — and a
failed write counts its rows and leaves them for the next tick.

The real stamp against PostgreSQL is exercised in
tests/integration/test_decoy_session_capture.py (rotation stamp).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from core.response.decoy_rotation import (
    CANARY_MARKER,
    generate_canary_value,
    rotate_active_canaries,
)
from services.daemon.config import SchedulerConfig
from services.daemon.scheduler import TaskScheduler

pytestmark = pytest.mark.unit


class _Rows:
    """The registry read's query chain, reduced to what the rotation asks."""

    def __init__(self, rows: List[SimpleNamespace]):
        self._rows = rows

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self._rows)


class _Manager:
    """session_scope over prepared rows — the get_db_manager seam."""

    def __init__(self, rows: List[SimpleNamespace]):
        self._rows = rows

    @contextmanager
    def session_scope(self):
        yield _Rows(self._rows)


def _decoy(decoy_id: str, ref: str) -> SimpleNamespace:
    return SimpleNamespace(decoy_id=decoy_id, canary_credential_ref=ref)


def _rotate(
    monkeypatch,
    rows: List[SimpleNamespace],
    *,
    failing_refs: set = frozenset(),
) -> List[Dict[str, Any]]:
    """Run one rotation with the store and stamp seams faked; return the
    stamps the rotation attempted, in order."""
    written: List[Dict[str, Any]] = []

    def _set_secret(ref: str, value: str) -> bool:
        written.append({"ref": ref, "value": value})
        return ref not in failing_refs

    stamp_calls: List[List[str]] = []

    def _stamp(decoy_ids: List[str], when) -> None:
        stamp_calls.append(list(decoy_ids))

    import core.storage.connection

    monkeypatch.setattr(
        core.storage.connection, "get_db_manager", lambda: _Manager(rows)
    )
    import core.response.decoy_rotation as rotation

    monkeypatch.setattr(rotation, "set_secret", _set_secret)
    monkeypatch.setattr(rotation, "_stamp_rotated", _stamp)
    result = rotate_active_canaries()
    assert result["rotated"] == sum(len(ids) for ids in stamp_calls)
    return stamp_calls


def test_one_credential_write_per_distinct_ref_and_rows_stamped_together(
    monkeypatch,
):
    # decoy-a and decoy-b share REF1; decoy-c has its own REF2. Two writes,
    # two stamps — never one write per row, which would churn the same
    # credential twice per tick.
    rows = [
        _decoy("decoy-a", "DECOY_CANARY_PASSWORD"),
        _decoy("decoy-b", "DECOY_CANARY_PASSWORD"),
        _decoy("decoy-c", "OTHER_REF"),
    ]
    stamps = _rotate(monkeypatch, rows)
    assert stamps == [
        ["decoy-a", "decoy-b"],
        ["decoy-c"],
    ]


def test_a_failed_store_write_counts_its_rows_and_stamps_nothing(monkeypatch):
    rows = [
        _decoy("decoy-a", "BROKEN_REF"),
        _decoy("decoy-b", "GOOD_REF"),
    ]
    stamps = _rotate(monkeypatch, rows, failing_refs={"BROKEN_REF"})
    # Only the good ref rotates; the failed ref's rows are not stamped.
    assert stamps == [["decoy-b"]]


def test_no_active_decoys_is_a_clean_zero_and_touches_nothing(monkeypatch):
    written: List[Any] = []

    import core.response.decoy_rotation as rotation
    import core.storage.connection

    monkeypatch.setattr(core.storage.connection, "get_db_manager", lambda: _Manager([]))

    def _boom(*args):
        written.append(args)
        raise AssertionError("no credential writes when the registry is empty")

    monkeypatch.setattr(rotation, "set_secret", _boom)
    monkeypatch.setattr(rotation, "_stamp_rotated", _boom)
    result = rotate_active_canaries()
    assert result == {"scanned": 0, "rotated": 0, "failed": 0}


def test_generated_canary_embeds_the_marker():
    value = generate_canary_value()
    assert value.startswith(CANARY_MARKER + "-")


def test_scheduler_registers_the_rotation_task_at_its_daily_interval():
    scheduler = TaskScheduler(SchedulerConfig())
    by_name = {task.name: task for task in scheduler._tasks}
    task = by_name.get("mtd_canary_rotation")
    assert task is not None, "the canary rotation must be a registered task"
    assert task.interval == SchedulerConfig().mtd_canary_rotation_interval == 86400
    assert task.enabled is True
    # Hygiene is not gated on the MTD enable switch: rotation must run even
    # when MTD is disabled, so stale canaries never persist in live decoys.
    assert task.run_on_start is False


def test_scheduler_runner_records_rotations_and_failures(monkeypatch):
    scheduler = TaskScheduler(SchedulerConfig())

    import core.response.decoy_rotation as rotation

    async def _fake(now=None):
        return {"scanned": 3, "rotated": 2, "failed": 1}

    monkeypatch.setattr(rotation, "rotate_active_canaries_async", _fake)
    result = asyncio.run(scheduler._run_mtd_canary_rotation())
    assert result == {"scanned": 3, "rotated": 2, "failed": 1}
    assert scheduler.stats["mtd_canaries_rotated"] == 2
