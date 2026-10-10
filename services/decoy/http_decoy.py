"""Minimal high-interaction HTTP decoy.

A plausible internal appliance: a login page, a dashboard, an upload
endpoint. The canary credential always authenticates (so credential stuffing
continues and is captured); a failed login never locks anything out. Every
request lands in a per-client session; a session's payload is emitted to the
daemon webhook ingest when the window closes (idle, TTL, or shutdown).

Error resilience is structural: a middleware catches everything a handler
can raise and answers 500 — the server outlives any single bad request.
"""

import asyncio
import hashlib
import logging
from typing import Dict

from aiohttp import web

from services.decoy.canary import CanaryCredentials
from services.decoy.config import HTTP_PORT, DecoyConfig
from services.decoy.emitter import SessionEventEmitter
from services.decoy.session import (
    CREDENTIAL_CANARY,
    CREDENTIAL_REJECTED,
    DecoySession,
    DroppedFile,
)

logger = logging.getLogger(__name__)

DECOY_SERVICE_NAME = "http-decoy"

# How often the expired-session sweep runs.
_SWEEP_INTERVAL_SECONDS = 30

# Capture bound: a request body recorded as a dropped file caps here. A flood
# is data, not a lever against the decoy's memory.
_MAX_BODY_CAPTURE = 64 * 1024

_LOGIN_PAGE = """<!doctype html>
<html><head><title>NetOps Appliance</title></head>
<body>
<h2>NetOps Appliance — Sign in</h2>
<form method="post" action="/login">
  <label>Username <input name="username" autocomplete="off"></label><br>
  <label>Password <input name="password" type="password"></label><br>
  <button type="submit">Sign in</button>
</form>
</body></html>"""

_DASHBOARD_PAGE = """<!doctype html>
<html><head><title>NetOps Appliance — Dashboard</title></head>
<body>
<h2>Dashboard</h2>
<ul>
  <li><a href="/admin">Administration</a></li>
  <li><a href="/upload">Upload diagnostic bundle</a></li>
</ul>
</body></html>"""

_ADMIN_PAGE = """<!doctype html>
<html><head><title>NetOps Appliance — Administration</title></head>
<body><h2>Administration</h2><p>Configuration is current. No action required.</p></body></html>"""


class HttpDecoy:
    """The HTTP decoy application. One process serves many sessions; each
    remote address gets its own :class:`DecoySession`."""

    def __init__(
        self,
        config: DecoyConfig,
        canary: CanaryCredentials,
        emitter: SessionEventEmitter,
        host: str = "0.0.0.0",  # nosec B104 — container-scoped by the decoy network
        port: int = HTTP_PORT,
    ):
        self.config = config
        self.canary = canary
        self.emitter = emitter
        self.host = host
        self.port = port
        self._sessions: Dict[str, DecoySession] = {}

    # --- session bookkeeping ----------------------------------------------

    def _session_for(self, remote_ip: str) -> DecoySession:
        session = self._sessions.get(remote_ip)
        if session is None:
            session = DecoySession(
                decoy_service=DECOY_SERVICE_NAME,
                attacker_ip=remote_ip,
                ttl_seconds=self.config.session_ttl_seconds,
            )
            self._sessions[remote_ip] = session
            logger.info("Decoy HTTP session opened for %s", remote_ip)
        return session

    async def _emit_and_drop(self, session: DecoySession) -> None:
        payload = session.build_payload()
        ok = await self.emitter.emit(payload)
        logger.info(
            "Decoy HTTP session for %s closed (%s) — %d commands, %d auth attempts",
            session.attacker_ip,
            "emitted" if ok else "NOT emitted",
            len(payload["commands"]),
            len(payload["auth_attempts"]),
        )

    async def sweep_expired(self) -> int:
        """Close and emit every expired session window. Returns the count."""
        expired = [ip for ip, s in self._sessions.items() if s.expired()]
        for ip in expired:
            session = self._sessions.pop(ip)
            await self._emit_and_drop(session)
        return len(expired)

    async def flush_all(self) -> None:
        """Emit everything outstanding (shutdown path)."""
        while self._sessions:
            _, session = self._sessions.popitem()
            await self._emit_and_drop(session)

    # --- handlers ----------------------------------------------------------

    async def _record(self, request: web.Request, detail: str) -> DecoySession:
        session = self._session_for(request.remote or "unknown")
        session.record_command(detail)
        return session

    async def handle_index(self, request: web.Request) -> web.Response:
        await self._record(request, "GET /")
        return web.Response(text=_LOGIN_PAGE, content_type="text/html")

    async def handle_login(self, request: web.Request) -> web.Response:
        session = self._session_for(request.remote or "unknown")
        form = await request.post()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        # Canary path: only the canary password ever succeeds, for any user.
        success = self.canary.matches(password)
        session.record_auth(
            user=username or "(none)",
            success=success,
            credential=CREDENTIAL_CANARY if success else CREDENTIAL_REJECTED,
        )
        if success:
            logger.info(
                "Decoy HTTP canary login for %s as %s", request.remote, username
            )
            response = web.Response(status=303, headers={"Location": "/dashboard"})
            response.set_cookie("sessionid", "decoy", path="/", httponly=True)
            return response
        # A failed login looks like a failed login — and nothing locks out.
        return web.Response(
            text=_LOGIN_PAGE.replace("<h2>", "<h2>Invalid credentials<br>"),
            content_type="text/html",
            status=401,
        )

    async def handle_dashboard(self, request: web.Request) -> web.Response:
        await self._record(request, "GET /dashboard")
        return web.Response(text=_DASHBOARD_PAGE, content_type="text/html")

    async def handle_admin(self, request: web.Request) -> web.Response:
        await self._record(request, "GET /admin")
        return web.Response(text=_ADMIN_PAGE, content_type="text/html")

    async def handle_upload(self, request: web.Request) -> web.Response:
        session = await self._record(request, "POST /upload")
        body = await request.read()
        if body:
            content = body[:_MAX_BODY_CAPTURE]
            session.record_file(
                DroppedFile(
                    name="request-body.bin",
                    sha256=hashlib.sha256(content).hexdigest(),
                    source="request-body",
                )
            )
            session.raw["upload_bytes"] = len(body)
        return web.json_response({"status": "stored"})

    async def handle_health(self, request: web.Request) -> web.Response:
        # Container healthcheck target; deliberately boring.
        return web.json_response({"status": "healthy"})

    async def handle_404(self, request: web.Request) -> web.Response:
        await self._record(request, f"{request.method} {request.path}")
        return web.Response(status=404, text="Not Found")

    # --- wiring -------------------------------------------------------------

    @web.middleware
    async def _resilience(self, request: web.Request, handler) -> web.StreamResponse:
        """A handler error is a 500, never a crash: the decoy outlives any
        single bad request (the session-never-terminates invariant)."""
        try:
            return await handler(request)
        except Exception:
            logger.exception(
                "Decoy HTTP handler failed on %s %s", request.method, request.path
            )
            return web.Response(status=500, text="Internal Server Error")

    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._resilience])
        app.router.add_get("/", self.handle_index)
        app.router.add_post("/login", self.handle_login)
        app.router.add_get("/dashboard", self.handle_dashboard)
        app.router.add_get("/admin", self.handle_admin)
        app.router.add_post("/upload", self.handle_upload)
        app.router.add_get("/health", self.handle_health)
        # Unknown paths are recorded and answered with a plain 404.
        app.router.add_route("*", "/{tail:.*}", self.handle_404)
        return app

    async def run(self, shutdown_event) -> None:
        """Serve until the shutdown event, sweeping expired session windows.
        On shutdown, everything still open is emitted before exit."""
        app = self.build_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("HTTP decoy serving on %s:%d", self.host, self.port)
        try:
            while not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=_SWEEP_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    pass
                await self.sweep_expired()
        finally:
            await self.flush_all()
            await runner.cleanup()
            logger.info("HTTP decoy stopped")


def main() -> None:
    """Container entrypoint (``python -m services.decoy.http_decoy``)."""
    import signal

    from core.telemetry import configure_logging
    from services.decoy.canary import resolve_canary

    configure_logging()
    config = DecoyConfig.from_settings()
    if not config.enabled:
        # The container was started without its master switch: an honest no-op,
        # not a half-serving decoy.
        logger.info("Decoy disabled (DECOY_ENABLED is not true); exiting")
        return
    shutdown_event = asyncio.Event()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_event.set)
        except NotImplementedError:  # pragma: no cover — non-POSIX
            pass
    decoy = HttpDecoy(
        config=config,
        canary=resolve_canary(),
        emitter=SessionEventEmitter(
            config.ingest_url, timeout_seconds=config.emit_timeout_seconds
        ),
    )
    loop.run_until_complete(decoy.run(shutdown_event))
    loop.close()


if __name__ == "__main__":
    main()
