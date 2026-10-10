"""The check command: the image HEALTHCHECK's probe surface.

``python -m services.warden check`` is the only thing standing between a
stopped-defending Warden and a supervisor that keeps it running, so the
probe's contract gets the same treatment as the fail-closed receivers: every
way the answer can be wrong gets a test. The dispatch tests also pin the two
invariants the Dockerfile relies on: ``check`` needs no trust material, and
the default (no-argument) path still refuses to start without one.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import pytest
from aiohttp import web

from services.warden import main as warden_main
from services.warden.check import check_health, probe_host
from services.warden.metrics import WardenMetrics, WardenMetricsServer
from tests.unit.warden.helpers import free_port, free_ports

HealthProvider = Callable[[], tuple[int, dict[str, Any]]]


async def serve_health(
    health_provider: HealthProvider,
) -> tuple[int, asyncio.Event, asyncio.Task[None]]:
    """Serve /health on free ports; the caller stops the returned task.

    Real HTTP on ephemeral ports (the metrics-server tests' pattern): the
    probe is a network client, and mocking the network out of it would test
    nothing.
    """
    health_port, metrics_port = free_ports(2)
    server = WardenMetricsServer(
        bind_host="127.0.0.1",
        health_port=health_port,
        metrics_port=metrics_port,
        metrics=WardenMetrics(),
        health_provider=health_provider,
        status_provider=dict,
    )
    shutdown = asyncio.Event()
    task = asyncio.create_task(server.run(shutdown))
    # Poll until the site is bound — TCPSite.start happens inside the task's
    # first steps. Via to_thread: check_health is a blocking client, and
    # calling it on the loop thread would deadlock the handler it waits on
    # (in production the probe is a separate process; here it must share the
    # loop with the server it probes).
    for _ in range(50):
        code, reason = await asyncio.to_thread(check_health, "127.0.0.1", health_port)
        if "unreachable" not in reason:
            return health_port, shutdown, task
        await asyncio.sleep(0.05)
    shutdown.set()
    await task
    pytest.fail("health listener never came up")


# --------------------------------------------------------------------------
# probe_host — where a local probe dials
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bind_host", "expected"),
    [
        ("0.0.0.0", "127.0.0.1"),
        ("::", "127.0.0.1"),
        ("", "127.0.0.1"),
        ("127.0.0.1", "127.0.0.1"),
        ("192.168.1.5", "192.168.1.5"),
    ],
)
def test_probe_host(bind_host: str, expected: str) -> None:
    assert probe_host(bind_host) == expected


# --------------------------------------------------------------------------
# check_health — against a live listener
# --------------------------------------------------------------------------


class TestCheckHealth:
    async def test_healthy_listener_answers_zero(self) -> None:
        port, shutdown, task = await serve_health(lambda: (200, {"status": "healthy"}))
        try:
            code, reason = await asyncio.to_thread(check_health, "127.0.0.1", port)
            assert (code, reason) == (0, "healthy")
        finally:
            shutdown.set()
            await task

    async def test_dead_component_answers_one(self) -> None:
        # The 503-with-payload case the health provider really produces.
        port, shutdown, task = await serve_health(
            lambda: (503, {"status": "unhealthy", "components": {"loop": "failed"}})
        )
        try:
            code, reason = await asyncio.to_thread(check_health, "127.0.0.1", port)
            assert code == 1
            assert "503" in reason
        finally:
            shutdown.set()
            await task

    async def test_wrong_payload_status_answers_one(self) -> None:
        # 200 from the socket but the payload does not say healthy: not a
        # pass — the probe reads the payload, not just the transport.
        port, shutdown, task = await serve_health(lambda: (200, {"status": "degraded"}))
        try:
            code, reason = await asyncio.to_thread(check_health, "127.0.0.1", port)
            assert code == 1
            assert "degraded" in reason
        finally:
            shutdown.set()
            await task

    async def test_unreachable_port_answers_one(self) -> None:
        port = free_port()  # bound by nothing
        code, reason = check_health("127.0.0.1", port, timeout_seconds=0.2)
        assert code == 1
        assert "unreachable" in reason

    async def test_non_json_payload_answers_one(self) -> None:
        # A payload the server did not build (a proxy answering, a broken
        # handler) must read unhealthy, not crash the probe.
        app = web.Application()
        app.router.add_get("/health", lambda _: web.Response(text="not json"))
        runner = web.AppRunner(app)
        await runner.setup()
        port = free_port()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        try:
            code, reason = await asyncio.to_thread(check_health, "127.0.0.1", port)
            assert code == 1
            assert "not JSON" in reason
        finally:
            await runner.cleanup()


# --------------------------------------------------------------------------
# main() dispatch — check needs no trust material; the run path still does
# --------------------------------------------------------------------------


class TestCheckDispatch:
    async def test_check_returns_zero_against_a_healthy_listener(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        port, shutdown, task = await serve_health(lambda: (200, {"status": "healthy"}))
        try:
            monkeypatch.setenv("WARDEN_HEALTH_PORT", str(port))
            monkeypatch.setenv("WARDEN_BIND_HOST", "127.0.0.1")
            # The point of the command: the probe answers before any trust
            # material or enrollment exists.
            monkeypatch.delenv("WARDEN_TRUST_ROOT_PATH", raising=False)
            code = await asyncio.to_thread(warden_main.main, ["check"])
            assert code == 0
        finally:
            shutdown.set()
            await task

    async def test_check_reports_a_dead_process_as_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A live listener with a failed component answers 503; the probe
        # maps that to exit 1 so the supervisor restarts the container.
        port, shutdown, task = await serve_health(
            lambda: (503, {"status": "unhealthy", "components": {"loop": "failed"}})
        )
        try:
            monkeypatch.setenv("WARDEN_HEALTH_PORT", str(port))
            monkeypatch.setenv("WARDEN_BIND_HOST", "127.0.0.1")
            code = await asyncio.to_thread(warden_main.main, ["check"])
            assert code == 1
        finally:
            shutdown.set()
            await task

    def test_check_without_a_listener_answers_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # No process at all (the image's boot hasn't finished, or it died):
        # unreachable, not an exception out of the probe.
        port = free_port()
        monkeypatch.setenv("WARDEN_HEALTH_PORT", str(port))
        monkeypatch.setenv("WARDEN_BIND_HOST", "127.0.0.1")
        assert warden_main.main(["check"]) == 1
        assert "unreachable" in capsys.readouterr().out

    def test_check_reports_invalid_env_as_exit_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("WARDEN_HEALTH_PORT", "not-a-port")
        assert warden_main.main(["check"]) == 2
        assert "invalid configuration" in capsys.readouterr().err

    def test_default_path_still_refuses_without_trust_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The dispatch change must not have loosened the run path: no
        # subcommand and no WARDEN_TRUST_ROOT_PATH is still exit 2.
        monkeypatch.delenv("WARDEN_TRUST_ROOT_PATH", raising=False)
        assert warden_main.main([]) == 2
