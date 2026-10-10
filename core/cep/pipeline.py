"""The CEP loop, assembled: tap queue -> normalize -> graph -> engine -> bridge.

This is the integration module the daemon wires (``services.daemon.main``).
It owns the second leg of the finding tee end to end: one component task
drains the tap's bounded queue, feeds each normalized finding to the entity
graph, advances the engine, decorates completed matches with the graph path
that links their entities, and proposes them through the response bridge.
The spine (``FindingProcessor`` and its acks) is never touched — a fault in
any subsystem here costs only its own contribution and is logged with the
finding id, never swallowed.

Graph linkage follows the graph's own edge semantics: each finding points
``observed_in`` every entity it carries, and entities co-occurring in one
finding are ``connected_to`` each other in both directions (``connected_to``
is a symmetric relation and edges are directed — recording both directions
is what lets ``path_exists`` find the chain regardless of walk direction).
Timestamps are the finding's event time, or the receive time when the source
sent none — the engine's documented fallback, applied here too.

Snapshot adapters: :class:`EngineSnapshotState` presents the engine's
combined ``serialize_machines`` / ``restore_machines`` hooks as the two
``StateSection`` slots :class:`~core.cep.snapshot.SnapshotManager` fills, so
the envelope keeps its documented shape — ``machines`` and ``seen_ids`` as
separate sections. The adapter pair shares a one-pass stash: the manager
restores the machines section first and the seen-ids section second, and
only the second call has both payloads in hand for the engine's combined
restore. One stash per restore pass — the daemon restores once per boot,
and each boot builds its own adapter pair.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.cep.engine import CepEngine, SequenceMatch
from core.cep.graph import EntityGraph
from core.cep.normalize import NormalizedFinding, normalize_finding
from core.cep.rules import CepRule

if TYPE_CHECKING:  # the protocol the snapshot manager fills these into
    from core.cep.snapshot import StateSection

logger = logging.getLogger(__name__)

# Normalized entity field -> graph node kind (core.cep.graph.NODE_KINDS).
# The rule vocabulary is the normalizer's four fields; the graph's is
# host/user/ip — the two ip fields share a kind and stay distinct by value.
_ENTITY_NODE_KINDS: Dict[str, str] = {
    "host": "host",
    "user": "user",
    "src_ip": "ip",
    "dest_ip": "ip",
}

# Co-occurring entity fields, in the normalizer's canonical order — the
# deterministic pair order keeps graph edges reproducible across restarts.
_ENTITY_FIELDS: Tuple[str, ...] = ("host", "user", "src_ip", "dest_ip")


class CepPipeline:
    """Drains the tap queue and runs the full correlation loop for it."""

    def __init__(
        self,
        *,
        engine: CepEngine,
        rules: Sequence[CepRule],
        graph: EntityGraph,
        bridge: Any,
        tap_queue: "asyncio.Queue[Any]",
    ) -> None:
        self._engine = engine
        self._graph = graph
        self._bridge = bridge
        self._tap_queue = tap_queue
        # rule id -> window, for the path-evidence query on each match.
        self._windows: Dict[str, int] = {
            rule.id: rule.window_seconds for rule in rules
        }

    # ------------------------------------------------------------------
    # The component task
    # ------------------------------------------------------------------

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Drain the tap queue until shutdown, alongside the engine's
        sweeper. Item faults are logged and skipped; the spine is elsewhere
        and untouched (the processor owns the acks)."""
        sweeper = asyncio.create_task(self._engine.run_sweeper())
        try:
            while not shutdown_event.is_set():
                try:
                    item = await asyncio.wait_for(
                        self._tap_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                try:
                    self.process_item(item)
                except Exception:
                    logger.exception(
                        "CEP pipeline: item processing failed; the finding "
                        "spine is unaffected and the item is skipped"
                    )
        finally:
            sweeper.cancel()
            await asyncio.gather(sweeper, return_exceptions=True)

    # ------------------------------------------------------------------
    # One event through the loop
    # ------------------------------------------------------------------

    def process_item(self, item: Any) -> List[SequenceMatch]:
        """One tap-queue item, normalized and correlated.

        Returns the completed (graph-decorated) matches the engine emitted
        from this item — already proposed through the bridge. Items that are
        not findings (the tee only mirrors those, but never say never) are
        skipped without touching any state.
        """
        if not isinstance(item, Mapping) or item.get("type") != "finding":
            return []
        data = item.get("data")
        if not isinstance(data, Mapping):
            return []

        event = normalize_finding(data)
        try:
            self._link_event(event)
        except Exception:
            logger.exception(
                "CEP graph: linking failed for finding %s (non-fatal); "
                "graph evidence may lag this event",
                event.finding_id,
            )

        matches = self._engine.on_event(event)
        processed: List[SequenceMatch] = []
        for match in matches:
            decorated = self._attach_graph_path(match)
            try:
                self._bridge.fire(decorated)
            except Exception:
                # The proposal failed (the gate is DB-backed); the sequence
                # is already consumed, so the log carries the evidence —
                # the one place this match survives.
                logger.exception(
                    "CEP bridge: proposing the %s match on %s failed; match "
                    "dropped (contributing findings: %s)",
                    match.rule_id,
                    match.entity_key,
                    decorated.finding_ids,
                )
            processed.append(decorated)
        return processed

    # ------------------------------------------------------------------
    # Graph linkage
    # ------------------------------------------------------------------

    def _link_event(self, event: NormalizedFinding) -> None:
        """Observe one finding and its entities in the graph.

        Event time is the source's stamp when it has one, else the receive
        time — the engine's documented fallback, honestly applied.
        """
        ts = event.timestamp or datetime.now(timezone.utc)
        finding_node: Optional[Tuple[str, str]] = (
            ("finding", event.finding_id) if event.finding_id else None
        )
        entity_nodes: List[Tuple[str, str]] = []
        for field_name in _ENTITY_FIELDS:
            value = getattr(event, field_name)
            if value:
                entity_nodes.append((_ENTITY_NODE_KINDS[field_name], value))

        if finding_node is not None:
            self._graph.observe_node(finding_node[0], finding_node[1], ts)
        for kind, value in entity_nodes:
            self._graph.observe_node(kind, value, ts)

        if finding_node is not None:
            for kind, value in entity_nodes:
                self._graph.link(finding_node, "observed_in", (kind, value), ts)
        for i in range(len(entity_nodes)):
            for j in range(i + 1, len(entity_nodes)):
                src, dst = entity_nodes[i], entity_nodes[j]
                self._graph.link(src, "connected_to", dst, ts)
                self._graph.link(dst, "connected_to", src, ts)

    def _attach_graph_path(self, match: SequenceMatch) -> SequenceMatch:
        """Attach the chain that linked this match's entities, when one is
        in the graph. The query anchors at the match's completion event
        time — the evidence answers "what linked them when the sequence
        completed", so a replay produces the same path."""
        window = self._windows.get(match.rule_id)
        target_value = match.entities.get(match.target_field)
        if window is None or not target_value:
            return match
        target_node = (_ENTITY_NODE_KINDS[match.target_field], target_value)

        # Most informative first: the opening finding's chain to the target,
        # then any secondary entity's chain to it. A degenerate self-path
        # (no edges) is not evidence of linkage.
        candidates: List[Tuple[str, str]] = []
        if match.finding_ids:
            candidates.append(("finding", match.finding_ids[0]))
        candidates.extend(
            (_ENTITY_NODE_KINDS[field_name], value)
            for field_name, value in match.entities.items()
            if field_name != match.target_field
        )

        completed_at = datetime.fromtimestamp(match.completed_at, tz=timezone.utc)
        for src in candidates:
            path = self._graph.path_exists(
                src, target_node, within_seconds=window, now=completed_at
            )
            if path is not None and path.edges:
                return replace(
                    match,
                    graph_path=tuple(
                        f"{kind}:{value}" for kind, value in path.nodes
                    ),
                )
        return match


class EngineSnapshotState:
    """The engine's combined snapshot hooks, as the two sections the
    snapshot manager fills.

    ``serialize_machines`` returns ``{"machines": ..., "seen_ids": ...}`` as
    one payload and ``restore_machines`` consumes it as one payload, while
    the manager's envelope carries the two as separate sections and restores
    them in two calls. This adapter bridges the two shapes: each section
    snapshots its own half of the combined payload, and a restore stashes
    its half, then performs the engine's combined restore with whatever the
    other half has stashed so far (the machines section restores first, the
    seen-ids section second, so the second call completes the pair). The
    stash lives for one restore pass — the daemon restores once per boot and
    builds a fresh adapter pair for it.
    """

    def __init__(self, engine: CepEngine) -> None:
        self._engine = engine
        self._stashed: Dict[str, Any] = {}

    def machines_section(self) -> "StateSection":
        return _EngineSection(self, "machines")

    def seen_ids_section(self) -> "StateSection":
        return _EngineSection(self, "seen_ids")

    def _snapshot_section(self, name: str) -> Any:
        return self._engine.serialize_machines().get(name)

    def _restore_section(self, name: str, payload: Any) -> None:
        self._stashed[name] = payload
        self._engine.restore_machines(
            {
                "machines": self._stashed.get("machines") or {},
                "seen_ids": self._stashed.get("seen_ids") or {},
            }
        )


class _EngineSection:
    """One named half of the engine's combined snapshot payload."""

    def __init__(self, owner: EngineSnapshotState, name: str) -> None:
        self._owner = owner
        self._name = name

    def snapshot_state(self) -> Any:
        return self._owner._snapshot_section(self._name)

    def restore_state(self, payload: Any) -> None:
        self._owner._restore_section(self._name, payload)
