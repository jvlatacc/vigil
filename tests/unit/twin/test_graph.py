"""Unit tests for the pure twin-graph derivation (``core.twin.graph``).

The six fixtures spec V1 asks for — hostnames-only; src/dst + ports;
CrowdStrike ``device_id``-only; an excluded IP; a multi-entity finding (edge +
weight); a zero-entity finding (Unattributed) — plus the invariants the
derivation promises around them: case links, severity bucketing, flow/link
distinctness, determinism, and layout.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.twin.graph import build_graph

pytestmark = pytest.mark.unit

STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)


def row(finding_id, entity_context=None, severity="high", status="new"):
    """A finding as the router hands it to build_graph (mappings are accepted)."""
    return SimpleNamespace(
        finding_id=finding_id,
        entity_context=entity_context,
        severity=severity,
        status=status,
    )


def node_ids(graph):
    return [node.id for node in graph.nodes]


# ---------------------------------------------------------------------------
# V1 fixture 1: hostnames-only
# ---------------------------------------------------------------------------


def test_hostnames_only_becomes_one_host_node():
    graph = build_graph(
        [row("f-1", {"hostnames": ["web-01"]}, severity="critical")],
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:web-01"]
    node = graph.nodes[0]
    assert (node.kind, node.label) == ("host", "web-01")
    assert node.finding_ids == ["f-1"]
    assert node.severity_counts == {"crit": 1, "high": 0, "med": 0, "low": 0}
    assert graph.edges == []
    assert graph.unattributed_finding_ids == []


def test_host_id_folds_case_but_keeps_the_first_label():
    graph = build_graph(
        [
            row("f-1", {"hostnames": ["Web-01"]}),
            row("f-2", {"hostnames": ["web-01"]}),
        ],
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:web-01"]
    assert graph.nodes[0].label == "Web-01"
    assert graph.nodes[0].finding_ids == ["f-1", "f-2"]


# ---------------------------------------------------------------------------
# V1 fixture 2: src/dst + ports
# ---------------------------------------------------------------------------


def test_canonical_src_dst_makes_one_directed_flow_edge():
    graph = build_graph(
        [
            row(
                "f-1",
                {
                    "src_ip": "10.0.4.12",
                    "dst_ip": "10.0.4.13",
                    "src_port": "443",
                    "dst_port": "8080",
                    "proto": "tcp",
                },
            )
        ],
        generated_at=STAMP,
    )

    assert sorted(node_ids(graph)) == ["ip:10.0.4.12", "ip:10.0.4.13"]
    (edge,) = graph.edges
    assert (
        edge.kind,
        edge.source,
        edge.target,
        edge.weight,
        edge.finding_ids,
    ) == ("flow", "ip:10.0.4.12", "ip:10.0.4.13", 1, ["f-1"])


def test_plural_dst_ips_are_links_not_flow():
    # Flow requires both ends to come from the canonical singular aliases;
    # Splunk's dest_ips list co-names its addresses, it does not direct them.
    graph = build_graph(
        [
            row(
                "f-1",
                {"src_ip": "10.0.4.12", "dst_ips": ["10.0.4.13", "10.0.4.14"]},
            )
        ],
        generated_at=STAMP,
    )

    assert [edge.kind for edge in graph.edges] == ["link", "link"]
    assert all(edge.weight == 1 for edge in graph.edges)


# ---------------------------------------------------------------------------
# V1 fixture 3: CrowdStrike device_id-only
# ---------------------------------------------------------------------------


def test_device_id_with_no_hostname_is_the_host():
    graph = build_graph(
        [row("f-1", {"device_id": "abc123", "usernames": ["j.vanlowe"]})],
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:abc123", "user:j.vanlowe"]
    assert graph.nodes[0].label == "abc123"
    assert graph.nodes[0].kind == "host"


def test_hostname_outranks_device_id():
    graph = build_graph(
        [row("f-1", {"hostnames": ["web-01"], "device_id": "abc123"})],
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:web-01"]


# ---------------------------------------------------------------------------
# V1 fixture 4: an excluded IP
# ---------------------------------------------------------------------------


def test_excluded_ip_never_becomes_a_node():
    graph = build_graph(
        [
            row("f-1", {"src_ip": "203.0.113.9", "hostnames": ["web-01"]}),
            row("f-2", {"ip": "203.0.113.9"}, severity="low"),
        ],
        excluded_ips={"203.0.113.9"},
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:web-01", "unattributed"]
    assert "ip:203.0.113.9" not in node_ids(graph)
    # f-2 named nothing that survived the exclusion: it stays on the map.
    assert graph.unattributed_finding_ids == ["f-2"]
    unattributed = graph.nodes[-1]
    assert unattributed.severity_counts["low"] == 1
    assert graph.nodes[0].finding_ids == ["f-1"]


def test_apply_exclusions_false_restores_the_ip_node():
    graph = build_graph(
        [row("f-1", {"src_ip": "203.0.113.9", "hostnames": ["web-01"]})],
        excluded_ips=set(),
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["host:web-01", "ip:203.0.113.9"]
    assert graph.unattributed_finding_ids == []


# ---------------------------------------------------------------------------
# V1 fixture 5: multi-entity finding -> edge + weight
# ---------------------------------------------------------------------------


def test_two_findings_naming_the_same_pair_weight_one_edge():
    graph = build_graph(
        [
            row("f-1", {"hostnames": ["web-01"], "usernames": ["j.vanlowe"]}),
            row("f-2", {"hostnames": ["web-01"], "usernames": ["j.vanlowe"]}),
            # A third finding that names only one of the two: no new edge.
            row("f-3", {"hostnames": ["web-01"]}),
        ],
        generated_at=STAMP,
    )

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.kind, edge.source, edge.target) == (
        "link",
        "host:web-01",
        "user:j.vanlowe",
    )
    assert edge.weight == 2
    assert edge.finding_ids == ["f-1", "f-2"]


def test_a_flow_pair_earns_no_duplicate_link_from_the_same_finding():
    graph = build_graph(
        [row("f-1", {"src_ip": "10.0.4.12", "dst_ip": "10.0.4.13"})],
        generated_at=STAMP,
    )

    assert [edge.kind for edge in graph.edges] == ["flow"]


# ---------------------------------------------------------------------------
# V1 fixture 6: zero-entity finding -> Unattributed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entity_context",
    [
        None,
        {},
        {"src_port": "22"},  # non-entity keys do not attribute either
    ],
    ids=["none", "empty", "ports-only"],
)
def test_zero_entity_finding_lands_on_the_single_unattributed_node(entity_context):
    graph = build_graph(
        [
            row("f-1", entity_context, severity="med"),
            row("f-2", entity_context),
        ],
        generated_at=STAMP,
    )

    assert node_ids(graph) == ["unattributed"]
    node = graph.nodes[0]
    assert (node.kind, node.label) == ("unattributed", "Unattributed")
    assert node.finding_ids == ["f-1", "f-2"]
    assert graph.unattributed_finding_ids == ["f-1", "f-2"]
    assert node.severity_counts["med"] == 1
    assert node.severity_counts["high"] == 1


def test_no_unattributed_node_when_every_finding_names_an_entity():
    graph = build_graph(
        [row("f-1", {"hostnames": ["web-01"]})],
        generated_at=STAMP,
    )

    assert "unattributed" not in node_ids(graph)
    assert graph.unattributed_finding_ids == []


# ---------------------------------------------------------------------------
# Context the spec pins beyond the six fixtures
# ---------------------------------------------------------------------------


def test_case_ids_join_through_the_map_argument():
    graph = build_graph(
        [
            row("f-1", {"hostnames": ["web-01"]}),
            row("f-2", {"hostnames": ["web-01"]}),
        ],
        cases_by_finding={"f-1": ["case-2", "case-1"], "f-2": ["case-1"]},
        generated_at=STAMP,
    )

    assert graph.nodes[0].case_ids == ["case-1", "case-2"]


def test_severity_buckets_normalize_and_never_drop_a_finding():
    graph = build_graph(
        [
            row("f-1", {"hostnames": ["web-01"]}, severity="Critical"),
            row("f-2", {"hostnames": ["web-01"]}, severity=None),
            row("f-3", {"hostnames": ["web-01"]}, severity="sev3"),
        ],
        generated_at=STAMP,
    )

    node = graph.nodes[0]
    assert node.severity_counts["crit"] == 1
    assert node.severity_counts["unranked"] == 2
    assert sum(node.severity_counts.values()) == len(node.finding_ids)


def test_same_rows_build_the_same_graph_including_layout():
    findings = [
        row("f-1", {"hostnames": ["web-01"], "src_ip": "10.0.4.12"}),
        row("f-2", {"usernames": ["j.vanlowe"]}),
    ]

    first = build_graph(findings, generated_at=STAMP)
    second = build_graph(list(reversed(findings)), generated_at=STAMP)

    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.unattributed_finding_ids == second.unattributed_finding_ids


def test_layout_places_kinds_on_distinct_concentric_rings():
    graph = build_graph(
        [
            row("f-1", {"hostnames": ["web-01"]}),
            row("f-2", {"hostnames": ["db-01"]}),
            row("f-3", {"ip": "10.0.4.12"}),
            row("f-4", {"usernames": ["j.vanlowe"]}),
        ],
        generated_at=STAMP,
    )

    by_id = {node.id: node for node in graph.nodes}

    def radius(node):
        return round(math.hypot(node.x, node.y), 2)

    assert radius(by_id["host:db-01"]) == 220.0  # innermost ring
    assert radius(by_id["host:web-01"]) == 220.0
    assert radius(by_id["ip:10.0.4.12"]) == 440.0
    assert radius(by_id["user:j.vanlowe"]) == 660.0
    assert all(node.x is not None and node.y is not None for node in graph.nodes)


def test_generated_at_defaults_to_the_clock_when_not_injected():
    graph = build_graph([], generated_at=None)

    assert graph.generated_at.tzinfo is None  # naive UTC, like the columns
