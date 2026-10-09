"""Speculative containment's fast path: a pure policy plus its configuration.

The decision core is LLM-free and side-effect-free — no provider, no queue,
no database — so importing it pulls no heavy dependency. The speculative
service, enforcement adapters, and rollback verbs that act on its decisions
join this package in later slices.
"""
