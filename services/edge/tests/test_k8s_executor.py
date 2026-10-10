"""K8s NetworkPolicy executor suite against a fake API server.

The acceptance bar for T4's cluster executor: apply → present, revoke →
absent, idempotent re-apply — proven against an in-memory API server backed
by ``httpx.MockTransport``, plus the fail-closed refusals (non-IP targets,
empty namespace scope, unreadable token). No cluster, no kubectl, no
network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from services.edge.executors.k8s_networkpolicy import (
    K8sExecutorConfig,
    K8sNetworkPolicyExecutor,
    policy_name,
)
from services.edge.gate.gate import Action
from services.edge.journal.journal import canonical_bytes


class FakeK8sApi:
    """The minimum API server the executor speaks to: namespaced
    NetworkPolicy create-or-update, read, delete — and nothing else. The
    store doubles as the present/absent oracle."""

    def __init__(self, *, fail_namespace: str | None = None) -> None:
        self.store: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        # Every mutating call touching this namespace gets a 403 — the
        # scoped-RBAC refusal shape.
        self.fail_namespace = fail_namespace

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        self.calls.append((method, path))
        if path.startswith("/apis/networking.k8s.io/v1/namespaces/"):
            remainder = path.removeprefix("/apis/networking.k8s.io/v1/namespaces/")
            parts = remainder.split("/")
            if len(parts) == 3 and parts[1] == "networkpolicies":
                namespace, _, name = parts
                identity = f"{namespace}/{name}"
                if method == "PUT":
                    if namespace == self.fail_namespace:
                        return httpx.Response(403, json={"reason": "Forbidden"})
                    body = json.loads(request.content)
                    code = 200 if identity in self.store else 201
                    self.store[identity] = body
                    return httpx.Response(code, json=body)
                if method == "GET":
                    body = self.store.get(identity)
                    if body is None:
                        return httpx.Response(404, json={"reason": "NotFound"})
                    return httpx.Response(200, json=body)
                if method == "DELETE":
                    if identity in self.store:
                        del self.store[identity]
                        return httpx.Response(200, json={})
                    return httpx.Response(404, json={"reason": "NotFound"})
        return httpx.Response(404, json={"reason": "NotFound"})

    def get(self, namespace: str, name: str) -> dict | None:
        return self.store.get(f"{namespace}/{name}")


def block_action(target: str = "203.0.113.55") -> Action:
    return Action(
        action_type="block_ip",
        executor="k8s_networkpolicy",
        target=target,
        ttl_seconds=900,
    )


def make_executor(api: FakeK8sApi, tmp_path: Path) -> K8sNetworkPolicyExecutor:
    token_file = tmp_path / "token"
    token_file.write_text("sa-token-abc\n")
    config = K8sExecutorConfig(
        api_url="https://api.fake.cluster:6443",
        token_file=token_file,
        ca_file=tmp_path / "ca.crt",  # unused by the mock transport
    )
    return K8sNetworkPolicyExecutor(config, transport=httpx.MockTransport(api.handler))


def test_apply_makes_the_policy_present_in_every_signed_namespace(
    tmp_path: Path,
) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    result = asyncio.run(
        executor.apply(block_action(), 900, namespaces=("prod", "staging"))
    )

    assert result.success is True
    assert result.ref is not None
    refs = json.loads(result.ref)["networkpolicies"]
    expected = sorted(
        f"{ns}/{policy_name('203.0.113.55')}" for ns in ("prod", "staging")
    )
    assert sorted(refs) == expected
    for namespace in ("prod", "staging"):
        body = api.get(namespace, policy_name("203.0.113.55"))
        assert body is not None, f"policy absent in {namespace}"
        assert body["spec"]["policyTypes"] == ["Egress"]
        ip_block = body["spec"]["egress"][0]["to"][0]["ipBlock"]
        assert ip_block["except"] == ["203.0.113.55/32"]
        assert body["metadata"]["labels"]["vigil.ai/edge-managed"] == "true"


def test_apply_writes_allow_all_except_target(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))

    stored = api.get("prod", policy_name("203.0.113.55"))
    assert stored is not None
    block = stored["spec"]["egress"][0]["to"][0]["ipBlock"]
    # Allow every destination; deny only the target at its full prefix.
    assert block["cidr"] == "0.0.0.0/0"
    assert block["except"] == ["203.0.113.55/32"]


def test_revoke_removes_the_policy(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)
    result = asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))
    assert result.ref is not None
    assert api.get("prod", policy_name("203.0.113.55")) is not None

    revert = asyncio.run(executor.revert(result.ref))

    assert revert.success is True
    assert api.get("prod", policy_name("203.0.113.55")) is None


def test_reapply_is_idempotent_same_object_rewritten(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    first = asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))
    second = asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))

    assert first.success and second.success
    assert first.ref == second.ref  # deterministic identity, not a second object
    assert len(api.store) == 1  # one policy object, updated in place
    puts = [c for c in api.calls if c[0] == "PUT"]
    assert len(puts) == 2  # both applies actually round-tripped


def test_revert_of_already_absent_policy_succeeds(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)
    ref = json.dumps({"networkpolicies": ["prod/" + policy_name("203.0.113.55")]})

    result = asyncio.run(executor.revert(ref))

    assert result.success is True  # 404 on delete = already reverted


def test_non_ip_target_is_refused_before_any_request(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    result = asyncio.run(
        executor.apply(
            block_action(target="203.0.113.55; nft delete table inet filter"),
            900,
            namespaces=("prod",),
        )
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("invalid_target")
    assert api.calls == []  # nothing left the process


def test_empty_namespace_scope_is_refused(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    result = asyncio.run(executor.apply(block_action(), 900))

    assert result.success is False
    assert result.error == "no_namespaces_in_scope"
    assert api.calls == []


def test_unreadable_token_fails_closed(tmp_path: Path) -> None:
    api = FakeK8sApi()
    config = K8sExecutorConfig(
        api_url="https://api.fake.cluster:6443",
        token_file=tmp_path / "missing-token",
        ca_file=tmp_path / "ca.crt",
    )
    executor = K8sNetworkPolicyExecutor(
        config, transport=httpx.MockTransport(api.handler)
    )

    result = asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))

    assert result.success is False
    assert result.error == "token_unreadable"
    assert api.calls == []


def test_partial_apply_failure_fails_the_whole_apply(tmp_path: Path) -> None:
    api = FakeK8sApi(fail_namespace="staging")  # RBAC refusal on one namespace
    executor = make_executor(api, tmp_path)

    result = asyncio.run(
        executor.apply(block_action(), 900, namespaces=("prod", "staging"))
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("api_error:403:staging/")
    # A partial apply must not be reported as success: prod landed, but the
    # ref is only produced on a fully successful apply, so the reaper will
    # never be told a block exists that it cannot revert as a unit.
    assert api.get("prod", policy_name("203.0.113.55")) is not None


def test_policy_name_is_dns1123_and_deterministic() -> None:
    name1 = policy_name("203.0.113.55")
    name2 = policy_name("203.0.113.55")
    assert name1 == name2
    assert name1.startswith("vigil-edge-block-")
    assert len(name1) <= 63
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert set(name1) <= allowed


def test_ipv6_target_gets_v6_block_shape(tmp_path: Path) -> None:
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)

    result = asyncio.run(
        executor.apply(block_action(target="2001:db8::1"), 900, namespaces=("prod",))
    )

    assert result.success is True
    stored = api.get("prod", policy_name("2001:db8::1"))
    assert stored is not None
    block = stored["spec"]["egress"][0]["to"][0]["ipBlock"]
    assert block["cidr"] == "::/0"
    assert block["except"] == ["2001:db8::1/128"]


def test_canonical_ref_shape_matches_journal_wire_format(tmp_path: Path) -> None:
    """The ref the journal stores must round-trip through the record's
    canonical JSON serializer (sort_keys + compact separators)."""
    api = FakeK8sApi()
    executor = make_executor(api, tmp_path)
    result = asyncio.run(executor.apply(block_action(), 900, namespaces=("prod",)))
    payload = {"ref": result.ref}
    canonical = canonical_bytes(
        {
            "local_sequence": 1,
            "node_id": "n",
            "boot_id": "b",
            "timestamp": "t",
            "kind": "decision",
            "payload": payload,
            "prev_hash": "0",
        }
    )
    assert b"networkpolicies" in canonical
