"""The CEP engine's bounded in-process entity graph (spec ACs 3 and 6).

Correlation needs the multi-hop questions the per-rule state machines
cannot answer alone: which entities are linked, and is there a chain
between two of them inside the attack window. This module is that state —
plain adjacency dicts, no graph database, per the spec's locked decision
(the storage interface in ``core/cep/snapshot.py`` carries the adapter seam
for FalkorDB later).

Bounded by design, in the same spirit as the tap's drop-newest queue: the
graph shares the daemon's memory budget, so growth stops at the configured
caps. Nodes beyond ``max_nodes`` evict the least recently observed entity;
edges beyond ``max_edges`` reject the newest link with a metric — an edge
that was never observed cannot mislead a path query, and the counter keeps
the rejection visible instead of silent.

Edges are directed and timestamped. A re-observed link refreshes its
timestamp to the most recent observation, so an edge's time is always
"last seen linked", never regressed by a late-arriving backfill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Node kinds and edge relations are closed vocabularies, per the spec. A
# misspelled kind ("hosts") would otherwise silently fork the entity space,
# and a path query across the fork would answer "no path" to a chain that
# exists — the fabricated-value failure the normalizer refuses upstream.
NODE_KINDS = frozenset({"host", "user", "ip", "finding"})
EDGE_RELATIONS = frozenset({"observed_in", "connected_to", "sequence_link"})

# Bumped when the serialized shape below changes incompatibly. restore()
# refuses payloads from a different version rather than guessing.
GRAPH_SNAPSHOT_VERSION = 1

NodeKey = Tuple[str, str]  # (kind, value)

_EVICT_LOG_EVERY = 100


class GraphRestoreError(ValueError):
    """The snapshot payload is not one this graph version can rebuild."""


def _utc(ts: datetime) -> datetime:
    """Coerce to aware UTC: a naive timestamp is read as UTC, because the
    daemon's producers stamp UTC and the normalizer passes what it parsed.
    Mixing naive and aware datetimes raises on comparison, so the coercion
    happens once, at the graph's edge."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class GraphNode:
    """One entity (or finding) node: an identity plus when it was seen."""

    kind: str
    value: str
    first_seen: datetime
    last_seen: datetime


@dataclass(frozen=True)
class GraphEdge:
    """One directed, timestamped relation between two nodes."""

    src: NodeKey
    relation: str
    dst: NodeKey
    ts: datetime


@dataclass(frozen=True)
class GraphPath:
    """The chain a successful path query returns: the nodes in walk order
    and the edges that linked them, so rule evidence can render the path
    and not merely assert it."""

    nodes: Tuple[NodeKey, ...]
    edges: Tuple[GraphEdge, ...]


class EntityGraph:
    """In-process multi-node correlation state over plain adjacency dicts.

    Amortized O(1) per mutation: node add/touch and edge upsert are dict
    operations; eviction is rare (only at the cap). ``path_exists`` is a
    BFS bounded by the node cap, so worst case stays proportional to the
    graph it walks.

    Counters live in ``stats`` — the same dict convention the tap uses —
    so the MetricsServer wiring can surface graph health without this
    module owning OTEL instruments.
    """

    def __init__(self, max_nodes: int = 10000, max_edges: int = 50000) -> None:
        self._max_nodes = max(1, max_nodes)
        self._max_edges = max(1, max_edges)
        # adj[src][(relation, dst)] = latest edge ts; radj mirrors it for
        # eviction (drop every incident edge) and reverse queries.
        self._adj: Dict[NodeKey, Dict[Tuple[str, NodeKey], datetime]] = {}
        self._radj: Dict[NodeKey, Dict[Tuple[str, NodeKey], datetime]] = {}
        self._nodes: Dict[NodeKey, GraphNode] = {}
        self._edge_count = 0
        self.stats: Dict[str, int] = {
            "cep_graph_nodes": 0,
            "cep_graph_edges": 0,
            "cep_graph_nodes_evicted": 0,
            "cep_graph_edges_rejected": 0,
        }
        self._logged_evictions = 0

    # -- mutation ---------------------------------------------------------

    def observe_node(self, kind: str, value: str, ts: datetime) -> NodeKey:
        """Add the entity, or touch it: last_seen moves to ``ts`` (never
        backwards). Returns the node key."""
        _check_kind(kind)
        if not isinstance(value, str) or not value:
            raise ValueError(f"node value must be a non-empty string, got {value!r}")
        stamp = _utc(ts)
        key: NodeKey = (kind, value)
        node = self._nodes.get(key)
        if node is None:
            self._evict_for_node()
            self._nodes[key] = GraphNode(
                kind=kind, value=value, first_seen=stamp, last_seen=stamp
            )
            self.stats["cep_graph_nodes"] = len(self._nodes)
        elif stamp > node.last_seen:
            self._nodes[key] = GraphNode(
                kind=kind,
                value=value,
                first_seen=node.first_seen,
                last_seen=stamp,
            )
        return key

    def link(
        self,
        src: NodeKey,
        relation: str,
        dst: NodeKey,
        ts: datetime,
    ) -> bool:
        """Timestamp one directed relation, adding its endpoints if new.

        Returns True when the edge is in the graph. At the edge cap a
        *new* triple is rejected (counted, logged at debug); refreshing an
        existing edge's timestamp is not growth and always succeeds.
        """
        if relation not in EDGE_RELATIONS:
            raise ValueError(f"unknown edge relation {relation!r}")
        stamp = _utc(ts)
        self.observe_node(src[0], src[1], stamp)
        self.observe_node(dst[0], dst[1], stamp)

        out_edges = self._adj.setdefault(src, {})
        existing = out_edges.get((relation, dst))
        if existing is not None:
            if stamp > existing:
                out_edges[(relation, dst)] = stamp
                self._radj[dst][(relation, src)] = stamp
            return True
        if self._edge_count >= self._max_edges:
            self.stats["cep_graph_edges_rejected"] += 1
            logger.debug(
                "CEP graph edge cap (%d) reached: link %s -%s-> %s rejected",
                self._max_edges,
                src,
                relation,
                dst,
            )
            return False
        out_edges[(relation, dst)] = stamp
        self._radj.setdefault(dst, {})[(relation, src)] = stamp
        self._edge_count += 1
        self.stats["cep_graph_edges"] = self._edge_count
        return True

    def _evict_for_node(self) -> None:
        """Make room for one node: evict the least recently observed. The
        node being added is not here yet, so eviction cannot remove it."""
        if len(self._nodes) < self._max_nodes:
            return
        oldest = min(
            self._nodes, key=lambda k: (self._nodes[k].last_seen, self._nodes[k].first_seen)
        )
        self._remove_node(oldest)
        self.stats["cep_graph_nodes_evicted"] += 1
        total = self.stats["cep_graph_nodes_evicted"]
        if total == 1 or total - self._logged_evictions >= _EVICT_LOG_EVERY:
            self._logged_evictions = total
            logger.info(
                "CEP graph node cap (%d) reached: evicted the least recently "
                "observed entity (%d evictions so far)",
                self._max_nodes,
                total,
            )

    def _remove_node(self, key: NodeKey) -> None:
        out_edges = self._adj.pop(key, {})
        for rel, dst in out_edges:
            self._radj.get(dst, {}).pop((rel, key), None)
        in_edges = self._radj.pop(key, {})
        for rel, src in in_edges:
            self._adj.get(src, {}).pop((rel, key), None)
        self._edge_count -= len(out_edges) + len(in_edges)
        del self._nodes[key]
        self.stats["cep_graph_edges"] = self._edge_count
        self.stats["cep_graph_nodes"] = len(self._nodes)

    # -- queries ----------------------------------------------------------

    def node(self, key: NodeKey) -> Optional[GraphNode]:
        return self._nodes.get(key)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return self._edge_count

    def neighbors(
        self, key: NodeKey, *, relation: Optional[str] = None
    ) -> Tuple[NodeKey, ...]:
        """Nodes with an outgoing edge from ``key`` — the next hops a rule
        can walk. Direction follows the edge: a finding points at the host
        it was observed in, a sequence link points forward in the chain."""
        out_edges = self._adj.get(key, {})
        return tuple(
            dst for (rel, dst) in out_edges if relation is None or rel == relation
        )

    def path_exists(
        self,
        src: NodeKey,
        dst: NodeKey,
        within_seconds: int,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[GraphPath]:
        """The chain from ``src`` to ``dst`` whose every edge was observed
        within the last ``within_seconds``, or None.

        The window anchors at ``now`` (wall clock by default; injectable
        for tests) because correlation is an in-flight question: the graph
        answers "are these entities linked as of the last minute", not
        "were they ever". Hop-to-hop pacing is the engine's per-step
        ``max_gap_seconds``, not this query's.
        """
        if src not in self._nodes or dst not in self._nodes:
            return None
        anchor = _utc(now) if now is not None else datetime.now(timezone.utc)
        cutoff = anchor - timedelta(seconds=within_seconds)
        if src == dst:
            return GraphPath(nodes=(src,), edges=())

        parents: Dict[NodeKey, Tuple[NodeKey, Tuple[str, NodeKey]]] = {}
        queue = [src]
        visited = {src}
        while queue:
            current = queue.pop(0)
            out_edges = self._adj.get(current, {})
            fresh = [
                (rel, nxt)
                for (rel, nxt), ts in out_edges.items()
                if ts >= cutoff and nxt not in visited
            ]
            # Deterministic walk: relations then destinations.
            fresh.sort()
            for rel, nxt in fresh:
                visited.add(nxt)
                parents[nxt] = (current, (rel, nxt))
                if nxt == dst:
                    return self._reconstruct(src, dst, parents)
                queue.append(nxt)
        return None

    def _reconstruct(
        self,
        src: NodeKey,
        dst: NodeKey,
        parents: Dict[NodeKey, Tuple[NodeKey, Tuple[str, NodeKey]]],
    ) -> GraphPath:
        nodes: list = [dst]
        edges: list = []
        cursor = dst
        while cursor != src:
            prev, (rel, _) = parents[cursor]
            edges.append(
                GraphEdge(
                    src=prev,
                    relation=rel,
                    dst=cursor,
                    ts=self._adj[prev][(rel, cursor)],
                )
            )
            nodes.append(prev)
            cursor = prev
        nodes.reverse()
        edges.reverse()
        return GraphPath(nodes=tuple(nodes), edges=tuple(edges))

    # -- durability -------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """A versioned, JSON-safe payload of every node and edge. Node and
        edge order is deterministic (insertion order; edges sorted), so a
        restore round-trip reproduces the payload byte for byte."""
        nodes = [
            {
                "kind": node.kind,
                "value": node.value,
                "first_seen": node.first_seen.isoformat(),
                "last_seen": node.last_seen.isoformat(),
            }
            for node in self._nodes.values()
        ]
        edges = [
            {
                "src_kind": src[0],
                "src_value": src[1],
                "relation": rel,
                "dst_kind": dst[0],
                "dst_value": dst[1],
                "ts": ts.isoformat(),
            }
            for src, out_edges in self._adj.items()
            for (rel, dst), ts in sorted(out_edges.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        ]
        return {"version": GRAPH_SNAPSHOT_VERSION, "nodes": nodes, "edges": edges}

    def restore(self, payload: Any) -> None:
        """Rebuild the graph exactly from a ``snapshot()`` payload.

        Raises ``GraphRestoreError`` — naming the real reason — on a wrong
        version or a malformed entry, so the caller can choose to start
        fresh loudly instead of correlating over half a graph.
        """
        if not isinstance(payload, dict):
            raise GraphRestoreError("graph payload must be an object")
        version = payload.get("version")
        if version != GRAPH_SNAPSHOT_VERSION:
            raise GraphRestoreError(
                f"graph payload version {version!r} != {GRAPH_SNAPSHOT_VERSION}"
            )
        raw_nodes = payload.get("nodes")
        raw_edges = payload.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise GraphRestoreError("graph payload needs 'nodes' and 'edges' lists")

        nodes: Dict[NodeKey, GraphNode] = {}
        for raw in raw_nodes:
            try:
                kind, value = raw["kind"], raw["value"]
                first_seen = _utc(datetime.fromisoformat(raw["first_seen"]))
                last_seen = _utc(datetime.fromisoformat(raw["last_seen"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise GraphRestoreError(f"malformed node entry {raw!r}: {exc}") from exc
            _check_kind(kind)
            key: NodeKey = (kind, value)
            if key in nodes:
                raise GraphRestoreError(f"duplicate node {key}")
            nodes[key] = GraphNode(
                kind=kind, value=value, first_seen=first_seen, last_seen=last_seen
            )
        if len(nodes) > self._max_nodes:
            raise GraphRestoreError(
                f"payload has {len(nodes)} nodes, over this graph's cap of {self._max_nodes}"
            )

        adj: Dict[NodeKey, Dict[Tuple[str, NodeKey], datetime]] = {}
        edge_count = 0
        for raw in raw_edges:
            try:
                src: NodeKey = (raw["src_kind"], raw["src_value"])
                relation = raw["relation"]
                dst: NodeKey = (raw["dst_kind"], raw["dst_value"])
                ts = _utc(datetime.fromisoformat(raw["ts"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise GraphRestoreError(f"malformed edge entry {raw!r}: {exc}") from exc
            if relation not in EDGE_RELATIONS:
                raise GraphRestoreError(f"unknown edge relation {relation!r}")
            if src not in nodes or dst not in nodes:
                raise GraphRestoreError(f"edge {src} -{relation}-> {dst} lacks an endpoint node")
            out_edges = adj.setdefault(src, {})
            if (relation, dst) in out_edges:
                raise GraphRestoreError(f"duplicate edge {src} -{relation}-> {dst}")
            out_edges[(relation, dst)] = ts
            edge_count += 1
        if edge_count > self._max_edges:
            raise GraphRestoreError(
                f"payload has {edge_count} edges, over this graph's cap of {self._max_edges}"
            )

        radj: Dict[NodeKey, Dict[Tuple[str, NodeKey], datetime]] = {}
        for src, out_edges in adj.items():
            for (rel, dst), ts in out_edges.items():
                radj.setdefault(dst, {})[(rel, src)] = ts

        self._nodes = nodes
        self._adj = adj
        self._radj = radj
        self._edge_count = edge_count
        self.stats["cep_graph_nodes"] = len(nodes)
        self.stats["cep_graph_edges"] = edge_count


def _check_kind(kind: str) -> None:
    if kind not in NODE_KINDS:
        raise ValueError(
            f"unknown node kind {kind!r}; known kinds: {sorted(NODE_KINDS)}"
        )
