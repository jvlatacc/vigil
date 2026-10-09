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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from services.edge.gate.gate import Action


@dataclass(frozen=True)
class ActionResult:
    success: bool
    ref: str | None = None
    error: str | None = None


@runtime_checkable
class Executor(Protocol):
    """One reversible containment mechanism. apply() and revert() are async:
    both executors wait on a remote API (k8s) or a host command (nftables)."""

    name: str
    action_types: frozenset[str]

    async def apply(self, action: Action, ttl_seconds: int) -> ActionResult: ...

    async def revert(self, ref: str) -> ActionResult: ...


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
