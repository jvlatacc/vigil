"""Metrics collection for daemon operations.

MetricsServer runs two listeners: health JSON (/health, /status) on
DAEMON_HEALTH_PORT (default 9091), and Prometheus text on
DAEMON_METRICS_PORT (default 9090) at /metrics. The Prometheus listener
renders prometheus_client's default REGISTRY, which is where the OTEL
PrometheusMetricReader from core/telemetry.init_telemetry() registers its
collector — so the OTEL instruments appear there when the flag is on.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, Optional

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.config import get_settings
from core.telemetry import get_meter
from core.time import utcnow
from services.daemon.config import MetricsConfig
from services.daemon.vendor_errors import vendor_error_snapshot

logger = logging.getLogger(__name__)

DAEMON_HEALTH_PORT = get_settings().daemon_health_port
DAEMON_METRICS_PORT = get_settings().daemon_metrics_port


# ---------------------------------------------------------------------------
# ProbeMetrics — known-answer probe scores (#924)
# ---------------------------------------------------------------------------


class ProbeMetrics:
    """The two probe instruments.

    Instruments are created on first record rather than at import, so they
    bind to the real meter once ``init_telemetry`` has run and to the no-op
    one when it has not. These names are what the Grafana twin and the
    health screen (#887) query; they are not aliased to ``soc_daemon_*``.
    """

    def __init__(self):
        self._results_counter = None
        self._time_to_verdict_hist = None
        self._instruments_ready = False
        # In-memory shadow, keyed (probe, outcome).
        self.results: dict[tuple, int] = defaultdict(int)

    def _ensure_instruments(self):
        if self._instruments_ready:
            return
        self._instruments_ready = True
        try:
            meter = get_meter("vigil.daemon")
            self._results_counter = meter.create_counter(
                name="vigil.probe.results.total",
                description="Known-answer probe scores by probe and outcome",
                unit="1",
            )
            self._time_to_verdict_hist = meter.create_histogram(
                name="vigil.probe.time_to_verdict.seconds",
                description="Seconds from probe creation to daemon triage verdict",
                unit="s",
            )
        except Exception as _err:
            logger.debug("OTEL probe instruments unavailable: %s", _err)

    def record(self, probe: str, outcome: str, time_to_verdict_s: float | None):
        """Count one score; the histogram only sees hit/miss (a verdict exists)."""
        self.results[(probe, outcome)] += 1
        self._ensure_instruments()
        try:
            if self._results_counter is not None:
                self._results_counter.add(1, {"probe": probe, "outcome": outcome})
            if time_to_verdict_s is not None and self._time_to_verdict_hist is not None:
                self._time_to_verdict_hist.record(time_to_verdict_s, {"probe": probe})
        except Exception as _err:
            logger.debug("OTEL probe record failed (non-fatal): %s", _err)


probe_metrics = ProbeMetrics()


# ---------------------------------------------------------------------------
# MetricsServer — health/status on DAEMON_HEALTH_PORT, Prometheus on
# DAEMON_METRICS_PORT
# ---------------------------------------------------------------------------


class MetricsServer:
    """Health/status and Prometheus HTTP listeners for the daemon.

    /health and /status (JSON) on DAEMON_HEALTH_PORT (default 9091);
    /metrics (Prometheus text, default registry) on DAEMON_METRICS_PORT
    (default 9090). Kept on separate ports so the scrape target and the
    probe target stay distinct.
    """

    def __init__(self, config: MetricsConfig):
        self.config = config
        self._start_time = utcnow()

        # Component references (set externally)
        self.poller = None
        self.kafka_ingestor = None
        self.processor = None
        self.responder = None
        self.scheduler = None
        self.orchestrator = None
        self.policy_maturity = None
        self.cep = None  # CepTap — None when CEP is disabled
        # The rest of the CEP loop — all None when CEP is disabled. Their
        # stats merge into the /status "cep" section (spec AC 8).
        self.cep_engine = None  # CepEngine
        self.cep_graph = None  # EntityGraph
        self.cep_snapshots = None  # SnapshotManager
        self.cep_pipeline = None  # CepPipeline
        self.cep_bridge = None  # CepResponseBridge

        self._tasks: Dict[str, asyncio.Task] = {}
        self._cep_observables_ready = False

    def register_task(self, name: str, task: "asyncio.Task") -> None:
        """Track a component's task so /health reflects whether it is alive."""
        self._tasks[name] = task

    @property
    def _cep_degraded(self) -> bool:
        """CEP degradation: tap overflow (drop-newest active) or snapshot
        writes failing (the restart loss window widening). Neither is a
        spine fault — the engine stays up and the pipeline keeps running."""
        if self.cep is not None and self.cep.stats.get("cep_degraded"):
            return True
        if self.cep_snapshots is not None and self.cep_snapshots.stats.get(
            "cep_snapshot_degraded"
        ):
            return True
        return False

    def _component_state(self, name: str, component: Any) -> str:
        # The CEP parts are a deliberate absence when disabled, not failed
        # components, and the tap has no run loop of its own to die.
        if name.startswith("cep"):
            if component is None:
                return "disabled"
            if name == "cep":
                # Degradation (tap overflow, snapshot writes failing) is a
                # visible state of its own, never an unhealthy one: the
                # spine and its acks are untouched (spec AC 8), and a
                # restart would not clear it faster.
                return "degraded" if self._cep_degraded else "running"
        # The maturity job is config-gated: an unwired scheduler is a
        # deliberate absence, not a failed component.
        if name == "policy-maturity" and component is None:
            return "disabled"
        task = self._tasks.get(name)
        if component is None or task is None:
            return "not_initialized"
        # done() first: a dead orchestrator task is a failure even when disabled.
        if task.done():
            if task.cancelled():
                return "stopped"
            exc = task.exception()
            return f"failed: {type(exc).__name__}" if exc else "stopped"
        if not getattr(component, "enabled", True):
            return "disabled"
        return "running"

    @property
    def health_port(self) -> int:
        return DAEMON_HEALTH_PORT

    @property
    def metrics_port(self) -> int:
        return DAEMON_METRICS_PORT

    async def run(self, shutdown_event: asyncio.Event):
        """Run the health and Prometheus HTTP servers until shutdown."""
        health_app = web.Application()
        health_app.router.add_get("/health", self._handle_health)
        health_app.router.add_get("/status", self._handle_status)

        metrics_app = web.Application()
        metrics_app.router.add_get("/metrics", self._handle_metrics)

        runners = []
        try:
            for app, port, label in (
                (health_app, self.health_port, "Health"),
                (metrics_app, self.metrics_port, "Prometheus"),
            ):
                runner = web.AppRunner(app)
                await runner.setup()
                runners.append(runner)
                logger.info("%s server starting on port %d", label, port)
                await web.TCPSite(runner, get_settings().daemon_bind_host, port).start()

            await shutdown_event.wait()
        except Exception:
            # A failed second bind must not leave the first listener orphaned;
            # log here because main.py gathers with return_exceptions=True.
            logger.exception("Health/Prometheus server failed")
            raise
        finally:
            for runner in runners:
                await runner.cleanup()
            logger.info("Health and Prometheus servers stopped")

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Prometheus text for the default registry (OTEL reader lives there)."""
        self._ensure_cep_observables()
        # Header set raw: aiohttp's content_type= rejects the charset parameter
        # that CONTENT_TYPE_LATEST carries.
        return web.Response(
            body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle health check request."""
        health: dict[str, Any] = {
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "uptime_seconds": (utcnow() - self._start_time).total_seconds(),
        }

        components = {
            name: self._component_state(name, obj)
            for name, obj in (
                ("poller", self.poller),
                ("kafka", self.kafka_ingestor),
                ("processor", self.processor),
                ("responder", self.responder),
                ("scheduler", self.scheduler),
                ("orchestrator", self.orchestrator),
                ("policy-maturity", self.policy_maturity),
                ("cep", self.cep),
                ("cep-engine", self.cep_pipeline),
                ("cep-snapshot", self.cep_snapshots),
            )
        }
        health["components"] = components

        # A dead task makes the daemon unhealthy so the probes restart it.
        # CEP degradation is not a dead task: it is visible as its own
        # component state, and never unhealthy-from-CEP (spec AC 8) — the
        # spine is untouched and a restart would not clear it faster.
        ok = all(v in ("running", "disabled", "degraded") for v in components.values())
        health["status"] = "healthy" if ok else "unhealthy"
        status_code = 200 if ok else 503
        return web.json_response(health, status=status_code)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Handle detailed status request."""
        metrics = self._collect_metrics()

        status = {
            "daemon": {
                "start_time": self._start_time.isoformat(),
                "uptime_seconds": (utcnow() - self._start_time).total_seconds(),
            },
            "poller": metrics.get("poller", {}),
            "kafka": metrics.get("kafka", {}),
            "processor": metrics.get("processor", {}),
            "responder": metrics.get("responder", {}),
            "scheduler": metrics.get("scheduler", {}),
            "orchestrator": metrics.get("orchestrator", {}),
            "cep": metrics.get("cep", {}),
            "vendors": metrics["vendors"],
        }

        return web.json_response(status)

    def _collect_metrics(self) -> dict[str, Any]:
        """Collect metrics from all component stats dicts."""
        metrics: dict[str, Any] = {"vendors": vendor_error_snapshot()}

        if self.poller:
            metrics["poller"] = self.poller.stats.copy()

        if self.kafka_ingestor:
            metrics["kafka"] = dict(self.kafka_ingestor.stats)

        if self.processor:
            metrics["processor"] = self.processor.stats.copy()

        if self.responder:
            metrics["responder"] = self.responder.stats.copy()

        if self.scheduler:
            metrics["scheduler"] = self.scheduler.stats.copy()

        if self.orchestrator:
            orch_stats = self.orchestrator.stats.copy()
            orch_stats["active_agents"] = self.orchestrator._in_flight()
            orch_stats["enabled"] = self.orchestrator.enabled
            metrics["orchestrator"] = orch_stats

        if self.cep:
            metrics["cep"] = self._collect_cep()

        return metrics

    def _collect_cep(self) -> Dict[str, Any]:
        """The merged CEP stats surface (spec AC 8): the tap's counters
        (events seen, dropped, degraded) plus every other component's
        stats dict — machine and seen-id counts from the engine, graph
        size and its cap counters, snapshot writes/failures/restores and
        the snapshot's age, completed matches, and proposed actions."""
        if self.cep is None:
            return {}
        cep: Dict[str, Any] = dict(self.cep.stats)
        if self.cep_engine is not None:
            counts = self.cep_engine.counts()
            cep["cep_machines"] = counts["machines"]
            cep["cep_seen_ids"] = counts["seen_ids"]
        if self.cep_graph is not None:
            cep.update(self.cep_graph.stats)
        if self.cep_snapshots is not None:
            cep.update(self.cep_snapshots.stats)
            if self.cep_snapshots.last_snapshot_at is not None:
                cep["cep_snapshot_age_seconds"] = max(
                    0.0,
                    (utcnow() - self.cep_snapshots.last_snapshot_at).total_seconds(),
                )
        if self.cep_pipeline is not None:
            cep.update(self.cep_pipeline.stats)
        if self.cep_bridge is not None:
            cep.update(self.cep_bridge.stats)
        return cep

    def _ensure_cep_observables(self) -> None:
        """The OTEL mirrors of the CEP size/age stats (spec AC 8).

        The event-shaped counters are recorded at their event sites (the
        tap, pipeline, bridge and snapshot manager each own theirs); the
        point-in-time values have no event site, so the MetricsServer owns
        these observable instruments and reads the live stats dicts at
        collection time — the graph and the engine deliberately own no
        instruments of their own. Created once, lazily, once CEP is wired;
        a no-op when OTEL is off."""
        if self._cep_observables_ready or self.cep is None:
            return
        self._cep_observables_ready = True
        try:
            meter = get_meter("vigil.daemon")
        except Exception as _err:
            logger.debug("OTEL CEP observable instruments unavailable: %s", _err)
            return

        def observation(
            read: Callable[[], Optional[float]],
        ) -> Callable[[Any], list]:
            """A callback that reads one stat at collection time, quietly
            absent when the component is not wired or the read fails."""

            def callback(_options: Any) -> list:
                try:
                    value = read()
                except Exception:
                    return []
                if value is None:
                    return []
                from opentelemetry.metrics import Observation

                return [Observation(value)]

            return callback

        def engine_count(field: str) -> Callable[[], Optional[float]]:
            return lambda: (
                self.cep_engine.counts().get(field) if self.cep_engine else None
            )

        def graph_stat(field: str) -> Callable[[], Optional[float]]:
            return lambda: (self.cep_graph.stats.get(field) if self.cep_graph else None)

        def snapshot_age() -> Optional[float]:
            if (
                self.cep_snapshots is None
                or self.cep_snapshots.last_snapshot_at is None
            ):
                return None
            return max(
                0.0,
                (utcnow() - self.cep_snapshots.last_snapshot_at).total_seconds(),
            )

        try:
            meter.create_observable_gauge(
                "vigil.cep.machines",
                description="Open sequence machines across the CEP rules",
                callbacks=[observation(engine_count("machines"))],
            )
            meter.create_observable_gauge(
                "vigil.cep.seen_ids",
                description="Finding ids in the engine's idempotency seen-set",
                callbacks=[observation(engine_count("seen_ids"))],
            )
            meter.create_observable_gauge(
                "vigil.cep.graph.nodes",
                description="Entities and findings in the CEP entity graph",
                callbacks=[observation(graph_stat("cep_graph_nodes"))],
            )
            meter.create_observable_gauge(
                "vigil.cep.graph.edges",
                description="Timestamped relations in the CEP entity graph",
                callbacks=[observation(graph_stat("cep_graph_edges"))],
            )
            meter.create_observable_counter(
                "vigil.cep.graph.nodes.evicted",
                description="Nodes evicted at the graph's node cap",
                callbacks=[observation(graph_stat("cep_graph_nodes_evicted"))],
            )
            meter.create_observable_counter(
                "vigil.cep.graph.edges.rejected",
                description="New links rejected at the graph's edge cap",
                callbacks=[observation(graph_stat("cep_graph_edges_rejected"))],
            )
            meter.create_observable_gauge(
                "vigil.cep.snapshot.age",
                description="Seconds since the last successful CEP snapshot",
                unit="s",
                callbacks=[observation(snapshot_age)],
            )
        except Exception as _err:
            logger.debug("OTEL CEP observable instruments unavailable: %s", _err)
