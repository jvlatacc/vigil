"""Speculative-containment Fast-Path: the deterministic blast-radius control.

The gate decides in-process, in microseconds, whether a finding earns a
reversible containment lease — before any LLM is consulted. It cannot
consult one: this package imports nothing but ``core.config``,
``core.telemetry`` and ``core.response``'s shared decision renderer, and
lint-imports blocks the LLM stack, the API surface and ``services/`` for
this subtree (.importlinter, contract ``fastpath``).

PR-2 ships the policy gate and its config. The lease ledger
(``containment_actions``), the executors and the TTL sweeper are later
slices of the same spec; nothing here reaches the database by design.

Callers import from ``core.response.fastpath``.
"""

from core.response.fastpath.config import FastPathConfig

__all__ = [
    "FastPathConfig",
]
