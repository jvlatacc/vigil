"""Local executors — the edge domain's only subprocess surface.

An enforcement decision leaves the pure world of ``decision.py`` here: an
executor turns an allowed ``block_ip`` into a real nftables element (or,
where the node cannot enforce, an honestly-labelled dry run). Three
invariants govern everything in this module:

**The registry is the allowlist.** Following the
``core/platform/service_manager.py`` pattern, ``executor_for`` is the only
dispatch door: an action type absent from the registry raises
``UnregisteredActionType`` before any executor — hence any subprocess — can
be reached. Nothing reads configuration to widen that set; it is exactly
what ``build_default_registry`` (or an embedding runtime) registered.

**A result records what actually happened.** The ``_execute_isolation``
lesson from ``core/response``: a success is never recorded for containment
that did not occur. Every ``ExecutionResult`` carries ``status`` (what the
call did), ``end_state`` (whether the target is blocked afterward) and, on
failures, a ``code`` and the nft stderr. nft commands are atomic — a nonzero
exit changed nothing — so the executor can state the end state: a failed
add leaves the target clear, a failed delete leaves it blocked. A probe may
conclude "absent" only from nft's own ENOENT marker; an unanswerable probe
is a failure with an unknown end state, never a guess.

**Idempotent by construction.** ``enforce`` on an already-blocked address
and ``undo`` of a never-applied block are no-op successes: the goal state
already held. Retries and TTL-expiry races converge instead of erroring.

Division of labor with the decision ladder: the protected-target guard ran
in ``decide_local_action``, before any executor — the executor's target
duty is narrower but hard: a target only ever reaches argv as the canonical
``str()`` of a parsed IP address, so alert-controlled junk cannot shape the
command. v1 blocks IPv4 addresses in a dedicated ``inet vigil_warden``
table (host-firewall input hook, per the spec's scope boundary); IPv6
targets and non-``block_ip`` action types are explicit failures, never
silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol

from core.edge.policy import EdgeAction

__all__ = [
    "BLOCKED",
    "CLEAR",
    "EXECUTED",
    "FAILED",
    "NO_OP",
    "UNKNOWN",
    "ExecutionResult",
    "LocalExecutor",
    "UnregisteredActionType",
    "executor_for",
    "register",
]

# --- what a result records --------------------------------------------------

# ``status``: what this call did. ``executed`` — the element state changed in
# this call; ``no-op`` — the goal state already held, nothing changed;
# ``dry-run`` — nothing was enforced (the fallback executor's mode);
# ``failed`` — the command failed or could not run.
Status = Literal["executed", "no-op", "dry-run", "failed"]
EXECUTED: Status = "executed"
NO_OP: Status = "no-op"
DRY_RUN: Status = "dry-run"
FAILED: Status = "failed"

# ``end_state``: whether the target is blocked once the call returned — the
# journal's honesty field. ``unknown`` is a failure state, never an excuse.
EndState = Literal["blocked", "clear", "unknown"]
BLOCKED: EndState = "blocked"
CLEAR: EndState = "clear"
UNKNOWN: EndState = "unknown"


@dataclass(frozen=True)
class ExecutionResult:
    """What actually happened when an executor handled one action.

    Built by executors, consumed by the journal: ``status`` and ``end_state``
    are the fields a reconcile-time audit reads to reconstruct whether the
    containment a record claims is the containment that occurred.
    """

    success: bool
    status: Status
    executor: str
    end_state: EndState = UNKNOWN
    code: str | None = None
    message: str = ""
    detail: Mapping[str, object] = field(default_factory=dict)


# --- the protocol ------------------------------------------------------------


class LocalExecutor(Protocol):
    """One reversible enforcement primitive, self-describing.

    ``action_type`` is the registry key this executor answers to and ``name``
    is what the journal records as the enforcement mechanism. Both
    ``enforce`` and ``undo`` take the decided action and the canonical
    target, and both are idempotent: applied twice, the second call is a
    no-op success. They never raise — every outcome, including a lost
    subprocess, is an ``ExecutionResult``.
    """

    action_type: str
    name: str

    def enforce(self, action: EdgeAction, target: str) -> ExecutionResult: ...

    def undo(self, action: EdgeAction, target: str) -> ExecutionResult: ...


# --- the allowlist registry ---------------------------------------------------


class UnregisteredActionType(KeyError):
    """Raised for an action type outside the registry's allowlist."""


def register(registry: dict[str, LocalExecutor], executor: LocalExecutor) -> None:
    """Add an executor to the allowlist.

    Keyed by the executor's declared ``action_type`` — a registry that agreed
    with anything other than the executor's own self-description would be a
    lie of exactly the kind this module exists to prevent. Replacing a live
    registration would swap enforcement primitives under the journal's feet,
    so it is refused.
    """
    if executor.action_type in registry:
        raise ValueError(
            f"an executor for {executor.action_type!r} is already registered"
        )
    registry[executor.action_type] = executor


def executor_for(
    registry: Mapping[str, LocalExecutor], action_type: str
) -> LocalExecutor:
    """The registered executor for ``action_type`` — or a refusal.

    The allowlist's only read door, the ``service_manager`` pattern: an
    action type that is not a key here raises before any executor, hence any
    subprocess, can be reached. There is no path through this module that
    enforces an unregistered type.
    """
    try:
        return registry[action_type]
    except KeyError:
        raise UnregisteredActionType(action_type) from None
