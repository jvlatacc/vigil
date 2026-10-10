"""Executor tests with a mocked Cloudflare HTTP surface.

The fake in ``FakeCloudflare`` is an in-memory ruleset: the built-ins'
REST calls (find / create / delete rules) run against it, and every
deletion is recorded so a test can assert that undo removed EXACTLY ONE
object — the property the whole executor contract rests on.

Also pins the hard spec decision: the fast-path executors ride their OWN
registry — ``execute_approved_actions`` (the 30 s approval sweep) must
keep refusing action types it does not know, which is every fastpath
type.
"""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import httpx
import pytest

from core.response.fastpath import executors
from core.response.fastpath.executors import (
    CloudflareChallengeExecutor,
    CloudflareRateLimitExecutor,
    EdgeContainmentExecutor,
    ExecutorError,
    ExecutorRegistry,
    LeaseSpec,
    default_registry,
    rule_name_for,
)

# The CI-safe test secret (not a credential: it signs fake requests only).
EDGE_SECRET = "test-signing-secret"


def _lease(
    action_type: str = "challenge",
    entity_type: str = "ip",
    entity_id: str = "203.0.113.7",
    lease_id: str = "lease-test-0001",
    **extra: Any,
) -> LeaseSpec:
    return LeaseSpec(
        lease_id=lease_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        ttl_seconds=300,
        observed={"severity": "critical", "confidence": 0.93},
        **extra,
    )


class FakeCloudflare:
    """In-memory account rulesets behind the REST calls."""

    def __init__(self) -> None:
        # phase -> {"id": ruleset_id, "rules": {rule_id: {"name": ...}}}
        self.rulesets: Dict[str, Dict[str, Any]] = {}
        self.deleted_rule_ids: List[str] = []
        self.delete_status_of: Dict[str, int] = {}
        self._next = 1

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        phase = url.split("/phases/")[1].split("/entrypoint")[0]
        ruleset = self.rulesets.get(phase)
        if ruleset is None:
            return httpx.Response(404, json={"success": False, "errors": []})
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "id": ruleset["id"],
                    "rules": list(ruleset["rules"].values()),
                },
            },
        )

    def post(
        self, url: str, json: Optional[Dict] = None, **kwargs: Any
    ) -> httpx.Response:
        phase = url.split("/phases/")[1].split("/entrypoint")[0]
        ruleset = self.rulesets.setdefault(phase, {"id": f"rs-{phase}", "rules": {}})
        rule_id = f"rule-{self._next}"
        self._next += 1
        ruleset["rules"][rule_id] = {"id": rule_id, "name": (json or {})["name"]}
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"id": ruleset["id"], "rule": {"id": rule_id}},
            },
        )

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        rule_id = url.rstrip("/").split("/")[-1]
        for ruleset in self.rulesets.values():
            if rule_id in ruleset["rules"]:
                del ruleset["rules"][rule_id]
                self.deleted_rule_ids.append(rule_id)
                self.delete_status_of[rule_id] = 200
                return httpx.Response(200, json={"success": True})
        # Nothing to delete — Cloudflare answers 404; undo treats it as
        # already-done success.
        self.delete_status_of[rule_id] = 404
        return httpx.Response(404, json={"success": False, "errors": []})

    def rule_count(self, phase: str) -> int:
        ruleset = self.rulesets.get(phase)
        return len(ruleset["rules"]) if ruleset else 0


class FakeEdge:
    """The operator-run endpoint: one object per apply, keyed by lease."""

    def __init__(self, *, omit_token: bool = False) -> None:
        self.objects: Dict[str, Dict] = {}  # undo_token -> body
        self.deleted_tokens: List[str] = []
        self.deleted_by_lease: List[str] = []
        self.omit_token = omit_token
        self.last_signature: Optional[str] = None
        self.last_timestamp: Optional[str] = None
        self.last_body: Optional[bytes] = None
        self._next = 1

    # POST /v1/containments
    def post(
        self, url: str, headers=None, content=None, **kwargs: Any
    ) -> httpx.Response:
        assert url.endswith("/v1/containments"), url
        self.last_signature = dict(headers or {}).get("X-Vigil-Signature")
        self.last_timestamp = dict(headers or {}).get("X-Vigil-Timestamp")
        self.last_body = content
        if self.omit_token:
            return httpx.Response(200, json={"ok": True})
        token = f"undo-{self._next}"
        self._next += 1
        self.objects[token] = {}
        return httpx.Response(200, json={"undo_token": token})

    # DELETE /v1/containments/{token} or /v1/containments/by-lease/{lease_id}
    def delete(
        self, url: str, headers=None, content=None, **kwargs: Any
    ) -> httpx.Response:
        self.last_signature = dict(headers or {}).get("X-Vigil-Signature")
        self.last_timestamp = dict(headers or {}).get("X-Vigil-Timestamp")
        self.last_body = content
        if "/by-lease/" in url:
            lease_id = url.rstrip("/").split("/by-lease/")[-1]
            self.deleted_by_lease.append(lease_id)
            return httpx.Response(200, json={"ok": True})
        token = url.rstrip("/").split("/")[-1]
        if token in self.objects:
            del self.objects[token]
            self.deleted_tokens.append(token)
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"ok": True})


@pytest.fixture
def fake_cf(monkeypatch: pytest.MonkeyPatch) -> FakeCloudflare:
    fake = FakeCloudflare()
    shim = SimpleNamespace(
        get=fake.get, post=fake.post, delete=fake.delete, Request=httpx.Request
    )
    monkeypatch.setattr(executors, "httpx", shim)
    monkeypatch.setattr(executors, "is_integration_enabled", lambda name: True)
    monkeypatch.setattr(
        executors,
        "get_integration_config",
        lambda name: {"api_token": "test-token", "account_id": "acct-1"},
    )
    return fake


@pytest.fixture
def fake_edge(monkeypatch: pytest.MonkeyPatch) -> FakeEdge:
    fake = FakeEdge()
    shim = SimpleNamespace(
        get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no GET")),
        post=fake.post,
        delete=fake.delete,
        Request=httpx.Request,
    )
    monkeypatch.setattr(executors, "httpx", shim)
    return fake


# ----------------------------------------------------------------------
# Cloudflare built-ins
# ----------------------------------------------------------------------


class TestCloudflareChallengeExecutor:
    async def test_apply_returns_an_undo_payload(self, fake_cf):
        payload = await CloudflareChallengeExecutor().apply(_lease())

        assert payload["rule_id"]
        assert payload["ruleset_id"]
        assert payload["rule_name"] == rule_name_for("lease-test-0001")
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 1

    async def test_reapply_with_same_lease_id_is_a_no_op(self, fake_cf):
        executor = CloudflareChallengeExecutor()

        first = await executor.apply(_lease())
        second = await executor.apply(_lease())

        assert first["rule_id"] == second["rule_id"]
        assert second.get("reapplied") is True
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 1

    async def test_undo_removes_exactly_one_object(self, fake_cf):
        executor = CloudflareChallengeExecutor()
        payload = await executor.apply(_lease())

        await executor.undo("lease-test-0001", payload)

        assert fake_cf.deleted_rule_ids == [payload["rule_id"]]
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 0

    async def test_repeated_undo_succeeds(self, fake_cf):
        executor = CloudflareChallengeExecutor()
        payload = await executor.apply(_lease())

        await executor.undo("lease-test-0001", payload)
        await executor.undo("lease-test-0001", payload)  # already gone

        assert fake_cf.delete_status_of[payload["rule_id"]] == 404
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 0

    async def test_undo_with_empty_payload_reconstructs_from_lease_id(self, fake_cf):
        """The crash-orphan path: the CAS never stored the undo token, so
        undo runs with an empty payload and must still find the rule —
        its name is derived from the lease id alone."""
        executor = CloudflareChallengeExecutor()
        await executor.apply(_lease())

        await executor.undo("lease-test-0001", {})

        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 0

    async def test_undo_touches_no_other_rule(self, fake_cf):
        """A sibling lease (another principal, same executor) must survive
        this lease's undo untouched."""
        executor = CloudflareChallengeExecutor()
        other_payload = await executor.apply(
            _lease(lease_id="lease-other", entity_id="198.51.100.9")
        )
        payload = await executor.apply(_lease())

        await executor.undo("lease-test-0001", payload)

        assert fake_cf.deleted_rule_ids == [payload["rule_id"]]
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 1
        assert other_payload["rule_id"] != payload["rule_id"]

    async def test_user_principal_is_refused_with_no_partial_state(self, fake_cf):
        with pytest.raises(ExecutorError, match="user"):
            await CloudflareChallengeExecutor().apply(
                _lease(entity_type="user", entity_id="j.vanlowe")
            )
        assert fake_cf.rule_count(executors.CF_PHASE_CUSTOM) == 0

    async def test_rate_limit_rule_is_created_in_its_own_phase(self, fake_cf):
        payload = await CloudflareRateLimitExecutor(
            requests_per_period=42, period_seconds=60
        ).apply(_lease(action_type="rate_limit"))

        assert payload["rule_id"]
        assert fake_cf.rule_count(executors.CF_PHASE_RATE_LIMIT) == 1


# ----------------------------------------------------------------------
# Edge containment — the signed endpoint contract
# ----------------------------------------------------------------------


class TestEdgeContainmentExecutor:
    def _executor(self) -> EdgeContainmentExecutor:
        return EdgeContainmentExecutor(
            base_url="https://edge.example.net", signing_secret=EDGE_SECRET
        )

    async def test_apply_returns_an_undo_token(self, fake_edge):
        payload = await self._executor().apply(
            _lease(action_type="tarpit", entity_type="ip")
        )

        assert payload["undo_token"] in fake_edge.objects
        assert fake_edge.last_signature

    async def test_apply_signature_verifies(self, fake_edge):
        await self._executor().apply(
            _lease(action_type="latency_injection", entity_type="ip")
        )

        assert fake_edge.last_timestamp and fake_edge.last_body
        expected = hmac.new(
            EDGE_SECRET.encode(),
            f"{fake_edge.last_timestamp}.".encode() + fake_edge.last_body,
            hashlib.sha256,
        ).hexdigest()
        assert fake_edge.last_signature == expected

    async def test_apply_refuses_unimplemented_verb(self, fake_edge):
        with pytest.raises(ExecutorError, match="challenge"):
            await self._executor().apply(_lease(action_type="challenge"))

    async def test_apply_without_undo_token_is_an_error(self, fake_edge):
        fake_edge.omit_token = True
        with pytest.raises(ExecutorError, match="undo_token"):
            await self._executor().apply(_lease(action_type="pin_session"))

    async def test_undo_by_token_removes_the_object(self, fake_edge):
        payload = await self._executor().apply(
            _lease(action_type="tarpit", entity_type="ip")
        )

        await self._executor().undo("lease-test-0001", payload)

        assert fake_edge.deleted_tokens == [payload["undo_token"]]
        assert not fake_edge.objects

    async def test_undo_with_empty_payload_uses_the_lease_id_route(self, fake_edge):
        await self._executor().apply(_lease(action_type="tarpit", entity_type="ip"))
        before = list(fake_edge.objects)

        await self._executor().undo("lease-test-0001", {})

        assert fake_edge.deleted_by_lease == ["lease-test-0001"]
        assert list(fake_edge.objects) == before

    async def test_repeated_undo_succeeds(self, fake_edge):
        payload = await self._executor().apply(
            _lease(action_type="tarpit", entity_type="ip")
        )
        await self._executor().undo("lease-test-0001", payload)
        await self._executor().undo("lease-test-0001", payload)  # 404 → ok


# ----------------------------------------------------------------------
# The registry
# ----------------------------------------------------------------------


class TestExecutorRegistry:
    def test_default_registry_offers_the_cloudflare_types(self, monkeypatch):
        monkeypatch.setattr(
            executors.EdgeContainmentExecutor,
            "from_settings",
            classmethod(lambda cls: None),
        )
        registry = default_registry()

        assert registry.get("challenge") is not None
        assert registry.get("rate_limit") is not None
        assert registry.get("tarpit") is None  # no endpoint configured

    def test_edge_executor_registers_all_three_verbs(self):
        registry = ExecutorRegistry()
        registry.register(
            EdgeContainmentExecutor(
                base_url="https://edge.example.net", signing_secret=EDGE_SECRET
            )
        )

        assert registry.action_types() == (
            "latency_injection",
            "pin_session",
            "tarpit",
        )

    def test_register_rejects_an_executor_without_action_types(self):
        registry = ExecutorRegistry()
        with pytest.raises(ExecutorError):
            registry.register(object())


# ----------------------------------------------------------------------
# The hard spec pin: the approval sweep must keep refusing fastpath types
# ----------------------------------------------------------------------


class TestApprovalSweepRefusesFastPathTypes:
    def test_execute_approved_actions_leaves_fastpath_types_alone(self):
        """``execute_approved_actions`` re-scans approved rows every 30 s.
        A fastpath type landing there would execute speculative effects on
        a cadence — the opposite of lease semantics. The sweep's unknown
        type refusal is the last line of defense; this test pins it."""
        from core.response.autonomous_response_service import (
            AutonomousResponseService,
        )

        lease_row = MagicMock()
        lease_row.action_id = "action-fastpath-1"
        lease_row.action_type = "rate_limit"  # a fastpath executor type
        lease_row.target = "203.0.113.7"
        lease_row.executed_at = None
        lease_row.requires_approval = True
        lease_row.approved_by = "operator"

        approvals = MagicMock()
        approvals.list_actions.return_value = [lease_row]
        service = AutonomousResponseService(approvals=approvals)

        results = service.execute_approved_actions()

        assert results == []  # unknown type → left for its own executor
        approvals.mark_executed.assert_not_called()
        approvals.mark_failed.assert_not_called()
