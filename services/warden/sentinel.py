"""Sentinel: the local alert receiver — the daemon-webhook pattern, fail-closed.

EDR agents, syslog shippers, and local tools push alerts to a loopback
listener; Sentinel validates and queues them for the decision loop. The
auth rules copy services/daemon/poller.py exactly:

- **Token unset → 503** on every request. A receiver that is "open because
  nobody configured it" is the failure mode, not a convenience.
- **Missing or wrong token → 401**, compared with hmac.compare_digest.
- Bounded queue: a full queue returns 503 so the pusher holds its cursor
  and retries (nothing dropped silently), never a 200 that lied.
- Dedup is in-memory and bounded — restarts may re-deliver, which is why
  decision-stage idempotency lives downstream.

The listener binds loopback by default; the v1 signal surface is local
pushers, not network producers.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections import OrderedDict
from typing import Any

from aiohttp import web

from services.warden.metrics import WardenMetrics

logger = logging.getLogger(__name__)


class Sentinel:
    """Authenticated local alert intake with a bounded decision queue."""

    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        token: str | None,
        max_queue: int = 1000,
        max_batch: int = 100,
        max_body_bytes: int = 1024 * 1024,
        dedup_capacity: int = 10_000,
        metrics: WardenMetrics | None = None,
    ) -> None:
        self._bind_host = bind_host
        self._port = port
        self._token = token
        self._max_batch = max_batch
        self._max_body = max_body_bytes
        self._metrics = metrics
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._dedup_capacity = dedup_capacity
        self._dedup_hits = 0

    # ------------------------------------------------------------------
    # Server lifecycle (the metrics-server pattern)
    # ------------------------------------------------------------------

    def _app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/alert", self._handle_alert)
        return app

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Serve until ``shutdown_event`` fires, then clean up.

        A port already taken raises and kills the task, matching the
        metrics server: an intake nobody can reach is a dead component.
        """
        runner = web.AppRunner(self._app(), access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self._bind_host, self._port)
            await site.start()
            logger.info(
                "warden sentinel on http://%s:%d/alert", self._bind_host, self._port
            )
            await shutdown_event.wait()
        finally:
            await runner.cleanup()

    # ------------------------------------------------------------------
    # Alert intake
    # ------------------------------------------------------------------

    async def _handle_alert(self, request: web.Request) -> web.Response:
        if not self._token:
            return self._reject("no_secret", status=503)
        presented = request.headers.get("Authorization", "")
        expected = f"Bearer {self._token}"
        if not hmac.compare_digest(presented, expected):
            return self._reject("bad_token", status=401)
        body = await request.content.read(self._max_body + 1)
        if len(body) > self._max_body:
            return self._reject("too_large", status=413)
        try:
            payload = json.loads(body)
        except ValueError:
            return self._reject("bad_body", status=400)
        alerts = self._extract(payload)
        if alerts is None or len(alerts) > self._max_batch:
            return self._reject("bad_body", status=400)

        accepted, duplicates = 0, 0
        for alert in alerts:
            alert_id = self._identity(alert)
            if alert_id in self._seen:
                self._seen.move_to_end(alert_id)
                duplicates += 1
                continue
            try:
                self.queue.put_nowait(alert)
            except asyncio.QueueFull:
                if accepted == 0 and duplicates == 0:
                    return self._reject("queue_full", status=503)
                break  # keep what fit; the pusher retries the rest
            self._remember(alert_id)
            accepted += 1
        self._dedup_hits += duplicates
        if self._metrics is not None:
            self._metrics.decisions.labels(result="accepted").inc(accepted)
            self._metrics.decisions.labels(result="duplicate").inc(duplicates)
        return web.json_response(
            {"status": "accepted", "accepted": accepted, "duplicates": duplicates},
            status=202,
        )

    @staticmethod
    def _extract(payload: Any) -> list[dict[str, Any]] | None:
        """Normalize a push body to a list of alert dicts, or None.

        The accepted shapes are exactly two — a single alert object or an
        ``{"alerts": [...]}`` envelope. A bare list is rejected so the
        wire contract stays unambiguous for local pushers.
        """
        if not isinstance(payload, dict):
            return None
        if "alerts" in payload:
            alerts = payload.get("alerts")
        else:
            alerts = [payload]
        if not isinstance(alerts, list) or not alerts:
            return None
        if not all(isinstance(alert, dict) for alert in alerts):
            return None
        if not all(alert.get("id") for alert in alerts):
            return None
        return alerts

    @staticmethod
    def _identity(alert: dict[str, Any]) -> str:
        raw = str(alert.get("id"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def _remember(self, alert_id: str) -> None:
        self._seen[alert_id] = None
        if len(self._seen) > self._dedup_capacity:
            self._seen.popitem(last=False)  # discard the oldest

    def _reject(self, reason: str, *, status: int) -> web.Response:
        if self._metrics is not None:
            self._metrics.sentinel_rejections.labels(reason=reason).inc()
        logger.warning("warden sentinel rejected a push: reason=%s", reason)
        return web.json_response(
            {"status": "rejected", "reason": reason}, status=status
        )

    # ------------------------------------------------------------------
    # Consumption (the decision loop drains this)
    # ------------------------------------------------------------------

    def drain(self, limit: int) -> list[dict[str, Any]]:
        """Take up to ``limit`` queued alerts without blocking."""
        alerts: list[dict[str, Any]] = []
        while len(alerts) < limit:
            try:
                alerts.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return alerts
