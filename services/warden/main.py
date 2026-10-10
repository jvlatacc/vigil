"""Warden's process: component orchestration and graceful shutdown.

Modeled on the SOC daemon's decomposition (task-per-component, done-callbacks
logging component death, SIGTERM/SIGINT shutdown) with the daemon's transport
assumptions stripped out: no Postgres, no Redis, no Settings — the edge
import gate (``lint-imports``, contract ``warden``) holds this file to
``core.edge`` plus the warden package. Run it as ``python -m services.warden``.

Components register through :meth:`Warden.register_component`; the metrics
server renders health from their task liveness plus what the process knows
(mode, journal, live actions) — a dead component task is a 503, because a
Warden that stopped defending should look stopped.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from core.edge.policy import PolicyPack
from core.edge.target_guard import TargetGuard
from core.edge.verify import load_root
from services.warden.config import WardenConfig
from services.warden.engine import (
    DecisionLoop,
    DryRunExecutor,
    ExecutorRegistry,
    LoopDeps,
)
from services.warden.journal import Journal
from services.warden.metrics import WardenMetrics, WardenMetricsServer
from services.warden.modes import ModeMachine
from services.warden.sentinel import Sentinel
from services.warden.storage import PolicyStore
from services.warden.sync import PolicySync

logger = logging.getLogger("services.warden")


def _default_clock() -> datetime:
    return datetime.now(UTC)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class Warden:
    """The edge process: config, components, shutdown, health."""

    def __init__(
        self,
        config: WardenConfig,
        *,
        trust_root: dict,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self.config = config
        self._trust_root = trust_root
        self._clock = clock
        self.metrics = WardenMetrics()
        self._shutdown_event = asyncio.Event()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._components: dict[str, Any] = {}
        self._mode = "BOOTSTRAP"
        self._mode_transitions: list[dict[str, str]] = []
        self._loop: DecisionLoop | None = None
        self._journal: Journal | None = None
        self._registry: ExecutorRegistry | None = None
        self._process_start = clock()
        self.metrics_server = WardenMetricsServer(
            bind_host=config.bind_host,
            health_port=config.health_port,
            metrics_port=config.metrics_port,
            metrics=self.metrics,
            health_provider=self._health_payload,
            status_provider=self._status_payload,
        )

    # ------------------------------------------------------------------
    # Component registry
    # ------------------------------------------------------------------

    def register_component(self, name: str, component: Any) -> None:
        """Adopt a component exposing ``run(shutdown_event)``.

        Called from ``run`` before tasks start; anything with side effects
        at construction belongs in its own ``run``, not here.
        """
        self._components[name] = component

    def set_mode(self, mode: str) -> None:
        """Publish a mode transition into the process status.

        The decision loop calls this on every mode change, so the status
        payload reflects the machine without the process reading loop
        internals. Repeats (the loop publishes conservatively) are
        collapsed, keeping one transition record per actual change.
        """
        if mode != self._mode:
            self._mode_transitions.append(
                {"mode": mode, "at": self._clock().isoformat()}
            )
        self._mode = mode

    def attach_decision_loop(
        self,
        loop: DecisionLoop,
        *,
        journal: Journal,
        registry: ExecutorRegistry,
    ) -> None:
        """Give the status payload its read path into loop state."""
        self._loop = loop
        self._journal = journal
        self._registry = registry

    # ------------------------------------------------------------------
    # Health and status payloads (rendered through the metrics server)
    # ------------------------------------------------------------------

    def _component_states(self) -> dict[str, str]:
        names = [*self._components.keys(), *self._tasks.keys()]
        states: dict[str, str] = {}
        for name in dict.fromkeys(names):  # dedupe, keep order
            task = self._tasks.get(name)
            if task is None:
                states[name] = "not-started"
            elif task.done():
                if task.cancelled():  # pragma: no cover - shutdown path
                    states[name] = "cancelled"
                else:
                    states[name] = "failed"
            else:
                states[name] = "running"
        return states

    def _health_payload(self) -> tuple[int, dict[str, Any]]:
        components = self._component_states()
        unhealthy = [
            name
            for name, state in components.items()
            if state in ("failed", "cancelled")
        ]
        healthy = not unhealthy
        payload = {
            "status": "healthy" if healthy else "unhealthy",
            "mode": self._mode,
            "uptime_seconds": round(
                (self._clock() - self._start_time()).total_seconds(), 3
            ),
            "components": components,
        }
        return (200 if healthy else 503, payload)

    def _start_time(self) -> datetime:
        return self._process_start

    def _status_payload(self) -> dict[str, Any]:
        status, health = self._health_payload()
        loop_status = self._loop.status() if self._loop is not None else None
        return {
            "health": health,
            "http_status": status,
            "mode": self._mode,
            "mode_transitions": self._mode_transitions,
            "node_id": self.config.node_id,
            "policy_version": loop_status["policy_version"] if loop_status else None,
            "journal": (
                self._journal.status().as_dict()
                if self._journal is not None
                else {"last_seq": 0, "head": None, "poisoned": None}
            ),
            "live_actions": loop_status["live_actions"] if loop_status else 0,
            "executors": (
                list(self._registry.registered_types())
                if self._registry is not None
                else []
            ),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Request a graceful shutdown from any thread or callback."""
        self._shutdown_event.set()

    async def run(self) -> None:
        """Start the metrics server and every registered component."""
        self._install_signal_handlers()
        self._start_component("metrics", self.metrics_server)
        for name, component in self._components.items():
            self._start_component(name, component)
        await self._shutdown_event.wait()
        await self._drain()

    def _start_component(self, name: str, component: Any) -> None:
        task = asyncio.get_running_loop().create_task(
            component.run(self._shutdown_event), name=name
        )
        self._tasks[name] = task

    async def _drain(self) -> None:
        """Cancel every component task and wait for it to finish."""
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - run() always has a loop
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:  # pragma: no cover - non-unix
                logger.warning(
                    "signal %s unsupported; shutdown is event-driven only", sig
                )


def load_trust_root(path: Path | None, *, now: datetime) -> dict:
    """Load and verify the baked-in trust root, or exit with a clear error.

    The trust root ships inside the image (the Medic pattern): without one
    no policy pack can ever verify, so refusing to start is the honest
    posture — the node could otherwise run forever believing it is merely
    partitioned.
    """
    if path is None:
        raise SystemExit(
            "warden: WARDEN_TRUST_ROOT_PATH is required — without a baked-in "
            "trust root no policy pack can verify"
        )
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"warden: cannot read trust root {path}: {exc}")
    try:
        return load_root(data, now=now)
    except ValueError as exc:
        raise SystemExit(f"warden: trust root {path} failed verification: {exc}")


def build_warden(config: WardenConfig, *, trust_root: dict) -> Warden:
    """Assemble the process from validated config: components and wiring.

    Every component shares one metrics registry and one clock. The
    decision loop publishes mode changes back into the process status;
    the journal and executor registry are attached for the same reason.
    """
    warden = Warden(config, trust_root=trust_root)
    store = PolicyStore(config.data_dir)
    journal = Journal(config.data_dir / "journal.jsonl")
    policy_sync = PolicySync(
        trust_root=trust_root,
        store=store,
        base_url=config.control_plane_url,
        enrollment_token=config.enrollment_token,
        segment_labels=config.segment_labels,
        sync_timeout_seconds=config.sync_timeout_seconds,
        clock=warden._clock,
        metrics=warden.metrics,
    )
    sentinel = Sentinel(
        bind_host=config.bind_host,
        port=config.sentinel_port,
        token=config.sentinel_token,
        max_queue=config.max_alert_queue,
        max_batch=config.max_alert_batch,
        max_body_bytes=config.max_alert_bytes,
        metrics=warden.metrics,
    )
    registry = ExecutorRegistry()
    registry.register(DryRunExecutor())

    def guard_for(pack: PolicyPack) -> TargetGuard:
        # The guard's categories come from the verified pack; the node
        # addresses come from config — never from anything alert-derived.
        return TargetGuard.from_pack(
            pack,
            self_addresses=config.self_addresses,
            gateway_addresses=config.gateway_addresses,
            control_plane_addresses=config.control_plane_addresses,
            dns_resolvers=config.dns_resolvers,
        )

    loop = DecisionLoop(
        deps=LoopDeps(
            sync=policy_sync,
            sentinel=sentinel,
            journal=journal,
            registry=registry,
            guard_provider=guard_for,
            clock=warden._clock,
            metrics=warden.metrics,
        ),
        interval_seconds=config.sync_interval_seconds,
        max_alert_batch=config.max_alert_batch,
        grace_window_seconds=config.grace_window_seconds,
        machine=ModeMachine(
            grace_window_seconds=config.grace_window_seconds,
            missed_syncs_threshold=config.missed_syncs_threshold,
        ),
        mode_observer=warden.set_mode,
    )
    warden.attach_decision_loop(loop, journal=journal, registry=registry)
    warden.register_component("loop", loop)
    warden.register_component("sentinel", sentinel)
    return warden


def main(argv: list[str] | None = None) -> int:
    """Build the process from the environment and run it until signalled."""
    del argv  # no flags yet: the environment is the config channel
    configure_logging("INFO")
    try:
        config = WardenConfig.from_env()
    except ValueError as exc:
        print(f"warden: invalid configuration: {exc}", file=sys.stderr)
        return 2
    problems = config.validate()
    if problems:
        for problem in problems:
            print(f"warden: {problem}", file=sys.stderr)
        return 2
    try:
        trust_root = load_trust_root(config.trust_root_path, now=_default_clock())
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    warden = build_warden(config, trust_root=trust_root)
    logger.info("warden starting (data %s, node %s)", config.data_dir, config.node_id)
    asyncio.run(warden.run())
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
