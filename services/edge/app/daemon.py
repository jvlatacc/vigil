"""The edge daemon: one asyncio process, one main loop, lazy components."""

from __future__ import annotations

import asyncio
import contextlib
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
    KIND_OFFLINE_WINDOW,
    KIND_STATE,
    JournalRecord,
)
from services.edge.sync.drift import build_drift_report

if TYPE_CHECKING:
    from services.edge.app.config import EdgeConfig
    from services.edge.observations.base import Observation, ObservationInput
    from services.edge.policy.model import Bundle

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
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The journal's decision-record contract — the reconciliation client
    uploads these verbatim; the gate's caps view reads them back. ``model``
    names the advisor that refined the confidence (id + pinned digest), the
    drift report's "model version" per decision."""
    action = decision.action
    return {
        "outcome": decision.outcome.value,
        "rule_string": decision.rule_string,
        "reason": decision.reason,
        "actor": decision.actor,
        "confidence": decision.confidence,
        "bundle_version": bundle_version,
        "model": model,
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
        # Open offline window: set on entry to PARTITIONED, closed (with the
        # drift report) on reconciliation. None = no window in progress.
        self._offline_window: dict[str, Any] | None = None
        self._window_records: list[JournalRecord] = []
        self._input_tasks: dict[str, asyncio.Task] = {}

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
        from services.edge.reaper import TtlReaper

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
        self._wire_executors(config)
        self._reaper = TtlReaper(
            self._journal,
            self._executors,
            interval_seconds=config.reaper_interval_seconds,
        )
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

        # Sync machinery. Enrollment is deliberately lazy — the first sync
        # cycle exchanges the token, so a control plane that is down at boot
        # delays enrollment instead of failing it.
        from services.edge.sync.client import SyncClient, SyncSurface
        from services.edge.sync.reconciler import Reconciler

        self._client: SyncSurface = SyncClient(
            control_url=config.control_url,
            node_id=config.node_id,
            credential_file=config.credential_file,
            timeout_seconds=config.sync_timeout_seconds,
        )
        self._reconciler = Reconciler(
            self._client,
            self._journal,
            batch_size=config.sync_batch_size,
        )
        # Backoff schedule inputs: consecutive failed cycles (reset on
        # success) drive next_delay's exponential window.
        self._failed_attempts = 0

    def _wire_executors(self, config: EdgeConfig) -> None:
        """Register the deployment mode's executors under the bundle-bound
        wrapper: every apply rechecks the live signed bundle, so a revoked
        or swapped bundle stops authorizing new containment immediately
        while undoing a block stays always-permitted."""
        from services.edge.executors.k8s_networkpolicy import (
            K8sExecutorConfig,
            K8sNetworkPolicyExecutor,
        )
        from services.edge.executors.nftables import NftablesExecutor, run_command
        from services.edge.executors.registry import BundleBound

        def bundle_fn() -> Bundle | None:
            return self._cache.current

        if config.mode == "gateway":
            self._executors.register(
                BundleBound(NftablesExecutor("nftables", run_command), bundle_fn)
            )
        else:  # cluster mode: the API server + service-account mount
            self._executors.register(
                BundleBound(
                    K8sNetworkPolicyExecutor(
                        K8sExecutorConfig(
                            api_url=config.k8s_api_url or "",
                            token_file=config.k8s_token_file,
                            ca_file=config.k8s_ca_file,
                        )
                    ),
                    bundle_fn,
                )
            )

    async def run(self) -> None:
        """Run until SIGTERM/SIGINT. Partition changes what the daemon may
        do, never whether it runs."""
        self._init_components()
        self._record_state(OperatingState.PARTITIONED, reason="boot")
        self._open_window("boot")
        self._setup_signal_handlers()

        server = HealthServer(
            port=self.config.health_port,
            state_fn=lambda: self._states.state.value,
            tier_fn=self._tier_fn,
            node_id=self.config.node_id,
            data_dir=self.config.data_dir,
        )

        loop = asyncio.get_running_loop()
        tasks: list[asyncio.Task] = [
            loop.create_task(server.serve(), name="health"),
            loop.create_task(self._sync_loop(), name="sync"),
        ]
        for source in self._inputs:
            name = f"input:{source.name}"
            self._input_tasks[name] = loop.create_task(
                source.run(self.handle_observation), name=name
            )
        tasks.append(loop.create_task(self._reaper.run_forever(), name="ttl-reaper"))
        tasks.extend(self._input_tasks.values())
        logger.info("Edge daemon running: %d task(s)", len(tasks))
        await self._shutdown_event.wait()

        logger.info("Edge daemon shutting down")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server.stop()
        await self._client.aclose()

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

    # -- the sync loop -------------------------------------------------------

    def _model_meta(self) -> dict[str, Any] | None:
        """The advisor identity for decision records (drift report's model
        version), or None when no advisor is configured."""
        if self._advisor is None:
            return None
        return {
            "id": self.config.model,
            "digest": self.config.model_digest or None,
        }

    def _bundle_version(self) -> int | None:
        bundle = self._cache.current
        return bundle.version if bundle is not None else None

    def _lease_state(self) -> str:
        # ≤32 chars (the heartbeat contract): the count of blocks the node
        # currently holds is the lease state that matters for drift.
        return f"blocks:{self._journal.active_blocks(datetime.now(UTC))}"

    async def _sync_loop(self) -> None:
        """One cycle per interval; failures back off with equal jitter.
        Pull-based per node — the control plane never fans out, so a fleet
        reconnecting after a mass outage cannot storm it (design spec)."""
        from services.edge.sync.backoff import next_delay
        from services.edge.sync.client import SyncError

        interval = self.config.sync_interval_seconds
        while not self._shutdown_event.is_set():
            try:
                await self._sync_cycle()
                self._failed_attempts = 0
                delay = interval
            except SyncError as exc:
                self._failed_attempts += 1
                delay = next_delay(
                    self._failed_attempts - 1,
                    base_seconds=min(2.0, interval),
                    max_seconds=max(interval, 300.0),
                )
                logger.warning("sync cycle failed (%s); retrying in %.1fs", exc, delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)

    async def _sync_cycle(self) -> None:
        """Heartbeat -> policy refresh -> reconciliation, with the state
        machine and offline window handled here so the pacing loop owns
        only timing. SyncError propagates to the loop's backoff."""
        from services.edge.sync.client import SyncError

        try:
            await self._ensure_enrolled()
            heartbeat = await self._client.heartbeat(
                boot_id=self._boot_id,
                bundle_version=self._bundle_version(),
                autonomy_tier=self._tier_fn(),
                lease_state=self._lease_state(),
                acked_upto=self._journal.acked_upto or None,
            )
        except SyncError as exc:
            self._sync_failed(f"heartbeat: {exc}")
            raise
        if heartbeat.get("revoked"):
            self._revoked()
            return
        # Spec's reconciliation order: upload bounded batches first, then
        # refresh policy, then the drift report (delivered by _sync_ok's
        # window close) — a revoked bundle must not gate the import of
        # actions already taken offline.
        try:
            drained = await self._reconciler.reconcile()
        except SyncError as exc:
            self._sync_failed(f"reconcile: {exc}")
            raise
        await self._refresh_policy(heartbeat)
        self._sync_ok(drained)

    async def _ensure_enrolled(self) -> None:
        """Adopt the persisted credential, or exchange the one-time token.
        No credential and no token is a logged sync failure, never a crash —
        the operator may drop a token in later."""
        from services.edge.app.config import ENROLLMENT_TOKEN_VAR
        from services.edge.sync.client import SyncError

        if self._client.credential or self._client.load_credential():
            return
        token = self.config.enrollment_token
        if not token:
            raise SyncError(
                f"no credential at {self.config.credential_file} and "
                f"{ENROLLMENT_TOKEN_VAR} unset: cannot authenticate"
            )
        await self._client.enroll(token, dict(self.config.segment_scope))

    async def _refresh_policy(self, heartbeat: dict) -> None:
        """Pull and (maybe) activate the newest bundle. Newest valid wins;
        an expired bundle is never extended locally (conflict precedence):
        only a new verified signature restores autonomy."""
        cursor = self._bundle_version()
        response = await self._client.pull_policy(cursor)
        # The route returns {"bundle": {bundle_id, version, autonomy_tier,
        # envelope}, "payload": ..., "current_version": ...} — the edge
        # verifies the DSSE envelope itself, never trusting the transport.
        row = response.get("bundle")
        envelope = row.get("envelope") if isinstance(row, dict) else None
        if envelope is not None:
            verification = self._cache.verify_and_activate(
                envelope, now=datetime.now(UTC)
            )
            if verification.accepted:
                await self._rebuild_inputs()
                if self._states.state is OperatingState.DEGRADED:
                    # Tier restored by signature, not by clock — the
                    # DEGRADED exit the spec allows exactly once per bundle.
                    self._record_state(OperatingState.SYNCED, reason="bundle_verified")
            else:
                logger.info(
                    "bundle refresh refused (%s): %s — keeping last-known-good",
                    verification.code,
                    verification.detail,
                )
        self._check_degraded()

    def _check_degraded(self) -> None:
        """An expired active bundle is DEGRADED from any state — the clock
        may demote autonomy, never promote it. A node that never had a
        bundle is the Tier-0 floor, not degradation."""
        bundle = self._cache.current
        if (
            bundle is not None
            and bundle.expires_at <= datetime.now(UTC)
            and self._states.state is not OperatingState.DEGRADED
        ):
            self._record_state(OperatingState.DEGRADED, reason="bundle_expired")

    async def _rebuild_inputs(self) -> None:
        """Restart observation inputs against the new bundle's scope: the
        FileTail's home CIDRs come from the signed segment definition."""
        from services.edge.observations.file_tail import FileTail

        if self.config.eve_path is None or not self._input_tasks:
            return
        loop = asyncio.get_running_loop()
        stale = list(self._input_tasks.values())
        bundle = self._cache.current
        home = bundle.segment_scope.cidrs if bundle is not None else ()
        self._inputs = [
            FileTail(
                self.config.eve_path, home_cidrs=home, state_dir=self.config.data_dir
            )
        ]
        for task in stale:
            task.cancel()
        await asyncio.gather(*stale, return_exceptions=True)
        for source in self._inputs:
            name = f"input:{source.name}"
            self._input_tasks[name] = loop.create_task(
                source.run(self.handle_observation), name=name
            )
        logger.info("observation inputs rebuilt against the active bundle scope")

    def _revoked(self) -> None:
        """Revocation beats allowance: the credential is dead server-side,
        so sync is over — and enforcement drops to the Tier-0 floor now,
        not on the next failed sync. No transition leaves this state
        except a fresh credential (re-enrollment is a human act)."""
        logger.error(
            "node %s revoked by the control plane: autonomy revoked, observing only",
            self.config.node_id,
        )
        # The state machine alone does not gate actions — the bundle tier
        # does. Withdraw the cached bundle so the tier-0 floor holds now and
        # after any restart (revocation beats allowance, conflict precedence).
        self._cache.revoke(now=datetime.now(UTC))
        self._record_state(OperatingState.DEGRADED, reason="node_revoked")

    def _sync_failed(self, reason: str) -> None:
        state = self._states.state
        if state in (OperatingState.SYNCED, OperatingState.RECONCILING):
            self._enter_partitioned(reason)
            return
        # PARTITIONED stays (already the state); DEGRADED stays — its cause
        # is the bundle, not the link. But the offline window opens on any
        # sync failure, boot included: a node that boots disconnected still
        # accumulates evidence that must reconcile as one unit later.
        self._open_window(reason)

    def _enter_partitioned(self, reason: str) -> None:
        # Window first, state second: the partitioned transition itself is
        # inside the window, so the closure report's timeline shows it.
        self._open_window(reason)
        self._record_state(OperatingState.PARTITIONED, reason=reason)

    def _sync_ok(self, drained: bool) -> None:
        state = self._states.state
        if drained:
            if state in (OperatingState.RECONCILING, OperatingState.PARTITIONED):
                self._close_window()
                self._record_state(
                    OperatingState.SYNCED,
                    reason=(
                        "reconciled"
                        if state is OperatingState.RECONCILING
                        else "reconnected"
                    ),
                )
            # SYNCED stays SYNCED; DEGRADED waits for a verified bundle.
        elif state is OperatingState.PARTITIONED:
            # Link restored but the journal is not drained yet: the
            # reconciliation state the spec names, enforced limits active.
            self._record_state(OperatingState.RECONCILING, reason="link_restored")

    def _open_window(self, reason: str) -> None:
        """Open the offline window that brackets everything this partition
        journals — one closure record, not a per-event special case. Records
        are snapshotted as they land (on_append), because compaction drops
        the acked prefix from the journal itself."""
        if self._offline_window is not None:
            return
        self._window_records = []
        self._journal.on_append = self._window_records.append
        now = datetime.now(UTC).isoformat()
        record = self._journal.append(
            KIND_OFFLINE_WINDOW,
            {"phase": "open", "opened_at": now, "reason": reason},
        )
        self._offline_window = {
            "opened_at": now,
            "open_seq": record.local_sequence,
            "reason": reason,
        }

    def _close_window(self) -> None:
        """Close the window: build the drift report from the window's
        journal records, log it for the operator, and append the closure
        record — uploaded as the offline-window's final event, closing the
        interval so analysts can filter the partition as one unit."""
        window = self._offline_window
        if window is None:
            return
        self._journal.on_append = None
        records = self._window_records
        self._window_records = []
        closed_at = datetime.now(UTC)
        report = build_drift_report(
            records,
            node_id=self.config.node_id,
            boot_id=self._boot_id,
            opened_at=window["opened_at"],
            closed_at=closed_at.isoformat(),
            loss_counters=self._journal.loss_counters,
            evicted_ranges=self._journal.evicted_ranges,
            rejected_events=self._journal.rejected,
        )
        for line in report.to_lines():
            logger.info(line)
        self._journal.append(KIND_OFFLINE_WINDOW, report.to_payload())
        self._offline_window = None

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
                    model=self._model_meta(),
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
            decision_payload(
                decision,
                observation,
                bundle.version,
                execution=None,
                model=self._model_meta(),
            ),
        )
