"""Warden's metrics and the two listeners every operator points at.

The metrics registry is per-instance (its own ``CollectorRegistry``, never
the global one): the process is the only writer, and a second instance in a
test must not collide with the first's series. ``/metrics`` is Prometheus
text — the daemon's scrape contract. ``/health`` and ``/status`` render a
payload the process assembles (``health_provider``), so the server stays
dumb about components: it owns ports and liveness, the ``Warden`` object
owns what the numbers say.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from aiohttp import web
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

logger = logging.getLogger(__name__)

# A callable returning (http_status, payload) for /health, and a payload
# for /status — assembled by the Warden process, which knows the components.
HealthProvider = Callable[[], tuple[int, dict[str, Any]]]
StatusProvider = Callable[[], dict[str, Any]]


class WardenMetrics:
    """The process's counters and gauge, on a private registry."""

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self.sync_attempts = Counter(
            "warden_sync_attempts_total",
            "Policy sync attempts by outcome.",
            labelnames=("outcome",),
            registry=self._registry,
        )
        self.decisions = Counter(
            "warden_decisions_total",
            "Sentinel alerts by handling result.",
            labelnames=("result",),
            registry=self._registry,
        )
        self.enforcements = Counter(
            "warden_enforcements_total",
            "Executor invocations by status and executor.",
            labelnames=("status", "executor"),
            registry=self._registry,
        )
        self.journal_appends = Counter(
            "warden_journal_appends_total",
            "Journal appends by result.",
            labelnames=("result",),
            registry=self._registry,
        )
        self.undo_total = Counter(
            "warden_undo_total",
            "Executor undos by reason.",
            labelnames=("reason",),
            registry=self._registry,
        )
        self.sentinel_rejections = Counter(
            "warden_sentinel_rejections_total",
            "Sentinel rejections by reason.",
            labelnames=("reason",),
            registry=self._registry,
        )
        self.slm_opinions = Counter(
            "warden_slm_opinions_total",
            "Local SLM rankings by outcome.",
            labelnames=("outcome",),  # deciding | advisory | unavailable
            registry=self._registry,
        )
        self.reconcile_attempts = Counter(
            "warden_reconcile_attempts_total",
            "Journal reconcile pushes by outcome.",
            labelnames=("outcome",),
            registry=self._registry,
        )
        self.reconcile_records = Counter(
            "warden_reconcile_records_total",
            "Journal records by reconcile result.",
            labelnames=("result",),
            registry=self._registry,
        )
        self.live_actions = Gauge(
            "warden_live_actions",
            "Live reversible actions currently enforced.",
            registry=self._registry,
        )

    def render(self) -> bytes:
        return generate_latest(self._registry)


class WardenMetricsServer:
    """Health/status and Prometheus listeners, one aiohttp app per port.

    Modeled on the daemon's metrics server, without its dependencies: no
    Settings, no OTEL — Warden's edge surface is these ports and the
    policy-sync channel, nothing else.
    """

    def __init__(
        self,
        *,
        bind_host: str,
        health_port: int,
        metrics_port: int,
        metrics: WardenMetrics,
        health_provider: HealthProvider,
        status_provider: StatusProvider,
    ) -> None:
        self._bind_host = bind_host
        self._health_port = health_port
        self._metrics_port = metrics_port
        self._metrics = metrics
        self._health_provider = health_provider
        self._status_provider = status_provider
        self._runner: web.AppRunner | None = None
        self._metrics_runner: web.AppRunner | None = None

    def _health_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/status", self._handle_status)
        return app

    def _metrics_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/metrics", self._handle_metrics)
        return app

    async def _handle_health(self, request: web.Request) -> web.Response:
        status, payload = self._health_provider()
        return web.json_response(payload, status=status)

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._status_provider())

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        return web.Response(
            body=self._metrics.render(),
            content_type="text/plain",
            charset="utf-8",
        )

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Serve until ``shutdown_event`` fires, then clean up.

        A port already taken raises and kills the task: a Warden whose
        health port is missing looks dead to every probe, so it should
        actually be dead — the supervisor restarts it.
        """
        self._runner = web.AppRunner(self._health_app(), access_log=None)
        self._metrics_runner = web.AppRunner(self._metrics_app(), access_log=None)
        await self._runner.setup()
        await self._metrics_runner.setup()
        try:
            health_site = web.TCPSite(self._runner, self._bind_host, self._health_port)
            metrics_site = web.TCPSite(
                self._metrics_runner, self._bind_host, self._metrics_port
            )
            await health_site.start()
            await metrics_site.start()
            logger.info(
                "warden health on http://%s:%d, metrics on http://%s:%d",
                self._bind_host,
                self._health_port,
                self._bind_host,
                self._metrics_port,
            )
            await shutdown_event.wait()
        finally:
            await self._runner.cleanup()
            await self._metrics_runner.cleanup()
            self._runner = None
            self._metrics_runner = None
