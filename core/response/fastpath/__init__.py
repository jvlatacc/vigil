"""Speculative containment's fast path: policy, configuration, enforcement.

The decision core is LLM-free and side-effect-free — no provider, no queue,
no database — so importing it pulls no heavy dependency. The speculative
service turns a decision into a row on the approval ledger and dispatches it
through the enforcement adapters; the rollback service resolves those rows —
release, escalation through the approval pipeline, and the fail-safe TTL
sweep's expiry.
"""
