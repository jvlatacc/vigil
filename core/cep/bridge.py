"""The one path from a CEP match to containment: the approval gate.

A completed sequence (:class:`core.cep.engine.SequenceMatch`) is a
*proposal*, never an execution. This module renders the proposal audit-style
and hands it to ``ApprovalService.create_action`` — the same DB-backed,
idempotent, confidence-banded gate every other trigger uses (the daemon's
autonomous responder, the workflow phases, the MCP ``approve_action`` tools).
The confidence bands, reversibility rules, force-manual-approval override,
dry-run and insert dedupe are the service's decisions; this bridge
deliberately re-implements none of them. The engine never executes an
action and neither does this module — execution stays with the responder's
existing poll executor.

Two dedupe layers exist because a re-proposed match must never become a
second row:

1. the ``cep:`` idempotency key — ApprovalService returns the existing
   non-failed row for a repeated key, so a duplicate proposal is inert even
   across daemon restarts;
2. a first-wins TTL set here, in front of the gate, so a match the engine
   somehow re-emits inside the window does not even re-attempt the insert.

The key encodes the match's completion event time rather than its window
bucket: two distinct sequences of the same rule on the same entity anchored
in one bucket are different attacks, and a bucket key would silently
swallow the second proposal. The completion time is also replay-stable —
it is the completing finding's event time, identical when a restart
re-fires the same sequence.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.cep.engine import SequenceMatch
from core.response.approval_service import ActionType, ApprovalService, PendingAction
from core.telemetry import get_meter

logger = logging.getLogger(__name__)

# The actor stamp for actions the CEP engine proposes. The engine is not an
# agent — no prompt, no BUILTIN_AGENTS record — the same shape
# ORCHESTRATOR_ACTOR covers for the autonomous loop (core.agents.builtins).
CEP_ENGINE_ACTOR = "cep_engine"

# Row-level origin stamp inside the action's parameters: the machine-readable
# answer to "where did this proposal come from", for filters and audits.
CEP_SOURCE = "cep"

DEFAULT_DEDUPE_TTL_S = 3600.0


def _iso(epoch: float) -> str:
    """UTC ISO stamp for an event-time epoch (matches are event-time)."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def match_id(match: SequenceMatch) -> str:
    """The match's identity — also the approval row's idempotency key."""
    return f"cep:{match.rule_id}:{match.entity_key}:{match.completed_at:.6f}"


def render_match_evidence(match: SequenceMatch) -> List[str]:
    """The completed sequence, audit-style: every claim the row makes is on
    the row (the ``decision_rule()`` spirit — one line per fact, parseable).

    Contributing findings render in step order; the sequence's start and
    completion are the match's event-time bounds; the graph path, when the
    pipeline attached one, is the chain that linked the entities.
    """
    lines = [
        f"cep.rule={match.rule_id}",
        f"cep.entity_key={match.entity_key}",
        f"cep.sequence_started={_iso(match.started_at)}",
        f"cep.sequence_completed={_iso(match.completed_at)}",
    ]
    for index, finding_id in enumerate(match.finding_ids):
        lines.append(f"cep.finding[{index}]={finding_id}")
    if match.sources:
        lines.append(f"cep.sources={','.join(match.sources)}")
    lines.append(f"cep.confidence={match.confidence}")
    lines.append(f"cep.window_bucket={match.window_bucket}")
    if match.graph_path:
        lines.append("cep.graph_path=" + " -> ".join(match.graph_path))
    return lines


class CepResponseBridge:
    """Proposes one approval-gated action per completed sequence.

    Constructed with the process's :class:`ApprovalService` — the same
    instance the responder and orchestrator hold — so CEP proposals land in
    the one approval queue a person actually reviews.
    """

    def __init__(
        self,
        approvals: ApprovalService,
        *,
        dedupe_ttl_s: float = DEFAULT_DEDUPE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._approvals = approvals
        self._dedupe_ttl_s = max(0.0, dedupe_ttl_s)
        self._clock = clock
        self._seen_match_ids: Dict[str, float] = {}
        # Lifetime count of proposals that reached the gate — the "actions
        # proposed" of spec AC 8. A dedupe-swallowed re-emission is not a
        # proposal and does not count.
        self.stats: Dict[str, Any] = {"cep_actions_proposed": 0}
        self._actions_counter: Any = None
        self._instruments_ready = False

    def fire(self, match: SequenceMatch) -> Optional[PendingAction]:
        """Propose ``match`` to the approval gate, exactly once.

        Returns the created (or reused) :class:`PendingAction`, or ``None``
        when this match id was already proposed inside the dedupe TTL
        window. Does not catch: a gate failure (the service is DB-backed)
        propagates to the caller, which owns the skip-and-log decision.
        """
        match_key = match_id(match)
        now = self._clock()
        self._forget_expired(now)
        if match_key in self._seen_match_ids:
            logger.debug(
                "CEP bridge: match %s already proposed inside the dedupe "
                "window; not re-proposing",
                match_key,
            )
            return None
        self._seen_match_ids[match_key] = now + self._dedupe_ttl_s

        action = self._approvals.create_action(
            action_type=ActionType(match.action_type),
            title=f"CEP {match.action_type}: {self._target(match)}",
            description=self._description(match),
            target=self._target(match),
            # Passed through untouched: the bands are the service's call,
            # and a bridge that nudged confidence would be gaming the gate.
            confidence=match.confidence,
            reason=(
                f"CEP rule {match.rule_id} completed a sequence on "
                f"{match.entity_key}"
            ),
            evidence=render_match_evidence(match),
            created_by=CEP_ENGINE_ACTOR,
            parameters=self._parameters(match),
            idempotency_key=match_key,
        )
        logger.info(
            "CEP bridge: proposed action %s (status %s) for rule %s on %s",
            action.action_id,
            action.status,
            match.rule_id,
            match.entity_key,
        )
        self.stats["cep_actions_proposed"] += 1
        self._record_proposed()
        return action

    # ------------------------------------------------------------------
    # Proposal parts
    # ------------------------------------------------------------------

    @staticmethod
    def _target(match: SequenceMatch) -> str:
        # The loader pins target_field to a key field and the engine fires
        # only when every key field is present, so this is always resolved;
        # a KeyError here is a contract violation worth surfacing, not
        # masking with an empty target row.
        return match.entities[match.target_field]

    @staticmethod
    def _description(match: SequenceMatch) -> str:
        contributed = (
            f"{len(match.finding_ids)} finding record(s)"
            if match.finding_ids
            else "findings without recorded ids"
        )
        return (
            f"CEP rule {match.rule_id} correlated {contributed} from "
            f"{', '.join(match.sources) if match.sources else 'unknown sources'} "
            f"on {match.entity_key} between {_iso(match.started_at)} and "
            f"{_iso(match.completed_at)}. Proposed in flight by the "
            f"streaming CEP engine; the approval gate decides the outcome."
        )

    @staticmethod
    def _parameters(match: SequenceMatch) -> Dict[str, Any]:
        """Machine-readable provenance, riding the row next to the
        rendered evidence (the audit trail the approval tools assume)."""
        return {
            "source": CEP_SOURCE,
            "rule_id": match.rule_id,
            "entity_key": match.entity_key,
            "entities": dict(match.entities),
            "target_field": match.target_field,
            "finding_ids": list(match.finding_ids),
            "data_sources": list(match.sources),
            "window_bucket": match.window_bucket,
            "sequence_started_at": _iso(match.started_at),
            "sequence_completed_at": _iso(match.completed_at),
            "graph_path": list(match.graph_path) if match.graph_path else None,
        }

    # ------------------------------------------------------------------
    # Metrics mirror (spec AC 8)
    # ------------------------------------------------------------------

    def _record_proposed(self) -> None:
        """Mirror the proposal into OTEL (instruments created on first
        record, the tap's pattern)."""
        self._ensure_instruments()
        try:
            if self._actions_counter is not None:
                self._actions_counter.add(1)
        except Exception as _err:
            logger.debug("OTEL CEP record failed (non-fatal): %s", _err)

    def _ensure_instruments(self) -> None:
        if self._instruments_ready:
            return
        self._instruments_ready = True
        try:
            meter = get_meter("vigil.daemon")
            self._actions_counter = meter.create_counter(
                name="vigil.cep.actions",
                description="Actions proposed to the approval gate by the CEP bridge",
                unit="1",
            )
        except Exception as _err:
            logger.debug("OTEL CEP instruments unavailable: %s", _err)

    # ------------------------------------------------------------------
    # First-wins dedupe
    # ------------------------------------------------------------------

    def _forget_expired(self, now: float) -> None:
        """Drop expired match ids so the set stays bounded by TTL traffic."""
        expired = [key for key, expiry in self._seen_match_ids.items() if expiry <= now]
        for key in expired:
            del self._seen_match_ids[key]
