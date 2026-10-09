"""Executor interface and registry.

v1 executors are network-scoped and reversible: ``k8s_networkpolicy`` (cluster
mode) and ``nftables`` (gateway mode) ship in the executors deliverable. The
daemon routes every gate-approved action through this registry, keyed by
``(action_type, executor)`` — the same pair the signed bundle's
``allowed_actions`` names.

An action with no registered executor is journaled as an ``execute_failed``
record naming the reason — recorded, never silently faked. The house
precedent is the central pipeline's ``isolate_host`` stub, which reports
``unsupported_action_type`` rather than pretend a containment happened.

Dispatch is bundle-bounded: executors register wrapped in :class:`BundleBound`,
which re-checks the live signed bundle at the boundary. The gate only emits
bundle actions, but the bundle can change between the gate's decision and the
executor's call, so the wrapper — not the executor — is the last check that
the (action_type, executor) pair, the namespace scope, and the TTL are all
inside what the operator signed. Out-of-bounds dispatch fails closed with a
journaled error; it never reaches the mechanism.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from services.edge.gate.gate import Action
    from services.edge.policy.model import AllowedAction, Bundle


@dataclass(frozen=True)
class ActionResult:
    success: bool
    ref: str | None = None
    error: str | None = None


@runtime_checkable
class Executor(Protocol):
    """One reversible containment mechanism. apply() and revert() are async:
    both executors wait on a remote API (k8s) or a host command (nftables).
    ``namespaces`` is the bundle's signed scope for the pair — executors never
    widen it."""

    name: str
    action_types: frozenset[str]

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult: ...

    async def revert(self, ref: str) -> ActionResult: ...


def allowed_action(
    bundle: Bundle, action_type: str, executor_name: str
) -> AllowedAction | None:
    """The bundle's allowed_actions entry for an (action_type, executor) pair,
    or None when the bundle does not allow it."""
    for entry in bundle.allowed_actions:
        if entry.action_type == action_type and entry.executor == executor_name:
            return entry
    return None


class BundleBound:
    """Bundle-bounded dispatch wrapper.

    apply() refuses — fails closed, executor untouched — unless the live
    bundle allows the pair, and caps the TTL and namespace scope to the
    signed entry before delegating. revert() delegates untouched: undoing a
    block is never out of bounds.
    """

    def __init__(self, inner: Executor, bundle_fn: Callable[[], Bundle | None]) -> None:
        self._inner = inner
        self._bundle_fn = bundle_fn

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def action_types(self) -> frozenset[str]:
        return self._inner.action_types

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        bundle = self._bundle_fn()
        if bundle is None:
            return ActionResult(success=False, error="no_active_bundle")
        signed = allowed_action(bundle, action.action_type, action.executor)
        if signed is None:
            return ActionResult(
                success=False,
                error=f"not_in_allowed_actions:{action.action_type}/{action.executor}",
            )
        scope = namespaces or signed.namespaces
        if signed.namespaces and not set(scope) <= set(signed.namespaces):
            return ActionResult(success=False, error="namespace_outside_bundle_scope")
        capped = ttl_seconds
        if signed.max_ttl_seconds is not None:
            capped = min(capped, signed.max_ttl_seconds)
        return await self._inner.apply(action, capped, namespaces=scope)

    async def revert(self, ref: str) -> ActionResult:
        return await self._inner.revert(ref)


class ExecutorRegistry:
    """Keyed by ``(action_type, executor_name)`` so one executor may serve
    ``block_ip`` while another serves ``block_domain``."""

    def __init__(self) -> None:
        self._executors: dict[tuple[str, str], Executor] = {}

    def register(self, executor: Executor) -> None:
        for action_type in executor.action_types:
            self._executors[(action_type, executor.name)] = executor

    def lookup(self, action_type: str, executor_name: str) -> Executor | None:
        return self._executors.get((action_type, executor_name))

    def registered(self) -> list[tuple[str, str]]:
        return sorted(self._executors)
