"""Derive the digital-twin graph from findings' ``entity_context``.

Vigil keeps no host inventory or topology store, so the map is derived from
what findings name: ``hostnames[]`` become host nodes, the shared
``FINDING_IP_KEYS`` addresses become IP nodes, ``usernames[]`` become user
nodes, and a ``device_id`` with no hostname stands in for its host. A finding
that names nothing lands on the single *Unattributed* node instead of
vanishing — the map always accounts for every finding.

Edges carry observations, weighted by how many distinct findings back them. A
directed ``flow`` edge joins the canonical ``src_ip`` to ``dst_ip``; every
other co-naming is an undirected ``link``. Analyst-excluded addresses never
become nodes — a finding left with nothing else is Unattributed.

Everything here is a pure function of its arguments: no clock (``generated_at``
is injectable), no database, no module state — which is what makes the layout
and the whole payload reproducible for a given set of rows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
)

from core.storage.ip_exclusion_repository import FINDING_IP_KEYS
from core.storage.schemas.twin import (
    TwinEdgeSchema,
    TwinGraphSchema,
    TwinNodeSchema,
)
from core.time import utcnow

# The severity buckets the console's severity tokens know (--crit, --high,
# --med, --ok). The four keys are always present (zeros included) so a reader
# never has to .get(); a stored severity outside the four — or none — counts
# under "unranked" when it occurs, mirroring the dashboard's own
# missing-severity bucket rather than dropping the finding from the counts.
SEVERITY_BUCKETS = ("crit", "high", "med", "low")
UNRANKED = "unranked"

NodeKind = Literal["host", "ip", "user", "unattributed"]
EdgeKind = Literal["flow", "link"]

_SEVERITY_ALIASES = {
    "critical": "crit",
    "crit": "crit",
    "high": "high",
    "medium": "med",
    "med": "med",
    "low": "low",
}

UNATTRIBUTED_ID = "unattributed"
UNATTRIBUTED_LABEL = "Unattributed"

# Rings, innermost first: hosts anchor the map, addresses orbit them,
# accounts orbit those, and the Unattributed sink sits outermost.
_RING_ORDER = {"host": 0, "ip": 1, "user": 2, "unattributed": 3}
_RING_SPACING = 220.0


def _field(row: Any, name: str) -> Any:
    """Read ``name`` off a finding row: an ORM instance or a plain mapping."""
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _string_list(value: Any) -> List[str]:
    """A scalar or a list of scalars (the two shapes these JSONB keys hold),
    stripped and emptied of blanks."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def _scalar_text(value: Any) -> Optional[str]:
    """One scalar as text, or None for absent, empty and structured values."""
    if (
        value is None
        or isinstance(value, bool)
        or isinstance(value, (dict, list, tuple))
    ):
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class _Entity:
    id: str
    kind: NodeKind
    label: str


def _host_id(name: str) -> str:
    # DNS names are case-insensitive; the id folds case so "Web-01" and
    # "web-01" are one node, while the label keeps the first-seen spelling.
    return f"host:{name.lower()}"


def _ip_id(address: str) -> str:
    return f"ip:{address}"


def _user_id(name: str) -> str:
    # Account identities are folded like hosts: the same account arrives in
    # mixed spellings across sources, and one node per spelling would shred
    # the map.
    return f"user:{name.lower()}"


def _finding_entities(entity_context: Any, excluded: FrozenSet[str]) -> List[_Entity]:
    """The entities one finding names, exclusions applied.

    Group order is fixed (hosts, IPs, users) and each group is sorted by node
    id: JSONB does not preserve object key order, so iterating the context as
    stored would not be deterministic across a storage round-trip.
    """
    if not isinstance(entity_context, Mapping):
        return []

    hosts = _string_list(entity_context.get("hostnames"))
    if not hosts:
        # CrowdStrike sends device_id and no hostnames (sources disagree on
        # coverage); until a hostname is seen, the device id is the host.
        device_id = _scalar_text(entity_context.get("device_id"))
        if device_id:
            hosts = [device_id]

    addresses: List[str] = []
    seen = set()
    for key in FINDING_IP_KEYS:
        for address in _string_list(entity_context.get(key)):
            if address in excluded or address in seen:
                continue
            seen.add(address)
            addresses.append(address)

    users = _string_list(entity_context.get("usernames"))

    entities: List[_Entity] = []
    groups: Tuple[Tuple[NodeKind, List[str], Callable[[str], str]], ...] = (
        ("host", hosts, _host_id),
        ("ip", addresses, _ip_id),
        ("user", users, _user_id),
    )
    for kind, values, node_id in groups:
        # First spelling of an id wins the label; the dict dedupes the rest.
        spelled: Dict[str, str] = {}
        for value in values:
            spelled.setdefault(node_id(value), value)
        for entity_id, label in sorted(spelled.items()):
            entities.append(_Entity(entity_id, kind, label))
    return entities


def _severity_bucket(severity: Any) -> str:
    return _SEVERITY_ALIASES.get(str(severity or "").strip().lower(), UNRANKED)


@dataclass
class _Node:
    id: str
    kind: NodeKind
    label: str
    finding_ids: set = field(default_factory=set)
    case_ids: set = field(default_factory=set)
    severity_counts: Dict[str, int] = field(
        default_factory=lambda: {bucket: 0 for bucket in SEVERITY_BUCKETS}
    )

    def record(self, finding_id: str, severity: Any, case_ids: set) -> None:
        self.finding_ids.add(finding_id)
        self.case_ids |= case_ids
        bucket = _severity_bucket(severity)
        self.severity_counts[bucket] = self.severity_counts.get(bucket, 0) + 1


class _Edge:
    __slots__ = ("source", "target", "kind", "finding_ids")

    def __init__(self, source: str, target: str, kind: EdgeKind) -> None:
        self.source = source
        self.target = target
        self.kind = kind
        self.finding_ids: set = set()

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.source}->{self.target}"


def _link_key(source: str, target: str) -> Tuple[str, str]:
    # Links are undirected co-namings; fold the pair so both orders share one
    # edge. Flow stays directed and is keyed as given.
    return (source, target) if source < target else (target, source)


def _layout(nodes: List[TwinNodeSchema]) -> None:
    """Concentric rings by kind, angles spread from the top, clockwise.

    Radius depends only on the ring, so two rings can never collide, and a
    lone node sits at the top of its own ring rather than stacked at the
    origin. The client may drag freely; this is only the first paint.
    """
    groups: Dict[str, List[TwinNodeSchema]] = {}
    for node in nodes:
        groups.setdefault(node.kind, []).append(node)
    for kind, group in groups.items():
        radius = (_RING_ORDER[kind] + 1) * _RING_SPACING
        count = len(group)
        for index, node in enumerate(group):
            angle = 2 * math.pi * index / count - math.pi / 2
            node.x = round(radius * math.cos(angle), 2)
            node.y = round(radius * math.sin(angle), 2)


def build_graph(
    findings: Iterable[Any],
    cases_by_finding: Optional[Mapping[str, Iterable[str]]] = None,
    excluded_ips: Iterable[str] = (),
    *,
    generated_at: Optional[datetime] = None,
) -> TwinGraphSchema:
    """Pin every finding to the entities it names and return the whole map.

    ``findings`` are ORM rows or mappings exposing ``finding_id``,
    ``entity_context`` and ``severity``. ``cases_by_finding`` maps finding id
    to the case ids joined through ``case_findings``. ``excluded_ips`` are the
    actively excluded addresses; they never become nodes.

    Severity counts include findings of every status: a closed finding still
    happened on the node it names, and the counts must keep summing to the
    node's ``finding_ids``. Filtering by disposition is the screen's job.
    """
    cases: Mapping[str, Iterable[str]] = cases_by_finding or {}
    excluded = frozenset(excluded_ips)

    nodes: Dict[str, _Node] = {}
    edges: Dict[Tuple[str, str, str], _Edge] = {}
    unattributed = _Node(
        id=UNATTRIBUTED_ID, kind="unattributed", label=UNATTRIBUTED_LABEL
    )

    for row in sorted(findings, key=lambda item: _field(item, "finding_id")):
        finding_id = _field(row, "finding_id")
        entity_context = _field(row, "entity_context")
        severity = _field(row, "severity")
        case_ids = set(cases.get(finding_id, ()))

        entities = _finding_entities(entity_context, excluded)
        if not entities:
            # Nothing recognizable: the finding stays on the map at the sink.
            unattributed.record(finding_id, severity, case_ids)
            continue

        for entity in entities:
            node = nodes.get(entity.id)
            if node is None:
                node = _Node(id=entity.id, kind=entity.kind, label=entity.label)
                nodes[entity.id] = node
            node.record(finding_id, severity, case_ids)

        if len(entities) < 2:
            continue

        context = entity_context if isinstance(entity_context, Mapping) else {}
        claimed: set = set()

        # Flow: the canonical src→dst aliases, directed as observed.
        for src in _string_list(context.get("src_ip")):
            if _ip_id(src) in excluded:
                continue
            for dst in _string_list(context.get("dst_ip")):
                if dst == src or _ip_id(dst) in excluded:
                    continue
                key = ("flow", _ip_id(src), _ip_id(dst))
                edge = edges.get(key)
                if edge is None:
                    edge = _Edge(_ip_id(src), _ip_id(dst), "flow")
                    edges[key] = edge
                edge.finding_ids.add(finding_id)
                claimed.add((key[1], key[2]))

        # Link: the rest of the co-namings, chained in id order so a finding
        # naming N entities costs N-1 edges, never a quadratic fan.
        chain = [entity.id for entity in entities]
        for left, right in zip(chain, chain[1:]):
            a, b = _link_key(left, right)
            if (a, b) in claimed:
                continue
            key = ("link", a, b)
            edge = edges.get(key)
            if edge is None:
                edge = _Edge(a, b, "link")
                edges[key] = edge
            edge.finding_ids.add(finding_id)

    ordered_nodes = sorted(nodes.values(), key=lambda node: (node.id, node.kind))
    schema_nodes = [
        TwinNodeSchema(
            id=node.id,
            kind=node.kind,
            label=node.label,
            finding_ids=sorted(node.finding_ids),
            case_ids=sorted(node.case_ids),
            severity_counts=dict(node.severity_counts),
        )
        for node in ordered_nodes
    ]

    unattributed_ids = sorted(unattributed.finding_ids)
    if unattributed_ids:
        schema_nodes.append(
            TwinNodeSchema(
                id=unattributed.id,
                kind=unattributed.kind,
                label=unattributed.label,
                finding_ids=unattributed_ids,
                case_ids=sorted(unattributed.case_ids),
                severity_counts=dict(unattributed.severity_counts),
            )
        )

    ordered_edges = sorted(
        edges.values(), key=lambda edge: (edge.kind, edge.source, edge.target)
    )
    schema_edges = [
        TwinEdgeSchema(
            id=edge.id,
            source=edge.source,
            target=edge.target,
            kind=edge.kind,
            weight=len(edge.finding_ids),
            finding_ids=sorted(edge.finding_ids),
        )
        for edge in ordered_edges
    ]

    _layout(schema_nodes)
    return TwinGraphSchema(
        generated_at=generated_at or utcnow(),
        nodes=schema_nodes,
        edges=schema_edges,
        unattributed_finding_ids=unattributed_ids,
    )
