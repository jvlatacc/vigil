"""The enforcement adapters: what a speculative action does to the world.

The simulation adapter is the fast path's honesty point — it records intent,
touches nothing external, and marks itself so surfaces can label its rows.
The registry refuses an action type with no adapter loudly: a silent
fall-through to simulation would turn a wiring mistake into a phantom
containment. The Cloudflare adapter's vendor calls are mocked here; the REST
helpers they wrap are pinned in tests/unit/integrations/.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.response.approval_service import PendingAction
from core.response.fastpath.adapters import (
    CloudflareRateLimitAdapter,
    EnforcementRegistry,
    EnforceResult,
    SimulationAdapter,
    UnknownActionTypeError,
    build_registry,
)
from core.response.fastpath.config import FastPathConfig

pytestmark = pytest.mark.unit

TARGET = "203.0.113.7"


def _action(**overrides) -> PendingAction:
    values = dict(
        action_id="action-1",
        action_type="rate_limit",
        title="Speculative rate_limit: " + TARGET,
        description="speculative containment",
        target=TARGET,
        confidence=0.92,
        reason="fast_path.review_threshold=0.85 met (0.92)",
        evidence=[],
        created_at="2026-10-09T00:00:00+00:00",
        created_by="fast-path",
        requires_approval=False,
        status="speculative",
        parameters={"ttl_seconds": 600, "rollback": {}},
    )
    values.update(overrides)
    return PendingAction(**values)


def _block_all_http():
    """Every httpx verb raises: a simulation adapter must never call one."""
    blocker = MagicMock(side_effect=AssertionError("external I/O in a simulation"))
    return (
        patch("httpx.post", blocker),
        patch("httpx.get", blocker),
        patch("httpx.delete", blocker),
        patch("httpx.put", blocker),
        patch("httpx.request", blocker),
    )


class TestSimulationAdapter:
    def test_records_intent_without_external_io(self):
        adapter = SimulationAdapter()
        patches = _block_all_http()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = adapter.apply(_action(action_type="tarpit"))
        assert result.applied is True
        assert result.external_ref is None
        assert "tarpit" in result.detail

    def test_release_is_also_external_free(self):
        adapter = SimulationAdapter()
        patches = _block_all_http()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = adapter.release(_action(action_type="tarpit"))
        assert result.applied is True
        assert result.external_ref is None

    def test_is_deterministic(self):
        adapter = SimulationAdapter()
        first = adapter.apply(_action())
        second = adapter.apply(_action())
        assert first == second

    def test_marks_itself_and_covers_the_unenforced_types(self):
        adapter = SimulationAdapter()
        assert adapter.simulates is True
        assert adapter.applies_to() == frozenset(
            {"rate_limit", "tarpit", "session_pin", "latency_inject"}
        )


class TestRegistry:
    def test_refuses_an_unknown_action_type(self):
        registry = EnforcementRegistry({})
        with pytest.raises(UnknownActionTypeError) as exc:
            registry.adapter_for("isolate_host")
        assert "isolate_host" in str(exc.value)

    def test_default_mapping_puts_rate_limit_on_cloudflare(self):
        registry = build_registry(FastPathConfig(enabled=True))
        assert registry.adapter_for("rate_limit").simulates is False

    def test_default_mapping_puts_the_rest_on_simulation(self):
        registry = build_registry(FastPathConfig(enabled=True))
        for action_type in ("tarpit", "session_pin", "latency_inject"):
            assert registry.adapter_for(action_type).simulates is True

    def test_simulation_rate_limit_when_enforcement_is_not_configured(self):
        registry = build_registry(
            FastPathConfig(enabled=True, enforced_action_types=frozenset())
        )
        assert registry.adapter_for("rate_limit").simulates is True

    def test_refuses_enforced_types_with_no_real_adapter(self):
        with pytest.raises(UnknownActionTypeError) as exc:
            build_registry(
                FastPathConfig(
                    enabled=True, enforced_action_types=frozenset({"tarpit"})
                )
            )
        assert "tarpit" in str(exc.value)


def _cloudflare_enabled(monkeypatch, zone_id="zone-1"):
    monkeypatch.setattr("core.config.is_integration_enabled", lambda name: True)
    monkeypatch.setattr(
        "core.config.get_integration_config",
        lambda name: {"api_token": "tok", "zone_id": zone_id},
    )


class TestCloudflareRateLimitAdapter:
    def test_refuses_when_integration_disabled(self, monkeypatch):
        monkeypatch.setattr("core.config.is_integration_enabled", lambda name: False)
        result = CloudflareRateLimitAdapter().apply(_action())
        assert result.applied is False
        assert "refused" in result.detail

    def test_refuses_without_a_zone_id(self, monkeypatch):
        monkeypatch.setattr("core.config.is_integration_enabled", lambda name: True)
        monkeypatch.setattr(
            "core.config.get_integration_config",
            lambda name: {"api_token": "tok"},
        )
        result = CloudflareRateLimitAdapter().apply(_action())
        assert result.applied is False
        assert "zone_id" in result.detail

    def test_apply_carries_the_ttl_and_reason(self, monkeypatch):
        _cloudflare_enabled(monkeypatch)
        seen = {}

        def fake_apply(**kwargs):
            seen.update(kwargs)
            return {"success": True, "external_ref": "rs-1:rule-1", "status_code": 201}

        monkeypatch.setattr(
            "core.integrations.cloudflare.tool._ratelimit_apply_ip", fake_apply
        )
        result = CloudflareRateLimitAdapter().apply(_action())
        assert result.applied is True
        assert result.external_ref == "rs-1:rule-1"
        assert seen["mitigation_timeout"] == 600
        assert seen["ip"] == TARGET
        assert "review_threshold" in seen["reason"]

    def test_release_uses_the_recorded_external_ref(self, monkeypatch):
        _cloudflare_enabled(monkeypatch)
        seen = {}
        monkeypatch.setattr(
            "core.integrations.cloudflare.tool._ratelimit_release_ip",
            lambda **kwargs: seen.update(kwargs)
            or {"success": True, "status_code": 200},
        )
        action = _action(parameters={"rollback": {"external_ref": "rs-9:rule-7"}})
        result = CloudflareRateLimitAdapter().release(action)
        assert result.applied is True
        assert seen["external_ref"] == "rs-9:rule-7"

    def test_release_reports_a_missing_ref_as_refused(self, monkeypatch):
        _cloudflare_enabled(monkeypatch)
        monkeypatch.setattr(
            "core.integrations.cloudflare.tool._ratelimit_release_ip",
            lambda **kwargs: {"error": "external_ref required"},
        )
        result = CloudflareRateLimitAdapter().release(_action())
        assert result.applied is False
        assert "refused" in result.detail

    def test_vendor_rejection_is_never_applied(self, monkeypatch):
        _cloudflare_enabled(monkeypatch)
        monkeypatch.setattr(
            "core.integrations.cloudflare.tool._ratelimit_apply_ip",
            lambda **kwargs: {"success": False, "status_code": 400},
        )
        result = CloudflareRateLimitAdapter().apply(_action())
        assert result.applied is False
        assert result.external_ref is None

    def test_helper_error_is_a_refusal(self, monkeypatch):
        _cloudflare_enabled(monkeypatch)
        monkeypatch.setattr(
            "core.integrations.cloudflare.tool._ratelimit_apply_ip",
            lambda **kwargs: {"error": "mitigation_timeout required"},
        )
        result = CloudflareRateLimitAdapter().apply(_action(parameters={}))
        assert result.applied is False
        assert "mitigation_timeout" in result.detail


def test_enforce_result_records_the_three_fields():
    result = EnforceResult(applied=True, external_ref="rs-1:rule-1", detail="done")
    assert result.applied is True
    assert result.external_ref == "rs-1:rule-1"
    assert result.detail == "done"
