"""Tool-call accountability: the audit writer and the chain verifier.

Every tool call Vigil allows or denies lands exactly one row in
``tool_call_audit`` (``41_tool_call_audit.sql``): who ran it, on what server
and tool, the arguments by digest, the decision, and the outcome. Allowed and
denied are both first-class — an access that leaves no row is the one an
investigation cannot see.

The writer never swallows a failure. A call whose audit row cannot be written
fails the call (fail closed): a tool execution nobody can account for is not a
successful one. This module is also the one place the hash formula lives in
Python, so the writer, the verifier, and the database trigger
(``tool_call_audit_assign_hashes``) all spell rows the same way — and the
integration suite proves the trigger and this module agree.
"""

from core.audit.tool_calls import (
    ACTOR_AGENT,
    DECISION_ALLOW,
    DECISION_DENY,
    SURFACE_AGENT,
    SURFACE_IN_PROCESS,
    SURFACE_MCP_CLIENT,
    SURFACE_MCP_INBOUND,
    SURFACE_VSTRIKE,
    ChainVerification,
    current_trace_id,
    hash_args,
    record_tool_call,
    verify_chain,
)

__all__ = [
    "ACTOR_AGENT",
    "DECISION_ALLOW",
    "DECISION_DENY",
    "SURFACE_AGENT",
    "SURFACE_IN_PROCESS",
    "SURFACE_MCP_CLIENT",
    "SURFACE_MCP_INBOUND",
    "SURFACE_VSTRIKE",
    "ChainVerification",
    "current_trace_id",
    "hash_args",
    "record_tool_call",
    "verify_chain",
]
