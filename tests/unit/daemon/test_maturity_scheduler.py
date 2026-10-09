"""The daemon's maturity scheduler loop: enabled, disabled, resilient, cancellable."""

import asyncio

import pytest

from services.daemon.maturity import PolicyMaturityScheduler

FULL_REPORT = {
    "archetypes_eligible": 0,
    "candidates_written": 0,
    "shadowed": 0,
    "unchanged": 0,
    "suspended": 0,
    "retired": 0,
    "lock_skipped": 0,
}


async def test_a_disabled_scheduler_never_runs_the_pass(monkeypatch):
    calls: list[int] = []

    async def fail_loudly(now=None):
        calls.append(1)
        return dict(FULL_REPORT)

    monkeypatch.setattr("core.policy_compiler.maturity.run_maturity_pass", fail_loudly)
    # The event is already set: the disabled branch's sleep returns at once
    # and the loop exits without ever reaching for the pass.
    shutdown = asyncio.Event()
    shutdown.set()

    await PolicyMaturityScheduler(interval_seconds=60, enabled=False).run(shutdown)

    assert calls == []


async def test_an_enabled_scheduler_runs_the_pass_and_exits_on_shutdown(
    monkeypatch,
):
    shutdown = asyncio.Event()
    calls: list[int] = []

    async def one_pass_then_shutdown(now=None):
        calls.append(1)
        shutdown.set()
        return dict(FULL_REPORT)

    monkeypatch.setattr(
        "core.policy_compiler.maturity.run_maturity_pass", one_pass_then_shutdown
    )

    await PolicyMaturityScheduler(interval_seconds=3600, enabled=True).run(shutdown)

    assert len(calls) == 1


async def test_a_failing_pass_is_logged_and_retried_not_fatal(monkeypatch):
    shutdown = asyncio.Event()
    calls: list[int] = []

    async def flaky_pass(now=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database on holiday")
        shutdown.set()
        return dict(FULL_REPORT)

    monkeypatch.setattr("core.policy_compiler.maturity.run_maturity_pass", flaky_pass)

    # A failing pass sleeps the real interval before the retry, so the test
    # needs the shortest interval the loop accepts — 3600s would outlive it.
    await PolicyMaturityScheduler(interval_seconds=1, enabled=True).run(shutdown)

    # The first failure came back around: the loop is a scheduler, and a
    # scheduler that dies on its job's first bad day is a bug that looks like
    # a policy that never rots.
    assert len(calls) == 2


async def test_cancellation_stops_the_loop_cleanly():
    scheduler = PolicyMaturityScheduler(interval_seconds=3600, enabled=False)
    shutdown = asyncio.Event()

    task = asyncio.create_task(scheduler.run(shutdown))
    await asyncio.sleep(0)  # let it enter the disabled branch's sleep
    task.cancel()

    # CancelledError is the loop's own exit, not a failure the daemon's
    # done-callback would report: run() ends without raising.
    await asyncio.wait_for(task, timeout=5)
    assert task.cancelled() or task.exception() is None


def test_the_interval_never_goes_to_zero_or_negative():
    # wait_for(timeout=0) would make the idle loop a busy loop.
    scheduler = PolicyMaturityScheduler(interval_seconds=0, enabled=False)
    assert scheduler.interval_seconds == 1


@pytest.mark.parametrize(
    "report,logged_at_info",
    [
        (dict(FULL_REPORT, shadowed=1), True),
        (dict(FULL_REPORT, suspended=1), True),
        (dict(FULL_REPORT, retired=1), True),
        (dict(FULL_REPORT), False),
        (dict(FULL_REPORT, lock_skipped=1), False),
    ],
)
async def test_state_changes_log_at_info_and_quiet_passes_do_not(
    report, logged_at_info, caplog, monkeypatch
):
    shutdown = asyncio.Event()

    async def one_pass(now=None):
        shutdown.set()
        return report

    monkeypatch.setattr("core.policy_compiler.maturity.run_maturity_pass", one_pass)

    with caplog.at_level("INFO"):
        await PolicyMaturityScheduler(interval_seconds=60, enabled=True).run(shutdown)

    info_lines = [
        r
        for r in caplog.records
        if r.levelname == "INFO" and "Policy maturity pass" in r.getMessage()
    ]
    assert bool(info_lines) == logged_at_info
