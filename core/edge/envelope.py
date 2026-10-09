"""The autonomy envelope's runtime semantics, alongside the signed shape.

``core.edge.policy.AutonomyEnvelope`` defines what is signed; this module
holds what the decision engine does with it: the action-allowlist check, the
set of action types with a reversible local enforcement story, and the
in-process hourly budget that makes ``max_actions_per_hour`` a hard limit.

The envelope is never configurable at the edge and never DB-overridable —
the lesson from the unsigned, remotely flippable autonomy knobs in
``core/response`` (``force_manual_approval``, thresholds). Nothing here reads
settings, env, or the clock: values arrive as arguments, so the ladder that
consumes them stays pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.edge.policy import AutonomyEnvelope

__all__ = [
    "AutonomyEnvelope",
    "REVERSIBLE_ACTION_TYPES",
    "HourlyBudget",
    "action_allowed",
    "budget_for",
]

# Action types whose v1 local enforcement story is reversible by
# construction: the nftables executor adds and deletes a set element, so
# ``block_ip`` can always be undone. The set is deliberately closed — an
# action type absent from it is treated as irreversible (fail-closed), so
# ``require_reversible`` can never be satisfied by an action nobody can undo.
# The executor allowlist-registry is the second backstop: an action type with
# no registered executor can never reach a subprocess at all.
REVERSIBLE_ACTION_TYPES: frozenset[str] = frozenset({"block_ip"})


def action_allowed(envelope: AutonomyEnvelope, action_type: str) -> bool:
    """Whether the envelope's signed allowlist permits this action type."""
    return action_type in envelope.allowed_actions


def budget_for(envelope: AutonomyEnvelope) -> "HourlyBudget":
    """The hourly budget derived from the envelope — the only sanctioned way
    to build one for the ladder, so its limit cannot drift from the signed cap."""
    return HourlyBudget(limit=envelope.max_actions_per_hour)


@dataclass
class HourlyBudget:
    """In-process state for the envelope's ``max_actions_per_hour`` cap.

    Fixed wall-hour buckets: the count resets when the injected ``now``
    crosses into a new clock hour — not sliding, not carried over, so an
    hour's behavior is judgeable from its decisions alone. State is
    in-process by design (no Redis, no disk): a node restart forgives the
    cap, which trades a bounded replay of local enforcement for zero new
    infrastructure — the pack's TTLs and the reconcile-time legality check
    bound what a restart-forgiven hour can have done.
    """

    limit: int
    bucket_start: datetime | None = None
    taken: int = 0

    def take(self, now: datetime) -> bool:
        """Record one action against this hour's cap, or refuse it.

        ``now`` is injected — the ladder passes the same instant it was
        given, so budget behavior is deterministic under a controllable
        clock.
        """
        bucket = now.replace(minute=0, second=0, microsecond=0)
        if self.bucket_start != bucket:
            self.bucket_start = bucket
            self.taken = 0
        if self.taken >= self.limit:
            return False
        self.taken += 1
        return True
