"""TTL reaper tests: the work queue is the journal, not memory.

The acceptance bar (design spec, executor suites): the reaper reverts on
schedule and journals the revert; a failed revert is a journaled error,
never a silent leak. The restart test is the point of the design — the
queue is derived from durable journal history, so a daemon that dies
mid-TTL still reaps the block after reboot.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.edge.executors.registry import ActionResult, ExecutorRegistry
from services.edge.gate.gate import Action
from services.edge.journal.journal import KIND_DECISION, KIND_REVERT, HashJournal
from services.edge.reaper import REAPER_ACTOR, TtlReaper

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


class FakeExecutor:
    """Revert-call recorder with optional failure — the only surface the
    reaper touches."""

    name = "nftables"
    action_types = frozenset({"block_ip", "block_domain"})

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.reverted: list[str] = []

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:  # pragma: no cover
        raise AssertionError("the reaper never applies")

    async def revert(self, ref: str) -> ActionResult:
        self.reverted.append(ref)
        if self.fail:
            return ActionResult(success=False, error="nft_error:1:boom")
        return ActionResult(success=True, ref=ref)


def executed_decision_payload(
    *, executor: str = "nftables", ref: str = "blk_abc123", ttl: int = 900
) -> dict:
    """The decision payload shape the daemon writes for a successful
    executor apply (see app/daemon.py)."""
    return {
        "outcome": "execute",
        "action": {
            "action_type": "block_ip",
            "executor": executor,
            "target": "203.0.113.55",
            "ttl_seconds": ttl,
        },
        "execution": {"success": True, "ref": ref, "error": None},
    }


def make_journal(tmp_path: Path) -> HashJournal:
    return HashJournal(
        tmp_path / "edge-data", node_id="node-1", boot_id=uuid.uuid4().hex
    )


def journal_expired_block(
    journal: HashJournal,
    *,
    when: datetime,
    ttl: int = 900,
    executor: str = "nftables",
    ref: str = "blk_abc123",
) -> int:
    record = journal.append(
        KIND_DECISION,
        executed_decision_payload(executor=executor, ref=ref, ttl=ttl),
        now=when,
    )
    return record.local_sequence


def test_expired_block_is_reverted_and_journaled(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    seq = journal_expired_block(journal, when=NOW, ttl=900)
    executor = FakeExecutor()
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry)

    appended = asyncio.run(reaper.sweep(now=NOW + timedelta(seconds=1000)))

    assert appended == 1
    assert executor.reverted == ["blk_abc123"]
    reverts = [r for r in journal.unacked() if r.kind == KIND_REVERT]
    assert len(reverts) == 1
    payload = reverts[0].payload
    assert payload["revert_of"] == seq
    assert payload["success"] is True
    assert payload["actor"] == REAPER_ACTOR


def test_unexpired_block_is_left_alone(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal_expired_block(journal, when=NOW, ttl=900)
    executor = FakeExecutor()
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry)

    appended = asyncio.run(reaper.sweep(now=NOW + timedelta(seconds=100)))

    assert appended == 0
    assert executor.reverted == []


def test_successful_revert_closes_the_work(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal_expired_block(journal, when=NOW, ttl=900)
    executor = FakeExecutor()
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry)
    moment = NOW + timedelta(seconds=1000)

    asyncio.run(reaper.sweep(now=moment))
    appended = asyncio.run(reaper.sweep(now=moment))

    assert appended == 0
    assert executor.reverted == ["blk_abc123"]  # not reverted twice


def test_failed_revert_is_journaled_and_retried(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal_expired_block(journal, when=NOW, ttl=900)
    executor = FakeExecutor(fail=True)
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry)
    moment = NOW + timedelta(seconds=1000)

    appended = asyncio.run(reaper.sweep(now=moment))

    assert appended == 1
    reverts = [r for r in journal.unacked() if r.kind == KIND_REVERT]
    assert len(reverts) == 1
    assert reverts[0].payload["success"] is False
    assert "nft_error:1" in reverts[0].payload["error"]

    # The failed revert stays pending: the next sweep retries it. A
    # dropped or swallowed failure here is the silent leak the spec bans.
    appended = asyncio.run(reaper.sweep(now=moment + timedelta(minutes=1)))
    assert appended == 1
    assert executor.reverted == ["blk_abc123", "blk_abc123"]


def test_missing_executor_journals_the_failure(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal_expired_block(journal, when=NOW, ttl=900)
    reaper = TtlReaper(journal, ExecutorRegistry())  # nothing registered

    appended = asyncio.run(reaper.sweep(now=NOW + timedelta(seconds=1000)))

    assert appended == 1
    reverts = [r for r in journal.unacked() if r.kind == KIND_REVERT]
    assert len(reverts) == 1
    assert reverts[0].payload["success"] is False
    assert reverts[0].payload["error"] == "no_executor_registered"


def test_queue_survives_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "edge-data"
    boot = HashJournal(data_dir, node_id="node-1", boot_id="boot-1")
    journal_expired_block(boot, when=NOW, ttl=900)

    # A fresh process: new journal over the same directory, new registry.
    journal = HashJournal(data_dir, node_id="node-1", boot_id="boot-2")
    executor = FakeExecutor()
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry)

    appended = asyncio.run(reaper.sweep(now=NOW + timedelta(seconds=1000)))

    assert appended == 1
    assert executor.reverted == ["blk_abc123"]  # the old block was reaped


def test_run_forever_sweeps_until_cancelled(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    journal_expired_block(journal, when=NOW, ttl=900)
    executor = FakeExecutor()
    registry = ExecutorRegistry()
    registry.register(executor)
    reaper = TtlReaper(journal, registry, interval_seconds=0.01)

    async def scenario() -> None:
        task = asyncio.create_task(reaper.run_forever())
        for _ in range(500):  # bounded wait for the first sweep
            if executor.reverted:
                break
            await asyncio.sleep(0.005)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert executor.reverted == ["blk_abc123"]
