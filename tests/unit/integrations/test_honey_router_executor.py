"""Executor-dispatch tests for the honey_route action type.

The isolate_host rule as tests: with no enforcement backend configured
(the default install), an approved honey_route must record a structured
failure — never a fabricated success. The integration-enabled gate is
patched at ``core.config`` (the executor imports it inside the method),
and the enforcement module is patched at the route-module seam.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import core.config as core_config
from core.response.autonomous_response_service import AutonomousResponseService


def _action(parameters=None, target="203.0.113.7"):
    return SimpleNamespace(
        action_id="action-20261009-200102-ab12cd",
        action_type="honey_route",
        target=target,
        parameters=parameters
        or {"decoy_id": "decoy-ssh-01", "session_ttl_seconds": 3600},
    )


def _enabled(monkeypatch, value=True):
    monkeypatch.setattr(core_config, "is_integration_enabled", lambda name: value)


class TestHonestFailureWithoutBackend:
    def test_disabled_integration_is_the_structured_unsupported_failure(
        self, monkeypatch
    ):
        _enabled(monkeypatch, value=False)
        result = AutonomousResponseService()._execute_honey_route(_action())
        assert result == {
            "success": False,
            "error": "unsupported_action_type",
            "message": "No enforcement backend is configured for honey-routing",
        }

    def test_broken_enforcement_module_is_caught_not_raised(self, monkeypatch):
        # The executor must never let an import error escape as a crash —
        # it reports the failure into execution_result like any other.
        # Poison the package (not the submodule): an already-imported
        # submodule binds via the package attribute, but a None package
        # entry makes the from-import itself raise ImportError.
        _enabled(monkeypatch, value=True)
        monkeypatch.setitem(sys.modules, "core.integrations.honey_router", None)
        result = AutonomousResponseService()._execute_honey_route(_action())
        assert result["success"] is False
        assert "unavailable" in result["error"]

    def test_action_without_decoy_id_is_a_named_failure(self, monkeypatch):
        _enabled(monkeypatch, value=True)
        result = AutonomousResponseService()._execute_honey_route(
            _action(parameters={"session_ttl_seconds": 3600})
        )
        assert result["success"] is False
        assert result["error"] == "missing_decoy_id"


class TestDispatchToBackend:
    def test_enabled_action_dispatches_with_registry_params(self, monkeypatch):
        _enabled(monkeypatch, value=True)
        seen = {}

        def fake_route(attacker_ip, decoy_id, ttl_seconds=None):
            seen["attacker_ip"] = attacker_ip
            seen["decoy_id"] = decoy_id
            seen["ttl_seconds"] = ttl_seconds
            return {"success": True, "policy": "vigil-honey-x"}

        import core.integrations.honey_router.route as hr_module

        monkeypatch.setattr(hr_module, "route", fake_route)
        result = AutonomousResponseService()._execute_honey_route(_action())
        assert result == {"success": True, "policy": "vigil-honey-x"}
        assert seen == {
            "attacker_ip": "203.0.113.7",
            "decoy_id": "decoy-ssh-01",
            "ttl_seconds": 3600,
        }

    def test_backend_failure_bubbles_as_the_recorded_result(self, monkeypatch):
        _enabled(monkeypatch, value=True)
        import core.integrations.honey_router.route as hr_module

        monkeypatch.setattr(
            hr_module,
            "route",
            lambda attacker_ip, decoy_id, ttl_seconds=None: {
                "success": False,
                "error": "cilium_crd_unavailable",
                "message": "does not run Cilium",
            },
        )
        result = AutonomousResponseService()._execute_honey_route(_action())
        assert result["success"] is False
        assert result["error"] == "cilium_crd_unavailable"
