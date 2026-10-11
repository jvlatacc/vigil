"""Entity graph behavior (spec AC 3).

Two shapes of evidence live here: correlation correctness (cross-host
events form edges; the multi-hop query returns the chain inside the
window and only inside it) and bounded durability (caps stop growth with
a visible metric; a snapshot round-trip through JSON rebuilds the graph
exactly). The window boundary tests pin the inclusive-cutoff semantics
the rules will lean on.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.cep.graph import (
    NODE_KINDS,
    EntityGraph,
    GraphPath,
    GraphRestoreError,
)

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def later(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


# -- cross-host events form edges -----------------------------------------


def test_cross_host_events_form_edges():
    g = EntityGraph()
    g.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)
    g.link(("host", "web-1"), "connected_to", ("host", "db-1"), later(30))

    assert g.node_count == 3  # the finding plus the two hosts
    assert g.edge_count == 2
    assert g.stats["cep_graph_edges"] == 2
    assert g.stats["cep_graph_nodes"] == 3


def test_finding_points_at_the_host_it_was_observed_in():
    g = EntityGraph()
    g.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)

    assert g.neighbors(("finding", "f-1")) == (("host", "web-1"),)
    # and the direction does not read backwards
    assert g.neighbors(("host", "web-1")) == ()


def test_relinking_an_edge_refreshes_its_timestamp_without_growing():
    g = EntityGraph()
    assert g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    assert g.link(("host", "a"), "connected_to", ("host", "b"), later(45))
    assert g.link(("host", "a"), "connected_to", ("host", "b"), T0)  # late backfill

    assert g.edge_count == 1
    # The edge survived at the refreshed (later) time: within 30s of
    # T0+50 means ts >= T0+20 — a regressed ts of T0 would answer None.
    path = g.path_exists(("host", "a"), ("host", "b"), within_seconds=30, now=later(50))
    assert path is not None


def test_repeat_observation_touches_last_seen_never_backwards():
    g = EntityGraph()
    g.observe_node("host", "web-1", T0)
    g.observe_node("host", "web-1", later(90))
    node = g.node(("host", "web-1"))
    assert node is not None
    assert node.first_seen == T0
    assert node.last_seen == later(90)

    g.observe_node("host", "web-1", T0)  # a stale producer must not regress
    node = g.node(("host", "web-1"))
    assert node is not None
    assert node.last_seen == later(90)


def test_unknown_kind_value_or_relation_is_rejected():
    g = EntityGraph()
    with pytest.raises(ValueError):
        g.observe_node("hosts", "web-1", T0)
    with pytest.raises(ValueError):
        g.observe_node("host", "", T0)
    g.link(("host", "a"), "observed_in", ("host", "b"), T0)
    with pytest.raises(ValueError):
        g.link(("host", "a"), "talked_to", ("host", "b"), T0)


def test_shipped_node_kinds_cover_the_spec():
    assert NODE_KINDS == {"host", "user", "ip", "finding"}


# -- multi-hop path inside the window -------------------------------------


def _two_host_chain(g: EntityGraph) -> None:
    """f-1 observed in web-1, web-1 linked to db-1, db-1 observed f-9."""
    g.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)
    g.link(("host", "web-1"), "connected_to", ("host", "db-1"), later(30))
    g.link(("host", "db-1"), "observed_in", ("finding", "f-9"), later(60))


def test_multihop_path_returns_the_chain_inside_the_window():
    g = EntityGraph()
    _two_host_chain(g)

    path = g.path_exists(
        ("finding", "f-1"), ("finding", "f-9"), within_seconds=120, now=later(70)
    )
    assert isinstance(path, GraphPath)
    assert path.nodes == (
        ("finding", "f-1"),
        ("host", "web-1"),
        ("host", "db-1"),
        ("finding", "f-9"),
    )
    assert [edge.relation for edge in path.edges] == [
        "observed_in",
        "connected_to",
        "observed_in",
    ]
    # the evidence carries timestamps, not just the shape
    assert path.edges[0].ts == T0


def test_path_vanishes_when_every_edge_is_outside_the_window():
    g = EntityGraph()
    _two_host_chain(g)

    path = g.path_exists(
        ("finding", "f-1"), ("finding", "f-9"), within_seconds=120, now=later(3600)
    )
    assert path is None


def test_window_boundary_is_inclusive_at_the_cutoff():
    g = EntityGraph()
    g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    # anchor - within_seconds == T0 exactly -> the edge is still inside
    path = g.path_exists(("host", "a"), ("host", "b"), within_seconds=60, now=later(60))
    assert path is not None
    # one second older and it is gone
    path = g.path_exists(("host", "a"), ("host", "b"), within_seconds=60, now=later(61))
    assert path is None


def test_no_path_across_disconnected_entities():
    g = EntityGraph()
    g.link(("finding", "f-1"), "observed_in", ("host", "web-1"), T0)
    g.link(("finding", "f-9"), "observed_in", ("host", "db-9"), T0)

    path = g.path_exists(
        ("finding", "f-1"), ("finding", "f-9"), within_seconds=600, now=later(1)
    )
    assert path is None


def test_traversal_follows_direction_not_wishes():
    g = EntityGraph()
    # db-1 -> web-1 direction only; asking backwards must not find a path
    g.link(("host", "db-1"), "connected_to", ("host", "web-1"), T0)
    backwards = g.path_exists(
        ("host", "web-1"), ("host", "db-1"), within_seconds=600, now=later(1)
    )
    forwards = g.path_exists(
        ("host", "db-1"), ("host", "web-1"), within_seconds=600, now=later(1)
    )
    assert backwards is None
    assert forwards is not None


def test_path_to_self_is_the_trivial_chain():
    g = EntityGraph()
    g.observe_node("host", "web-1", T0)
    path = g.path_exists(("host", "web-1"), ("host", "web-1"), within_seconds=60)
    assert path is not None
    assert path.nodes == (("host", "web-1"),)
    assert path.edges == ()


def test_path_with_missing_endpoint_is_none():
    g = EntityGraph()
    g.observe_node("host", "web-1", T0)
    assert (
        g.path_exists(("host", "web-1"), ("host", "ghost"), within_seconds=60) is None
    )


def test_one_stale_link_kills_the_whole_chain():
    """The window is per-edge: an old pivot must not re-qualify because the
    hops after it are fresh."""
    g = EntityGraph()
    g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    g.link(("host", "b"), "connected_to", ("host", "c"), later(590))

    whole = g.path_exists(
        ("host", "a"), ("host", "c"), within_seconds=100, now=later(595)
    )
    assert whole is None  # a->b is 595s old, outside the 100s window
    tail = g.path_exists(
        ("host", "b"), ("host", "c"), within_seconds=100, now=later(595)
    )
    assert tail is not None


# -- bounded growth --------------------------------------------------------


def test_node_cap_evicts_the_least_recently_observed():
    g = EntityGraph(max_nodes=3)
    g.observe_node("host", "a", T0)
    g.observe_node("host", "b", later(10))
    g.observe_node("host", "c", later(20))
    g.observe_node("host", "d", later(30))  # evicts "a"

    assert g.node_count == 3
    assert g.node(("host", "a")) is None
    assert g.node(("host", "d")) is not None
    assert g.stats["cep_graph_nodes_evicted"] == 1


def test_evicting_a_node_drops_its_edges():
    g = EntityGraph(max_nodes=2)
    g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    g.observe_node("host", "c", later(10))  # evicts "a" (and its edge)

    assert g.node_count == 2
    assert g.edge_count == 0
    assert g.stats["cep_graph_edges"] == 0


def test_edge_cap_rejects_new_links_with_a_metric():
    g = EntityGraph(max_edges=2)
    assert g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    assert g.link(("host", "b"), "connected_to", ("host", "c"), T0)
    assert not g.link(("host", "c"), "connected_to", ("host", "d"), T0)

    assert g.edge_count == 2
    assert g.stats["cep_graph_edges_rejected"] == 1
    # the rejected edge must not answer a path query
    assert g.path_exists(("host", "a"), ("host", "d"), within_seconds=60) is None


def test_edge_cap_still_allows_refreshing_existing_edges():
    g = EntityGraph(max_edges=1)
    assert g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    assert g.link(("host", "a"), "connected_to", ("host", "b"), later(30))
    assert g.edge_count == 1


# -- snapshot round-trip (AC 3's "restores ... exactly") -------------------


def _populated_graph() -> EntityGraph:
    g = EntityGraph()
    _two_host_chain(g)
    g.link(("user", "svc-backup"), "observed_in", ("host", "web-1"), later(5))
    return g


def test_snapshot_roundtrip_through_json_is_exact():
    g = _populated_graph()
    payload = json.loads(json.dumps(g.snapshot()))  # JSON-safety is the point

    restored = EntityGraph()
    restored.restore(payload)

    assert restored.snapshot() == g.snapshot()
    assert restored.node_count == g.node_count
    assert restored.edge_count == g.edge_count


def test_restored_graph_preserves_node_timestamps():
    g = _populated_graph()
    payload = g.snapshot()

    restored = EntityGraph()
    restored.restore(payload)
    original = g.node(("host", "web-1"))
    back = restored.node(("host", "web-1"))
    assert original is not None and back is not None
    assert back.first_seen == original.first_seen
    assert back.last_seen == original.last_seen


def test_restore_replaces_any_prior_state():
    g = EntityGraph()
    g.observe_node("host", "stale", T0)
    g.restore(EntityGraph().snapshot())

    assert g.node_count == 0
    assert g.edge_count == 0


def test_restore_rejects_a_wrong_version():
    payload = EntityGraph().snapshot()
    payload["version"] = 999
    with pytest.raises(GraphRestoreError, match="version"):
        EntityGraph().restore(payload)


def _mutators():
    def drop_nodes(p):
        p.pop("nodes")

    def malformed_node(p):
        p["nodes"].append({"kind": "host"})

    def unknown_kind(p):
        p["nodes"].append(
            {
                "kind": "hosts",
                "value": "x",
                "first_seen": T0.isoformat(),
                "last_seen": T0.isoformat(),
            }
        )

    def edge_without_endpoint(p):
        p["edges"].append(
            {
                "src_kind": "host",
                "src_value": "a",
                "relation": "connected_to",
                "dst_kind": "ghost",
                "dst_value": "b",
                "ts": T0.isoformat(),
            }
        )

    def unknown_relation(p):
        p["edges"][0]["relation"] = "talked_to"

    def duplicate_node(p):
        p["nodes"].append(
            {
                "kind": "host",
                "value": "web-1",
                "first_seen": T0.isoformat(),
                "last_seen": T0.isoformat(),
            }
        )

    return [
        (drop_nodes, "missing nodes list"),
        (malformed_node, "malformed node entry"),
        (unknown_kind, "unknown node kind"),
        (edge_without_endpoint, "edge lacking an endpoint node"),
        (unknown_relation, "unknown relation"),
        (duplicate_node, "duplicate node"),
    ]


@pytest.mark.parametrize(
    "mutate", [m for m, _ in _mutators()], ids=[w for _, w in _mutators()]
)
def test_restore_rejects_malformed_payloads_with_the_reason(mutate):
    payload = _populated_graph().snapshot()
    mutate(payload)
    with pytest.raises(GraphRestoreError):
        EntityGraph().restore(payload)


def test_restore_rejects_payloads_over_the_caps():
    fat_nodes = EntityGraph(max_nodes=2)
    fat_nodes.observe_node("host", "a", T0)
    fat_nodes.observe_node("host", "b", later(1))
    with pytest.raises(GraphRestoreError, match="cap"):
        EntityGraph(max_nodes=1).restore(fat_nodes.snapshot())

    fat_edges = EntityGraph(max_nodes=10)
    fat_edges.link(("host", "a"), "connected_to", ("host", "b"), T0)
    fat_edges.link(("host", "a"), "connected_to", ("host", "c"), T0)
    with pytest.raises(GraphRestoreError, match="cap"):
        EntityGraph(max_nodes=10, max_edges=1).restore(fat_edges.snapshot())


def test_restored_state_survives_further_mutation():
    """Restore is not a read-only copy: the graph keeps accepting events
    after a restore — the daemon boots and continues correlating."""
    g = EntityGraph()
    g.link(("host", "a"), "connected_to", ("host", "b"), T0)
    payload = g.snapshot()

    restored = EntityGraph()
    restored.restore(payload)
    restored.link(("host", "b"), "connected_to", ("host", "c"), later(10))

    assert restored.edge_count == 2
    path = restored.path_exists(
        ("host", "a"), ("host", "c"), within_seconds=60, now=later(11)
    )
    assert path is not None
