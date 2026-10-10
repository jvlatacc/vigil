"""The fake internal file portal — the one high-interaction HTTP decoy.

stdlib only (the decoy-farm image has no dependencies). A convincing-but-fake
internal document portal: a login form that rejects everything, a document
listing, and downloadable files whose contents are placeholders. Every
request from a non-loopback peer becomes a JSON-lines event on the shared
decoy_logs volume, where the telemetry shipper picks it up. Loopback callers
(the container healthcheck) are plumbing, not attackers, and are not recorded.

Environment:
- DECOY_HTTP_LISTEN     host:port to serve (default 0.0.0.0:8080)
- DECOY_HTTP_EVENT_LOG  event file (default /decoy-logs/http-decoy.jsonl)
- DECOY_HTTP_DECOY_NAME decoy identity in events (default fileportal-01)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

DEFAULT_LISTEN = "0.0.0.0:8080"
DEFAULT_EVENT_LOG = "/decoy-logs/http-decoy.jsonl"
DEFAULT_DECOY_NAME = "fileportal-01"
SERVER_BANNER = "nginx"  # version_string() renders "nginx/1.24.0"
SERVER_BANNER_VERSION = "1.24.0"

_LOGIN_FORM = (
    '<form method="post" action="/login">'
    '<input name="username" placeholder="Username" required>'
    '<input name="password" type="password" placeholder="Password" required>'
    '<button type="submit">Sign in</button></form>'
)

_FILE_TABLE = (
    "<h2>Shared documents</h2><table><tr><th>Name</th><th>Size</th></tr>"
    "<tr><td><a href='/files/Q3-forecast.xlsx'>Q3-forecast.xlsx</a></td><td>84 KB</td></tr>"
    "<tr><td><a href='/files/it-runbook.pdf'>it-runbook.pdf</a></td><td>1.2 MB</td></tr>"
    "<tr><td><a href='/files/vpn-config.bak'>vpn-config.bak</a></td><td>3 KB</td></tr>"
    "</table><p><a href='/'>&larr; Sign in</a></p>"
)

_FAKE_FILE = (
    "# This file is a placeholder on a decoy host.\n# Nothing here is real, "
    "and nothing here leaves the decoy network.\n"
)


def _page(body: str) -> str:
    return (
        "<!doctype html><html><head><title>FilePortal</title>"
        "<style>body{font-family:sans-serif;background:#f4f5f7;display:flex;"
        "align-items:center;justify-content:center;height:100vh;margin:0}"
        ".card{background:#fff;padding:2em;border-radius:8px;box-shadow:0 1px 4px "
        "rgba(0,0,0,.15);min-width:320px}input,button{display:block;margin:.5em 0;"
        "padding:.5em;width:100%}.err{color:#b00}</style></head>"
        f"<body><div class='card'><h1>FilePortal</h1>{body}</div></body></html>"
    )


class DecoyRequestHandler(BaseHTTPRequestHandler):
    server_version = SERVER_BANNER
    sys_version = SERVER_BANNER_VERSION

    # populated by serve()
    event_log: str = DEFAULT_EVENT_LOG
    decoy_name: str = DEFAULT_DECOY_NAME

    def _client_ip(self) -> str:
        host, _port = self.client_address[:2]
        return str(host)

    def _record(
        self, *, method: str, path: str, extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Append one JSON-lines event for non-loopback peers."""
        client_ip = self._client_ip()
        if client_ip.startswith("127."):
            return  # healthcheck and in-container plumbing
        event: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "decoy": self.decoy_name,
            "src_ip": client_ip,
            "src_port": self.client_address[1],
            "method": method,
            "path": path,
            "user_agent": self.headers.get("User-Agent", ""),
        }
        if extra:
            event.update(extra)
        try:
            with open(self.event_log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        except OSError as exc:
            # Never let telemetry failure take the decoy down: serving is the
            # priority, shipping is best-effort.
            logger.warning("Cannot write decoy event: %s", exc)

    def _respond(
        self, status: int, body: str, content_type: str = "text/html; charset=utf-8"
    ) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        self._record(method="GET", path=path)
        if path == "/":
            self._respond(200, _page(_LOGIN_FORM))
        elif path == "/files":
            self._respond(200, _page(_FILE_TABLE))
        elif path.startswith("/files/"):
            self._respond(200, _FAKE_FILE, content_type="application/octet-stream")
        elif path == "/health":
            self._respond(200, '{"status": "ok"}', content_type="application/json")
        else:
            self._respond(404, _page("<p>Not found.</p>"))

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/login":
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(
                self.rfile.read(min(length, 4096)).decode("utf-8", errors="replace")
            )
            username = (form.get("username") or [""])[0]
            self._record(method="POST", path=path, extra={"username": username})
            self._respond(401, _page("<p class='err'>Invalid credentials.</p>"))
        else:
            self._record(method="POST", path=path)
            self._respond(404, _page("<p>Not found.</p>"))

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("decoy http: %s", format % args)


def _split_listen(listen: str) -> Tuple[str, int]:
    parts = urlsplit(listen if "//" in listen else "//" + listen)
    return parts.hostname or "0.0.0.0", parts.port or 8080


def serve(listen: str, event_log: str, decoy_name: str) -> None:
    DecoyRequestHandler.event_log = event_log
    DecoyRequestHandler.decoy_name = decoy_name
    host, port = _split_listen(listen)
    server = ThreadingHTTPServer((host, port), DecoyRequestHandler)
    logger.info(
        "HTTP decoy %s serving on %s:%d (events -> %s)",
        decoy_name,
        host,
        port,
        event_log,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    listen = os.environ.get("DECOY_HTTP_LISTEN") or DEFAULT_LISTEN
    event_log = os.environ.get("DECOY_HTTP_EVENT_LOG") or DEFAULT_EVENT_LOG
    decoy_name = os.environ.get("DECOY_HTTP_DECOY_NAME") or DEFAULT_DECOY_NAME
    serve(listen, event_log, decoy_name)


if __name__ == "__main__":
    main()
