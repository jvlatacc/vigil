"""JIT policy compiler domain.

Foundation package for the compiled fast path: deterministic triage policies
compiled from workflow maturity evidence, evaluated in-process before any LLM
call. The runtime components (maturity job, compiler, evaluator, renderers,
console router) live beside this module; the governance record is
``docs/adr/0001-jit-policy-fast-path.md``.

This package is registered by name in two ``.importlinter`` contracts
(``versioned-api`` sources and ``tiers`` forbidden lists) — both lists are
enumerated, so the domain is declared the day it exists.
"""
