"""TTL reaper: reverts expired containment and journals every outcome.

The work queue is never held in memory — it is derived from the
hash-chained journal on every sweep (`Journal.pending_reverts`). That
is the whole durability story: a daemon that dies mid-TTL reaps the
block after restart, because the journal still says the block exists.

Every outcome is journaled — a failed revert appends a failed revert
record and the work stays pending for the next sweep. A silent leak
(reverted-in-memory-only, or failure swallowed) would leave the
operator's drift report describing a world that is not the real one.

Runs as its own asyncio task; the daemon's shutdown event cancels it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from services.edge.executors.registry import ExecutorRegistry
from services.edge.journal.journal import KIND_REVERT, HashJournal

logger = logging.getLogger(__name__)

#: The actor on every reaper-driven revert. House rule (R§2): a decision
#: always names who made it — the reaper is not a confidence score.
REAPER_ACTOR = "edge:ttl-reaper"


class TtlReaper:
    """Periodic sweep over the journal's expired-but-unreverted blocks."""

    def __init__(
        self,
        journal: HashJournal,
        registry: ExecutorRegistry,
        *,
        interval_seconds: float = 60.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._journal = journal
        self._registry = registry
        self._interval = interval_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    async def sweep(self, *, now: datetime | None = None) -> int:
        """One pass: revert every expired, unreverted block. Returns the
        number of revert records appended (successes and failures — both
        are news)."""
        moment = now or self._clock()
        appended = 0
        for record, payload in self._journal.pending_reverts(moment):
            action = payload.get("action") or {}
            execution = payload.get("execution") or {}
            executor_name = str(action.get("executor") or "")
            action_type = str(action.get("action_type") or "")
            ref = str(execution.get("ref") or "")
            executor = self._registry.lookup(action_type, executor_name)
            if executor is None:
                # No executor to do the revert: journal the failure so the
                # drift report shows a block that outlived its TTL.
                self._journal.append(
                    KIND_REVERT,
                    {
                        "revert_of": record.local_sequence,
                        "success": False,
                        "ref": ref,
                        "error": "no_executor_registered",
                        "executor": executor_name,
                        "target": action.get("target"),
                        "actor": REAPER_ACTOR,
                    },
                )
                appended += 1
                logger.error(
                    "reaper: no executor registered for %s; %s outlives its TTL",
                    executor_name,
                    ref,
                )
                continue
            result = await executor.revert(ref)
            self._journal.append(
                KIND_REVERT,
                {
                    "revert_of": record.local_sequence,
                    "success": result.success,
                    "ref": ref,
                    "error": result.error,
                    "executor": executor_name,
                    "target": action.get("target"),
                    "actor": REAPER_ACTOR,
                },
            )
            appended += 1
            if result.success:
                logger.info("reaper: reverted expired %s block %s", executor_name, ref)
            else:
                # Journaled error, retried next sweep — never a silent leak.
                logger.error(
                    "reaper: revert failed for %s (%s); will retry",
                    ref,
                    result.error,
                )
        return appended

    async def run_forever(self) -> None:
        """Sweep on the interval until cancelled. Cancellation is the
        daemon's shutdown path, not an error."""
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad sweep must not kill the loop that un-leaks the
                # ruleset; the failure stays visible in the logs and the
                # work stays pending in the journal.
                logger.exception("reaper: sweep failed; retrying on interval")
            await asyncio.sleep(self._interval)
