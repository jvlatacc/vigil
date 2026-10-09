"""Speculative-containment Fast-Path: the deterministic blast-radius control.

The gate decides in-process, in microseconds, whether a finding earns a
reversible containment lease — before any LLM is consulted. It cannot
consult one: this package imports nothing but ``core.config``,
``core.storage``, ``core.telemetry`` and ``core.response``'s shared
decision renderer, and lint-imports blocks the LLM stack, the API surface
and ``services/`` for this subtree (.importlinter, contract ``fastpath``).

Slices of the same spec: PR-2 shipped the policy gate and its config (no
database, by design — nothing in ``gate``/``config`` reaches storage). PR-3
ships the lease ledger, the executors and the TTL sweeper: the ledger owns
row state in ``containment_actions`` and the executors own effects, each
apply/undo pair undoing only its own object.

Callers import from ``core.response.fastpath``.
"""

from core.response.fastpath.config import FastPathConfig
from core.response.fastpath.gate import (
    ACTION_BY_SEVERITY,
    FastPathDecision,
    FastPathVerdict,
    GateCounters,
    evaluate,
    record_decision,
)
from core.response.fastpath.ledger import (
    ContainmentLedger,
    LeaseIntent,
    LeaseView,
    Transition,
)

__all__ = [
    "ACTION_BY_SEVERITY",
    "FastPathConfig",
    "FastPathDecision",
    "FastPathVerdict",
    "GateCounters",
    "LeaseIntent",
    "LeaseView",
    "Transition",
    "ContainmentLedger",
    "evaluate",
    "record_decision",
]
