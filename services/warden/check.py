"""``python -m services.warden check`` — the container HEALTHCHECK probe.

One local HTTP GET to the process's own ``/health`` listener: the same
surface the Helm probes scrape and the daemon's HEALTHCHECK pattern curls.
Stdlib urllib, deliberately — an image dependency regression should fail
the server, not the probe that reports on it.

Exit 0 only when the listener answers 200 with ``{"status": "healthy"}``.
The health payload is component-liveness (a dead component task is a 503),
so a Warden that stopped defending reads unhealthy and the supervisor
restarts it — the Medic ``check`` posture, minus the heartbeat file: the
listener is the process's own liveness record.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT_SECONDS = 3.0

# Bind hosts that mean "every interface". The probe still dials loopback,
# which a wildcard listener also serves; anything else is dialed as given.
_ANY_INTERFACE = frozenset({"", "0.0.0.0", "::"})


def probe_host(bind_host: str) -> str:
    """The address a local probe dials for a listener bound to ``bind_host``."""
    return "127.0.0.1" if bind_host in _ANY_INTERFACE else bind_host


def check_health(
    host: str,
    port: int,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, str]:
    """GET /health on the local listener; returns ``(exit_code, reason)``.

    Never raises: every failure mode (connection refused, timeout, non-200,
    non-JSON, wrong status field) comes back as a nonzero exit code and a
    one-line reason a container log can be skimmed for.
    """
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # urllib raises for every >=400 answer — the 503-from-dead-component
        # case included — and carries the response the server actually sent.
        return 1, f"unhealthy: /health answered HTTP {exc.code}"
    except OSError as exc:
        return 1, f"unreachable: /health on {host}:{port} ({exc})"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 1, "unhealthy: /health payload is not JSON"
    if not isinstance(payload, dict):
        return 1, "unhealthy: /health payload is not an object"
    reported = payload.get("status")
    if status != 200 or reported != "healthy":
        return 1, f"unhealthy: HTTP {status}, payload status {reported!r}"
    return 0, "healthy"
