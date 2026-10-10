"""Executor registry and bundle-bound dispatch suite.

The acceptance bar for T4: actions are typed and capped by the signed
bundle — an executor cannot act outside allowed_actions. BundleBound is the
enforcement point, so its suite proves the refusals (no bundle, pair not
allowed, namespace outside scope) and the caps (TTL capped, signed namespaces
passed through) without any real containment mechanism.
"""

from __future__ import annotations

import asyncio

from services.edge.executors.registry import (
    ActionResult,
    BundleBound,
    ExecutorRegistry,
    allowed_action,
)
from services.edge.gate.gate import Action
from services.edge.tests._fixtures import make_bundle


class FakeExecutor:
    name = "fake"
    action_types = frozenset({"block_ip"})

    def __init__(self, *, result: ActionResult | None = None) -> None:
        self.result = result or ActionResult(success=True, ref="fake-ref-1")
        self.applied: list[tuple[Action, int, tuple[str, ...]]] = []
        self.reverted: list[str] = []

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        self.applied.append((action, ttl_seconds, namespaces))
        return self.result

    async def revert(self, ref: str) -> ActionResult:
        self.reverted.append(ref)
        return self.result


class K8sShapedInner:
    """Stands in for the k8s executor: records TTLs and scopes instead of
    touching an API."""

    name = "k8s_networkpolicy"
    action_types = frozenset({"block_ip"})

    def __init__(self) -> None:
        self.ttls: list[int] = []
        self.scopes: list[tuple[str, ...]] = []

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        self.ttls.append(ttl_seconds)
        self.scopes.append(namespaces)
        return ActionResult(success=True, ref='{"networkpolicies": []}')

    async def revert(self, ref: str) -> ActionResult:
        return ActionResult(success=True, ref=ref)


def block_ip(executor: str = "fake", target: str = "203.0.113.55") -> Action:
    return Action(
        action_type="block_ip", executor=executor, target=target, ttl_seconds=900
    )


def test_registry_keys_by_action_type_and_executor() -> None:
    registry = ExecutorRegistry()
    executor = FakeExecutor()
    registry.register(executor)

    assert registry.lookup("block_ip", "fake") is executor
    assert registry.lookup("block_ip", "nftables") is None
    assert registry.lookup("block_domain", "fake") is None
    assert registry.registered() == [("block_ip", "fake")]


def test_allowed_action_finds_the_signed_pair() -> None:
    bundle = make_bundle()
    entry = allowed_action(bundle, "block_ip", "nftables")

    assert entry is not None
    assert entry.max_ttl_seconds == 3600
    assert allowed_action(bundle, "block_ip", "k8s_networkpolicy") is not None
    assert allowed_action(bundle, "block_domain", "k8s_networkpolicy") is None


def test_bundle_bound_without_bundle_fails_closed() -> None:
    inner = FakeExecutor()
    bound = BundleBound(inner, lambda: None)

    result = asyncio.run(bound.apply(block_ip(), 900))

    assert result.success is False
    assert result.error == "no_active_bundle"
    assert inner.applied == []


def test_bundle_bound_refuses_pair_not_in_allowed_actions() -> None:
    inner = FakeExecutor()
    # The fixture bundle allows block_ip for nftables/k8s only — not "fake".
    bound = BundleBound(inner, make_bundle)

    result = asyncio.run(bound.apply(block_ip(executor="fake"), 900))

    assert result.success is False
    assert result.error == "not_in_allowed_actions:block_ip/fake"
    assert inner.applied == []


def test_bundle_bound_caps_ttl_to_the_signed_maximum() -> None:
    # The fixture bundle signs max_ttl_seconds=3600 on the nftables pair.
    inner = FakeExecutor()
    bound = BundleBound(inner, make_bundle)

    result = asyncio.run(bound.apply(block_ip(executor="nftables"), 7200))
    assert result.success is True
    assert [ttl for _, ttl, _ in inner.applied] == [3600]

    asyncio.run(bound.apply(block_ip(executor="nftables"), 900))
    assert inner.applied[-1][1] == 900  # under the cap, passed through untouched


def test_bundle_bound_passes_signed_namespaces_through() -> None:
    inner = K8sShapedInner()
    bound = BundleBound(inner, make_bundle)

    asyncio.run(bound.apply(block_ip(executor="k8s_networkpolicy"), 900))

    # The fixture bundle signs ["prod", "staging"] for this pair.
    assert inner.scopes == [("prod", "staging")]


def test_bundle_bound_refuses_namespace_outside_bundle_scope() -> None:
    inner = K8sShapedInner()
    bound = BundleBound(inner, make_bundle)

    result = asyncio.run(
        bound.apply(
            block_ip(executor="k8s_networkpolicy"), 900, namespaces=("kube-system",)
        )
    )

    assert result.success is False
    assert result.error == "namespace_outside_bundle_scope"
    assert inner.scopes == []


def test_bundle_bound_revert_delegates() -> None:
    inner = FakeExecutor()
    bound = BundleBound(inner, make_bundle)

    result = asyncio.run(bound.revert("fake-ref-1"))

    assert result.success is True
    assert inner.reverted == ["fake-ref-1"]
