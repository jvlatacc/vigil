"""Warden process tests: startup refusals, lifecycle, health, hygiene.

The no-database requirement is not just an import-linter contract — it is
asserted here at AST level so the failure shows up in the fastest loop a
developer runs. Shutdown semantics get their own test because "stop" is a
control surface as well as a feature: it must never *tighten* protection
by, say, rolling back the live reversible actions a partition-time defense
put in place.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import aiohttp

from core.edge import EDGE_TRUST_ROOT
from core.edge.envelope import REVERSIBLE_ACTION_TYPES
from core.edge.policy import load_policy_pack
from core.edge.signing import deterministic_json, sign_envelope
from services.warden import main as warden_main
from services.warden.config import WardenConfig
from services.warden.main import Warden, load_trust_root
from tests.unit.edge.helpers import NOW, build_root_doc
from tests.unit.warden.helpers import (
    FakeClock,
    free_ports,
    make_pack_bytes,
    make_policy_key,
    make_root,
)

# --------------------------------------------------------------------------
# Test components
# --------------------------------------------------------------------------


class RecordingComponent:
    """A component that starts, waits on shutdown, and records its life."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self.started = True
        try:
            await shutdown_event.wait()
            self.stopped = True
        except asyncio.CancelledError:
            self.stopped = True
            raise


class FailingComponent:
    """A component that dies immediately — the dead-component health case."""

    def __init__(self) -> None:
        self.started = False

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self.started = True
        raise RuntimeError("component exploded")


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


def _config(tmp_path: Path, **overrides) -> WardenConfig:
    sentinel_port, health_port, metrics_port = free_ports(3)
    defaults = dict(
        control_plane_url="http://127.0.0.1:6987",
        data_dir=tmp_path / "warden-data",
        node_id="wn-test000",
        sentinel_port=sentinel_port,
        health_port=health_port,
        metrics_port=metrics_port,
    )
    defaults.update(overrides)
    return WardenConfig(**defaults)


# --------------------------------------------------------------------------
# main() startup refusals — fail-closed before anything starts
# --------------------------------------------------------------------------


def _write_root_file(tmp_path: Path, policy_key) -> Path:
    """Raw signed trust-root bytes on disk — the image-bake artifact."""
    root_key = make_policy_key()  # any key; the root self-signs
    doc = build_root_doc([root_key], [policy_key])
    raw = sign_envelope(deterministic_json(doc), EDGE_TRUST_ROOT, [root_key])
    path = tmp_path / "trust-root.json"
    path.write_bytes(raw)
    return path


class TestStartupRefusals:
    def test_no_configuration_fails_with_exit_2(self, capsys) -> None:
        exit_code = warden_main.main([])
        assert exit_code == 2
        err = capsys.readouterr().err
        # The control-plane URL has a valid default; the trust root does
        # not — it is the first complaint an empty environment produces.
        assert "WARDEN_TRUST_ROOT_PATH" in err

    def test_config_problems_are_reported_not_raised(self, capsys) -> None:
        exit_code = warden_main.main([])
        assert exit_code == 2  # a problem list, not an exception

    def test_config_validated_before_trust_root(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        # Both inputs are broken; the config problem must be what is
        # reported — validation is cheap, the trust-root check reads disk.
        monkeypatch.setenv("WARDEN_CONTROL_PLANE_URL", "not-a-url")
        monkeypatch.setenv("WARDEN_TRUST_ROOT_PATH", str(tmp_path / "missing.json"))
        exit_code = warden_main.main([])
        assert exit_code == 2
        assert "WARDEN_CONTROL_PLANE_URL" in capsys.readouterr().err

    def test_missing_trust_root_file_refuses_to_start(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("WARDEN_CONTROL_PLANE_URL", "http://127.0.0.1:6987")
        monkeypatch.setenv("WARDEN_TRUST_ROOT_PATH", str(tmp_path / "absent.json"))
        monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path / "data"))
        exit_code = warden_main.main([])
        assert exit_code == 2
        assert "cannot read trust root" in capsys.readouterr().err

    def test_tampered_trust_root_refuses_to_start(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        key = make_policy_key()
        root_path = _write_root_file(tmp_path, key)
        raw = root_path.read_bytes()
        half = len(raw) // 2
        root_path.write_bytes(raw[:half] + b"x" + raw[half + 1 :])
        monkeypatch.setenv("WARDEN_CONTROL_PLANE_URL", "http://127.0.0.1:6987")
        monkeypatch.setenv("WARDEN_TRUST_ROOT_PATH", str(root_path))
        monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path / "data"))
        exit_code = warden_main.main([])
        assert exit_code == 2
        assert "failed verification" in capsys.readouterr().err

    def test_valid_trust_root_loads(self, tmp_path) -> None:
        key = make_policy_key()
        root_path = _write_root_file(tmp_path, key)
        root = load_trust_root(root_path, now=NOW)
        assert root["version"] == 1


# --------------------------------------------------------------------------
# Warden lifecycle — start, supervise, drain
# --------------------------------------------------------------------------


class TestWardenLifecycle:
    async def test_registered_component_starts_and_stops(self, tmp_path) -> None:
        warden = Warden(_config(tmp_path), trust_root={}, clock=FakeClock())
        component = RecordingComponent()
        warden.register_component("dummy", component)
        task = asyncio.create_task(warden.run())
        await _wait_until(lambda: component.started)
        assert warden._component_states()["dummy"] == "running"

        warden.stop()
        await task
        assert component.stopped

    async def test_component_death_reflects_in_health(self, tmp_path) -> None:
        warden = Warden(_config(tmp_path), trust_root={}, clock=FakeClock())
        failing = FailingComponent()
        warden.register_component("failing", failing)
        task = asyncio.create_task(warden.run())
        await _wait_until(lambda: failing.started)

        status, payload = warden._health_payload()
        assert status == 503
        assert payload["status"] == "unhealthy"
        assert payload["components"]["failing"] == "failed"

        warden.stop()
        await task

    async def test_stop_does_not_tighten_protection(self, tmp_path) -> None:
        """Shutdown must not drop decision protections.

        Stopping is not a control-plane signal: what the envelope allowed
        stays allowed in the surviving state, and reversing live actions is
        undo work with its own reasons — never a side effect of shutdown.
        Asserted against the real decision vocabulary, not a mock.
        """
        key = make_policy_key()
        parsed = load_policy_pack(
            make_pack_bytes(key), make_root(key), now=NOW, state=None
        )
        assert parsed.ok, parsed.errors
        envelope = parsed.pack.autonomy_envelope

        warden = Warden(_config(tmp_path), trust_root={}, clock=FakeClock())
        protections_before = (
            envelope.require_reversible,
            frozenset(REVERSIBLE_ACTION_TYPES),
        )
        warden.stop()
        await asyncio.create_task(warden.run())
        assert (
            envelope.require_reversible,
            frozenset(REVERSIBLE_ACTION_TYPES),
        ) == protections_before
        assert REVERSIBLE_ACTION_TYPES == frozenset({"block_ip"})

    async def test_health_counts_metrics_server_component(self, tmp_path) -> None:
        warden = Warden(_config(tmp_path), trust_root={}, clock=FakeClock())
        task = asyncio.create_task(warden.run())
        await _wait_until(
            lambda: warden._component_states().get("metrics") == "running"
        )
        status, payload = warden._health_payload()
        assert status == 200
        assert payload["status"] == "healthy"
        warden.stop()
        await task


# --------------------------------------------------------------------------
# Status payload — the operator's single status view
# --------------------------------------------------------------------------


class TestStatusPayload:
    async def test_status_payload_shape(self, tmp_path) -> None:
        clock = FakeClock()
        warden = Warden(_config(tmp_path), trust_root={}, clock=clock)
        task = asyncio.create_task(warden.run())
        await _wait_until(
            lambda: warden._component_states().get("metrics") == "running"
        )
        status = warden._status_payload()
        assert status["node_id"] == "wn-test000"
        assert status["mode"] == "BOOTSTRAP"
        assert status["policy_version"] is None
        assert status["journal"] == {"last_seq": 0, "head": None, "poisoned": None}
        assert status["executors"] == []
        assert status["live_actions"] == 0
        assert status["health"]["status"] == "healthy"
        warden.stop()
        await task


# --------------------------------------------------------------------------
# No-database hygiene — the edge-deployability contract, at test speed
# --------------------------------------------------------------------------

_FORBIDDEN_ROOTS = frozenset(
    {
        "sqlalchemy",
        "psycopg2",
        "psycopg",
        "asyncpg",
        "redis",
        "arq",
        "pydantic_settings",
    }
)

_FORBIDDEN_PREFIXES = (
    "core.storage",
    "core.config",
    "core.secrets",
    "core.agents",
    "core.api",
    "core.response",
    "core.llm",
    "core.federation",
    "core.ingestion",
    "core.integrations",
    "core.workflows",
)


def _forbidden_reason(module: str) -> str | None:
    if module.split(".")[0] in _FORBIDDEN_ROOTS:
        return module
    for prefix in _FORBIDDEN_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return module
    return None


class TestNoDatabaseDependencies:
    def test_warden_imports_no_storage_or_queue_modules(self) -> None:
        warden_dir = Path(warden_main.__file__).parent
        offenders: list[str] = []
        for py_file in sorted(warden_dir.glob("*.py")):
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        reason = _forbidden_reason(alias.name)
                        if reason:
                            offenders.append(
                                f"{py_file.name}:{node.lineno} import {reason}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    reason = _forbidden_reason(node.module or "")
                    if reason:
                        offenders.append(f"{py_file.name}:{node.lineno} from {reason}")
        assert offenders == []


# --------------------------------------------------------------------------
# Metrics server — real HTTP on ephemeral ports
# --------------------------------------------------------------------------


class TestMetricsServer:
    async def _serve_and_get(self, tmp_path: Path, path: str) -> tuple[int, bytes]:
        clock = FakeClock()
        config = _config(tmp_path)
        warden = Warden(config, trust_root={}, clock=clock)
        shutdown = asyncio.Event()
        task = asyncio.create_task(warden.metrics_server.run(shutdown))
        try:
            target = (
                f"http://127.0.0.1:{config.metrics_port}/metrics"
                if path == "/metrics"
                else f"http://127.0.0.1:{config.health_port}{path}"
            )
            # Poll until the site is bound — TCPSite.start happens inside
            # the task's first steps.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 3.0
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.get(target) as response:
                            return response.status, await response.read()
                    except aiohttp.ClientConnectorError:
                        if loop.time() > deadline:
                            raise
                        await asyncio.sleep(0.05)
        finally:
            shutdown.set()
            await task

    async def test_health_endpoint_serves_200(self, tmp_path) -> None:
        status, body = await self._serve_and_get(tmp_path, "/health")
        assert status == 200
        assert b"healthy" in body

    async def test_status_endpoint_serves_json(self, tmp_path) -> None:
        status, body = await self._serve_and_get(tmp_path, "/status")
        assert status == 200
        assert b"node_id" in body

    async def test_metrics_endpoint_serves_prometheus_text(self, tmp_path) -> None:
        status, body = await self._serve_and_get(tmp_path, "/metrics")
        assert status == 200
        assert b"warden_" in body


# --------------------------------------------------------------------------
# build_warden — env to process assembly
# --------------------------------------------------------------------------


class TestBuildWarden:
    def test_build_warden_from_env(self, tmp_path, monkeypatch) -> None:
        key = make_policy_key()
        root_path = _write_root_file(tmp_path, key)
        monkeypatch.setenv("WARDEN_CONTROL_PLANE_URL", "http://127.0.0.1:6987")
        monkeypatch.setenv("WARDEN_NODE_ID", "wn-env0000")
        monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("WARDEN_TRUST_ROOT_PATH", str(root_path))

        config = WardenConfig.from_env()
        assert config.validate() == ()
        root = load_trust_root(config.trust_root_path, now=NOW)
        warden = warden_main.build_warden(config, trust_root=root)
        assert isinstance(warden, Warden)
        assert warden.config.node_id == "wn-env0000"
