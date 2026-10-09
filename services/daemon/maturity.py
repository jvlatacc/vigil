"""Daemon-scheduled policy maturity pass (docs/adr/0001).

Its own component rather than a tick inside another loop: the maturity pass
compiles, suspends, and retires — decisions about what may be trusted — while
the orchestrator's loops supervise live investigations and turn finished ones
into memory. Different evidence, different failure modes, different interval.

Single-flight is the DB advisory lock inside the pass, not this scheduler:
two daemons (or a restart overlapping a running pass) are safe by lock, not
by luck. When the fast path is off this loop stays alive but idle, so /health
keeps describing a real task.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class PolicyMaturityScheduler:
    """Runs the maturity pass on an interval for the life of the daemon."""

    def __init__(self, interval_seconds: int = 900, enabled: bool = False):
        self.interval_seconds = max(1, interval_seconds)
        self.enabled = enabled

    async def run(self, shutdown_event: asyncio.Event):
        from core.policy_compiler.maturity import run_maturity_pass

        logger.info(
            "Policy maturity scheduler started (interval=%ss, enabled=%s)",
            self.interval_seconds,
            self.enabled,
        )
        while not shutdown_event.is_set():
            try:
                if not self.enabled:
                    await self._sleep(shutdown_event, 10)
                    continue

                report = await run_maturity_pass()

                # State changes are console-visible events; a pass that only
                # found nothing new is the common case and stays quiet.
                if any(report[k] for k in ("shadowed", "suspended", "retired")):
                    logger.info("Policy maturity pass: %s", report)
                elif report.get("lock_skipped"):
                    # Normal contention with another instance — the lock did
                    # its job; worth a line only when debugging timing.
                    logger.debug("Policy maturity pass skipped (lock held): %s", report)
                else:
                    logger.debug("Policy maturity pass: %s", report)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Logged and retried rather than swallowed into a quiet stop:
                # a pass that dies silently leaves drift counters unwatched,
                # and an unwatched counter reads as a policy working when it
                # is rotting.
                logger.error("Policy maturity pass error: %s", e, exc_info=True)

            await self._sleep(shutdown_event, self.interval_seconds)

    @staticmethod
    async def _sleep(shutdown_event: asyncio.Event, seconds: int):
        """Sleep that respects shutdown events."""
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
        except TimeoutError:
            pass
