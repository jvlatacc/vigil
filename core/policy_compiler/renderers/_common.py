"""Shared deterministic pieces the four renderers compose.

Every renderer is a pure function of the policy IR: the same document
renders to byte-identical output — golden fixtures pin that property per
format. The shared header carries the policy's identity, its match clause
in prose, and its decision, so an exported artifact says what was trusted
even when the target format cannot express the predicate tree.
"""

from __future__ import annotations

import hashlib

from core.policy_compiler.models import MatchClause, PolicyIR

# Recommended actions that name packet-level containment. Only these render
# as blocking rules/fragments; the rest render as alerting or documentation
# artifacts — a decision is a triage verdict, and containment still routes
# through the approval pipeline (ADR 0001).
BLOCKING_ACTIONS = frozenset({"isolate", "block"})

# The order the match clauses are described in, everywhere, forever.
_CLAUSE_ORDER = ("data_source", "techniques", "entity_context_types")


def describe_match(match: MatchClause) -> str:
    """The match clause as one deterministic prose line for artifact headers."""
    parts: list[str] = []
    if match.data_source is not None:
        parts.append(f"data_source in {list(match.data_source)}")
    if match.techniques is not None:
        parts.append(_describe_set("techniques", match.techniques))
    if match.entity_context_types is not None:
        parts.append(_describe_set("entity-context types", match.entity_context_types))
    return "; ".join(parts) if parts else "unconstrained (workflow identity only)"


def _describe_set(name: str, set_) -> str:
    words = []
    if set_.any_of:
        words.append(f"any_of {list(set_.any_of)}")
    if set_.all_of:
        words.append(f"all_of {list(set_.all_of)}")
    return f"{name} " + " and ".join(words)


def describe_decision(policy: PolicyIR) -> str:
    decision = policy.decision
    return (
        f"severity={decision.severity} confidence={decision.confidence:g} "
        f"recommended_action={decision.recommended_action} "
        f"(actions human-only)"
    )


def provenance_header(policy: PolicyIR, tool: str) -> str:
    """The four provenance lines every rendered artifact opens with."""
    return (
        f"# Vigil JIT compiled policy: {policy.policy_id} v{policy.version}"
        f" (content {policy.content_hash})\n"
        f"# Archetype: workflow {policy.match.workflow_id} over"
        f" {policy.maturity.window_days} days\n"
        f"# Match: {describe_match(policy.match)}\n"
        f"# Decision: {describe_decision(policy)}\n"
        f"# Rendered for {tool} by the Vigil policy compiler — generated"
        f" artifact, do not edit."
    )


def sid_for(policy_id: str) -> int:
    """A deterministic Snort/Suricata sid in the local-rules range.

    Sids must be stable across recompiles (an ids deployment keys its
    suppressions and dashboards on them), so they hash the policy id —
    never the version or content, which rev, not sid, tracks.
    """
    digest = hashlib.sha256(policy_id.encode("utf-8")).hexdigest()
    return 1_000_000 + int(digest[:8], 16) % 9_000_000
