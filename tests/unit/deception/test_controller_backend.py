"""ControllerBackend — the daemon's client for the decoy-controller service.

Pure unit: the HTTP helpers are faked at the tool-module boundary, so every
credential, cooldown, and shape rule runs without a network. The service's
own HTTP behavior is covered by tests/integration/test_decoy_controller_api.py.
"""

import pytest

from core.deception import backends as backends_module
from core.deception.backends import (
    DECOY_VENDOR_ID,
    ControllerBackend,
    SteerScope,
    build_backend,
    set_vendor_error_hooks,
)
from tests.unit.deception.fixtures import ATTACKER, VICTIM

SCOPE: SteerScope = {
    "source_ip": ATTACKER,
    "destination_ips": [VICTIM],
    "ports": [445, 3389],
    "ttl_seconds": 3600,
    "lease_id": "lease-abc123",
}

CREDS = {"base_url": "http://decoy-controller:8484", "api_token": "secret"}


@pytest.fixture(autouse=True)
def _no_env_credentials(monkeypatch):
    """Never let a developer's real integration config leak into these tests."""
    monkeypatch.setattr(backends_module, "_credentials", lambda: None)
    monkeypatch.setattr(backends_module, "_record_error_hook", None)
    monkeypatch.setattr(backends_module, "_cooling_down_hook", None)


@pytest.fixture
def wired():
    """Hook fakes with a recording, like the daemon's vendor_errors pair."""
    recorded: list = []

    def record_error(vendor: str, status: int) -> None:
        recorded.append((vendor, status))

    cooling = {"active": False}

    def cooling_down(vendor: str) -> bool:
        return cooling["active"]

    set_vendor_error_hooks(record_error, cooling_down)
    yield {"recorded": recorded, "cooling": cooling}
    set_vendor_error_hooks(None, None)


def _fake_steer(monkeypatch, result, calls=None):
    from core.integrations.decoy_controller import tool as controller_tool

    def fake(base_url, api_token, lease_id, source_ip, destinations, ports, ttl):
        if calls is not None:
            calls.append(
                {
                    "base_url": base_url,
                    "api_token": api_token,
                    "lease_id": lease_id,
                    "source_ip": source_ip,
                    "destination_ips": list(destinations),
                    "ports": list(ports),
                    "ttl_seconds": ttl,
                }
            )
        return result

    monkeypatch.setattr(controller_tool, "_steer", fake)


class TestBuildBackend:
    def test_controller_builds_now(self):
        assert isinstance(build_backend("controller"), ControllerBackend)

    def test_dry_run_still_shipped_default(self):
        assert type(build_backend("dry_run")).__name__ == "DryRunBackend"

    def test_unknown_backend_refuses_at_construction(self):
        with pytest.raises(ValueError, match="[Uu]nknown"):
            build_backend("ssh-tunnel")


class TestCredentials:
    async def test_unconfigured_backend_fails_without_raising(self):
        # Fail-open: an unconfigured controller must look like any other
        # steering failure, never an exception that escapes the executor.
        result = await ControllerBackend().steer(SCOPE)
        assert result["success"] is False
        assert result["error"] == "decoy_controller_not_configured"

    async def test_unconfigured_unsteer_fails_without_raising(self):
        result = await ControllerBackend().unsteer("lease-abc123", None)
        assert result["success"] is False
        assert result["error"] == "decoy_controller_not_configured"

    async def test_explicit_credentials_beat_the_integration_slice(self, monkeypatch):
        calls: list = []
        _fake_steer(monkeypatch, {"success": True}, calls)
        backend = ControllerBackend(base_url="http://other:1", api_token="t2")
        result = await backend.steer(SCOPE)
        assert result["success"] is True
        assert calls[0]["base_url"] == "http://other:1"
        assert calls[0]["api_token"] == "t2"


class TestSteer:
    async def test_scope_reaches_the_helper_untouched(self, monkeypatch):
        calls: list = []
        _fake_steer(monkeypatch, {"success": True}, calls)
        backend = ControllerBackend(base_url=CREDS["base_url"], api_token="secret")
        await backend.steer(SCOPE)
        sent = calls[0]
        assert sent["lease_id"] == "lease-abc123"
        assert sent["source_ip"] == ATTACKER
        assert sent["destination_ips"] == [VICTIM]
        assert sent["ports"] == [445, 3389]
        assert sent["ttl_seconds"] == 3600

    async def test_helpers_never_run_on_the_event_loop_thread(self, monkeypatch):
        # The REST helpers are sync (httpx); the backend must ship them to a
        # worker thread or every steering call blocks the daemon's loop.
        import threading

        from core.integrations.decoy_controller import tool as controller_tool

        seen_threads = []

        def fake(base_url, api_token, *args):
            seen_threads.append(threading.current_thread())
            return {"success": True}

        monkeypatch.setattr(controller_tool, "_steer", fake)
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        await backend.steer(SCOPE)
        assert seen_threads[0] is not threading.main_thread()


class TestCooldown:
    async def test_cooling_down_refuses_steer_without_touching_the_controller(
        self, wired, monkeypatch
    ):
        wired["cooling"]["active"] = True
        called = []

        def must_not_run(*args):
            called.append(args)
            return {"success": True}

        from core.integrations.decoy_controller import tool as controller_tool

        monkeypatch.setattr(controller_tool, "_steer", must_not_run)
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        result = await backend.steer(SCOPE)
        assert called == []
        assert result["success"] is False
        assert result["error"] == "decoy_controller_cooling_down"

    @pytest.mark.parametrize("status", [401, 403, 429])
    async def test_tracked_failures_feed_the_bookkeeping(
        self, wired, monkeypatch, status
    ):
        _fake_steer(
            monkeypatch,
            {"success": False, "status_code": status, "error": "rejected"},
        )
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        await backend.steer(SCOPE)
        assert wired["recorded"] == [(DECOY_VENDOR_ID, status)]

    async def test_success_and_untracked_failures_do_not_cool_down(
        self, wired, monkeypatch
    ):
        _fake_steer(monkeypatch, {"success": True, "status_code": 200})
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        await backend.steer(SCOPE)
        _fake_steer(monkeypatch, {"success": False, "status_code": 502})
        await backend.steer(SCOPE)
        assert wired["recorded"] == []

    async def test_unsteer_never_gates_on_cooldown(self, wired, monkeypatch):
        # Rollback is the safety path: it must always be attempted, even
        # while new steering is cooling down.
        wired["cooling"]["active"] = True
        from core.integrations.decoy_controller import tool as controller_tool

        monkeypatch.setattr(
            controller_tool,
            "_unsteer",
            lambda *args: {"success": True, "status_code": 200, "removed": True},
        )
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        result = await backend.unsteer("lease-abc123", "memory:lease-abc123")
        assert result["success"] is True


class TestStatus:
    async def test_status_finds_the_lease_in_reconcile_output(self, wired, monkeypatch):
        from core.integrations.decoy_controller import tool as controller_tool

        monkeypatch.setattr(
            controller_tool,
            "_reconcile",
            lambda *args: {
                "success": True,
                "rules": [{"lease_id": "lease-abc123", "ref": "memory:lease-abc123"}],
            },
        )
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        result = await backend.status("lease-abc123")
        assert result["success"] is True
        assert result["active"] is True
        assert result["rule"]["ref"] == "memory:lease-abc123"

    async def test_status_reports_inactive_for_unknown_lease(self, wired, monkeypatch):
        from core.integrations.decoy_controller import tool as controller_tool

        monkeypatch.setattr(
            controller_tool,
            "_reconcile",
            lambda *args: {"success": True, "rules": []},
        )
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        result = await backend.status("lease-gone")
        assert result["active"] is False

    async def test_status_failure_surfaces_as_a_failure(self, wired, monkeypatch):
        from core.integrations.decoy_controller import tool as controller_tool

        monkeypatch.setattr(
            controller_tool,
            "_reconcile",
            lambda *args: {"success": False, "status_code": 401, "error": "no"},
        )
        backend = ControllerBackend(base_url="http://x:1", api_token="t")
        result = await backend.status("lease-abc123")
        assert result["success"] is False
        assert wired["recorded"] == [(DECOY_VENDOR_ID, 401)]
