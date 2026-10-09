"""The edge daemon: one asyncio process, one main loop, lazy components."""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from services.edge.app.health import HealthServer
from services.edge.app.states import OperatingState, StateTracker
from services.edge.gate.gate import Decision, Outcome, decide
from services.edge.journal.journal import (
    KIND_DECISION,
    KIND_EXECUTE_FAILED,
    KIND_OBSERVATION,
    KIND_STATE,
)

if TYPE_CHECKING:
    from services.edge.app.config import EdgeConfig
    from services.edge.observations.base import Observation, ObservationInput

logger = logging.getLogger(__name__)


def observation_payload(observation: Observation) -> dict[str, Any]:
    """The observation fields a journal record cites: digest + reference for
    evidence, the normalized fields the analyst needs."""
    return {
        "raw_digest": observation.raw_digest,
        "raw_ref": observation.raw_ref,
        "direction": observation.direction,
        "src_ip": observation.src_ip,
        "dest_ip": observation.dest_ip,
        "dest_domain": observation.dest_domain,
        "event_type": observation.event_type,
    }


def decision_payload(
    decision: Decision,
    observation: Observation,
    bundle_version: int,
    *,
    execution: dict[str, Any] | None,
) -> dict[str, Any]:
    """The journal's decision-record contract — the reconciliation client
    uploads these verbatim; the gate's caps view reads them back."""
    action = decision.action
    return {
        "outcome": decision.outcome.value,
        "rule_string": decision.rule_string,
        "reason": decision.reason,
        "actor": decision.actor,
        "confidence": decision.confidence,
        "bundle_version": bundle_version,
        "action": (
            None
            if action is None
            else {
                "action_type": action.action_type,
                "executor": action.executor,
                "target": action.target,
                "ttl_seconds": action.ttl_seconds,
            }
        ),
        "execution": execution,
        "observation": observation_payload(observation),
    }


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
        way the central daemon defers its imports."""
        from services.edge.executors.registry import ExecutorRegistry
        from services.edge.gate.advisor import AdvisorConfig, SlmAdvisor
        from services.edge.journal.journal import HashJournal
        from services.edge.observations.file_tail import FileTail
        from services.edge.policy.cache import BundleCache
        from services.edge.policy.envelope import load_trust_root

        config = self.config
        self._journal = HashJournal(
            config.data_dir,
            node_id=config.node_id,
            boot_id=self._boot_id,
            max_bytes=config.journal_max_bytes,
        )
        self._cache = BundleCache(
            config.data_dir / "policy",
            load_trust_root(config.trust_store),
            node_labels=config.node_labels,
            edge_version=config.edge_version,
        )
        restored = self._cache.load_persisted(now=datetime.now(UTC))
        logger.info(
            "bundle cache restored: current=%s previous=%s",
            restored.current is not None,
            restored.previous is not None,
        )
        self._executors = ExecutorRegistry()
        self._advisor = None
        if config.model is not None and config.model.strip():
            self._advisor = SlmAdvisor(
                AdvisorConfig(base_url=config.model_url, model=config.model),
                model_digest=config.model_digest,
            )
        # Direction inference uses the active bundle's scope CIDRs (the
        # signed segment definition); the sync client rebuilds the tail when
        # it activates a new bundle. Without a bundle the tail reports
        # direction "unknown" — IOC rules still match, direction-keyed ones
        # simply do not fire until a bundle is active.
        self._inputs: list[ObservationInput] = []
        if config.eve_path is not None:
            bundle = self._cache.current
            home = bundle.segment_scope.cidrs if bundle is not None else ()
            self._inputs.append(
                FileTail(config.eve_path, home_cidrs=home, state_dir=config.data_dir)
            )

    async def run(self) -> None:
        """Run until SIGTERM/SIGINT. Partition changes what the daemon may
        do, never whether it runs."""
        self._init_components()
        self._record_state(OperatingState.PARTITIONED, reason="boot")
        self._setup_signal_handlers()

        server = HealthServer(
            port=self.config.health_port,
            state_fn=lambda: self._states.state.value,
            tier_fn=self._tier_fn,
            node_id=self.config.node_id,
            data_dir=self.config.data_dir,
        )

        loop = asyncio.get_running_loop()
        tasks: list[asyncio.Task] = [loop.create_task(server.serve(), name="health")]
        for source in self._inputs:
            tasks.append(
                loop.create_task(
                    source.run(self.handle_observation), name=f"input:{source.name}"
                )
            )
        logger.info("Edge daemon running: %d task(s)", len(tasks))
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
        self._journal.append(
            KIND_STATE, {"from": old.value, "to": to.value, "reason": reason}
        )
        logger.info("Operating state: %s -> %s (%s)", old.value, to.value, reason)

    def _tier_fn(self) -> str:
        from services.edge.gate.tiers import tier_label  # lazy: gate machinery

        return tier_label(self._cache.effective_tier(datetime.now(UTC)))

    # -- the defense loop ---------------------------------------------------

    async def handle_observation(
        self, observation: Observation, *, now: datetime | None = None
    ) -> None:
        """One observation through the whole loop: gate -> journal ->
        executor dispatch. The journal is the caps authority (the gate reads
        caps from it); the advisor runs in a worker thread and its verdict
        may only refine confidence — the gate enforces that."""
        bundle = self._cache.current
        if bundle is None:
            self._journal.append(
                KIND_OBSERVATION,
                observation_payload(observation) | {"reason": "no_bundle"},
            )
            return
        rule = bundle.match(observation)
        verdict = None
        if self._advisor is not None:
            verdict = await asyncio.to_thread(self._advisor.classify, observation, rule)
        decision = decide(
            observation,
            bundle,
            verdict,
            caps=self._journal,
            node_id=self.config.node_id,
            now=now,
        )
        if decision.outcome is Outcome.EXECUTE and decision.action is not None:
            action = decision.action
            executor = self._executors.lookup(action.action_type, action.executor)
            if executor is None:
                # Recorded, never faked — the house precedent of the central
                # pipeline's isolate_host stub.
                self._journal.append(
                    KIND_EXECUTE_FAILED,
                    {
                        "reason": "no_executor_registered",
                        "action_type": action.action_type,
                        "executor": action.executor,
                        "target": action.target,
                        "rule_string": decision.rule_string,
                        "actor": decision.actor,
                    },
                )
                logger.error(
                    "no executor registered for (%s, %s): containment NOT applied",
                    action.action_type,
                    action.executor,
                )
                return
            result = await executor.apply(action, action.ttl_seconds)
            self._journal.append(
                KIND_DECISION,
                decision_payload(
                    decision,
                    observation,
                    bundle.version,
                    execution={
                        "success": result.success,
                        "ref": result.ref,
                        "error": result.error,
                    },
                ),
            )
            if not result.success:
                logger.error(
                    "executor %s failed to apply %s to %s: %s",
                    action.executor,
                    action.action_type,
                    action.target,
                    result.error,
                )
            return
        self._journal.append(
            KIND_DECISION,
            decision_payload(decision, observation, bundle.version, execution=None),
        )
