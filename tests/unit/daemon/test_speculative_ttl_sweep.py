"""The scheduled TTL sweep task is wired and runs its sweep.

The wiring is the risk, not the sweep: a task that is registered but never
reached — or reached with the wrong cadence — fails exactly the silent way
`_run_cleanup` once did (#675's lesson). The rollback sweep is patched in
the same style: the daemon tests here never touch Postgres.
"""

from unittest.mock import patch

import pytest

from core.response.fastpath.rollback import SweepOutcome
from services.daemon.config import SchedulerConfig
from services.daemon.scheduler import TaskScheduler

pytestmark = pytest.mark.unit


def _sweep_task(scheduler: TaskScheduler):
    tasks = [task for task in scheduler._tasks if task.name == "speculative_ttl_sweep"]
    assert len(tasks) == 1, "the TTL sweep must register exactly once"
    return tasks[0]


def test_the_ttl_sweep_is_registered_on_a_one_minute_cadence():
    scheduler = TaskScheduler(SchedulerConfig())

    task = _sweep_task(scheduler)

    assert task.enabled is True
    assert task.interval == 60
    assert task.run_on_start is False


@pytest.mark.asyncio
async def test_the_ttl_sweep_runs_the_rollback_sweep_off_the_scheduler():
    scheduler = TaskScheduler(SchedulerConfig())

    with patch(
        "core.response.fastpath.rollback.expire_speculative_actions",
        return_value=SweepOutcome(examined=3, released=2),
    ) as sweep:
        result = await scheduler._run_speculative_ttl_sweep()

    sweep.assert_called_once_with()
    assert result == {"speculative_examined": 3, "speculative_released": 2}
    assert scheduler.stats["speculative_released"] == 2


@pytest.mark.asyncio
async def test_the_ttl_sweep_reports_zero_when_nothing_is_expired():
    scheduler = TaskScheduler(SchedulerConfig())

    with patch(
        "core.response.fastpath.rollback.expire_speculative_actions",
        return_value=SweepOutcome(examined=0, released=0),
    ):
        result = await scheduler._run_speculative_ttl_sweep()

    assert result == {"speculative_examined": 0, "speculative_released": 0}
    assert scheduler.stats["speculative_released"] == 0
