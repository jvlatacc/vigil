"""The edge daemon: one asyncio process, one main loop, lazy components."""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from typing import TYPE_CHECKING

from services.edge.app.health import HealthServer
from services.edge.app.states import OperatingState, StateTracker

if TYPE_CHECKING:
    from services.edge.app.config import EdgeConfig

logger = logging.getLogger(__name__)


class EdgeDaemon:
    """The defense loop that runs when the control plane cannot be reached.

    Mirrors the SOCDaemon shape (services/daemon/main.py): the constructor
    takes the config, components are built in ``_init_components`` at run
    time — imports live inside that method, not at module top — and ``run``
    joins every task on one shutdown event. Durable state is on disk (the
    journal and the policy cache own it); the process holds none, so a
    DaemonSet slot can host it.
    """

    def __init__(self, config: EdgeConfig) -> None:
        self.config = config
        self._states = StateTracker()
        self._shutdown_event = asyncio.Event()
        self._boot_id = uuid.uuid4().hex

        logger.info(
            "Edge daemon initialized: node=%s mode=%s version=%s",
            config.node_id,
            config.mode,
            config.edge_version,
        )

    def _init_components(self) -> None:
        """Build the defense loop's parts. Imports are local so a broken
        optional component cannot stop the process from starting, the same
        way the central daemon defers its imports. Components land with
        their deliverables: journal and policy cache (bundle/cache), the
        gate and advisor (decision gate), executors, observation inputs."""

    async def run(self) -> None:
        """Run until SIGTERM/SIGINT. Partition changes what the daemon may
        do, never whether it runs."""
        self._init_components()
        self._record_state(OperatingState.PARTITIONED, reason="boot")
        self._setup_signal_handlers()

        server = HealthServer(
            port=self.config.health_port,
            state_fn=lambda: self._states.state.value,
            tier_fn=lambda: "tier0",
            node_id=self.config.node_id,
            data_dir=self.config.data_dir,
        )

        loop = asyncio.get_running_loop()
        tasks: list[asyncio.Task] = [loop.create_task(server.serve(), name="health")]
        logger.info("Edge daemon running: %s task(s)", len(tasks))
        await self._shutdown_event.wait()

        logger.info("Edge daemon shutting down")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server.stop()

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

    def _handle_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    def _record_state(self, to: OperatingState, *, reason: str) -> None:
        old = self._states.state
        if old is to:
            return
        self._states.transition(to)
        # Journaling of transitions arrives with the journal deliverable.
        logger.info("Operating state: %s -> %s (%s)", old.value, to.value, reason)
