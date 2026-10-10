"""Transform tests: rows_to_document over fixture row dicts, no database.

Counts and ids are asserted exactly (the fixture scenario is small enough to
hold in your head), relations against the spec's link table, and the
normalization against the defanged values threat intel writes.
"""

import json

from vigilmap.export import export_memory

EXPECTED_ENTITIES = {
    "domain:evildomain.com",
    "ip:203.0.113.7",
    "email:billing@vendor.example",
    "url:http://evildomain.com/payload",
    "user:j.wilson",
    "host:ws-0403",
}
EXPECTED_HUNTS = {"investigation:hunt:h-001", "investigation:hunt:h-002"}


def build(rows, **kwargs):
    return export_memory.rows_to_document(
        rows["sightings"],
        rows["verdicts"],
        rows["verdict_sources"],
        rows["gaps"],
        source="export",
        generated_at="2026-09-15T09:00:00+00:00",
        **kwargs,
    )


def nodes_of_kind(document, kind):
    return [n for n in document["nodes"] if n["kind"] == kind]


def links_of_relation(document, relation):
    return [link for link in document["links"] if link["relation"] == relation]


def test_document_envelope(rows):
    document = build(rows)
    assert document["schemaVersion"] == 1
    assert document["generatedAt"] == "2026-09-15T09:00:00+00:00"
    assert document["source"] == "export"


def test_node_counts_by_kind(rows):
    document = build(rows)
    counts = {
        kind: len(nodes_of_kind(document, kind))
        for kind in ("entity", "sighting", "verdict", "gap", "hunt")
    }
    # 6 entities, 4 sightings, 4 verdicts, 1 gap, 2 hunt (investigation) nodes.
    assert counts == {"entity": 6, "sighting": 4, "verdict": 4, "gap": 1, "hunt": 2}
    assert {n["id"] for n in nodes_of_kind(document, "entity")} == EXPECTED_ENTITIES
    assert {n["id"] for n in nodes_of_kind(document, "hunt")} == EXPECTED_HUNTS


def test_every_exportable_relation_present(rows):
    document = build(rows)
    relations = {link["relation"] for link in document["links"]}
    # The exporter emits six of the seven contract relations: episode-entity
    # has no episodic producer — the episode kind stays sample-data-only.
    assert relations == {
        "sighting-of",
        "verdict-subject",
        "verdict-source",
        "gap-subject",
        "hunt-verdict",
        "hunt-gap",
    }


def test_verdict_subject_join_with_defang_normalization(rows):
    document = build(rows)
    subjects = {
        link["target"]
        for link in links_of_relation(document, "verdict-subject")
        if link["source"] == "verdict-1"
    }
    # Stored defanged forms join the same minted entity nodes recall queries.
    assert subjects == {"domain:evildomain.com", "ip:203.0.113.7", "user:j.wilson"}


def test_verdict_source_join_follows_investigation_and_system(rows):
    document = build(rows)
    verdict_source = {
        (link["source"], link["target"])
        for link in links_of_relation(document, "verdict-source")
    }
    # verdict 1 cites wazuh and edr; its hunt's sightings from those systems
    # are the evidence. verdict 2 cites phishfeed. The duplicate wazuh source
    # row is one link, not two.
    assert verdict_source == {
        ("verdict-1", "sighting-1"),
        ("verdict-1", "sighting-2"),
        ("verdict-2", "sighting-3"),
    }


def test_zero_subject_verdict_is_legal(rows):
    document = build(rows)
    verdict_3_subjects = [
        link
        for link in links_of_relation(document, "verdict-subject")
        if link["source"] == "verdict-3"
    ]
    # "Is there any lateral movement at all" names none; the schema writes it,
    # and the exporter neither crashes nor invents a subject.
    assert verdict_3_subjects == []


def test_techniques_are_sorted_verdict_attributes(rows):
    document = build(rows)
    verdict_1 = next(
        n for n in nodes_of_kind(document, "verdict") if n["id"] == "verdict-1"
    )
    assert verdict_1["techniques"] == ["T1071", "T1566"]
    verdict_3 = next(
        n for n in nodes_of_kind(document, "verdict") if n["id"] == "verdict-3"
    )
    assert verdict_3["techniques"] == []  # None from the row is known-to-be-none


def test_no_dangling_links(rows):
    document = build(rows)
    ids = {n["id"] for n in document["nodes"]}
    for link in document["links"]:
        assert link["source"] in ids, link
        assert link["target"] in ids, link


def test_entity_key_prefix_holds(rows):
    document = build(rows)
    for node in nodes_of_kind(document, "entity"):
        assert node["entityKey"].startswith(node["entityType"] + ":")
        assert node["label"]  # the value half survived


def test_unknown_entity_type_drops_its_rows(rows):
    rows["sightings"].append(
        # a Case IOC typed outside the eleven-type vocabulary
        dict(rows["sightings"][0], id=5, entity_key="mutex:lateral_svc")
    )
    drops = []
    document = build(rows, on_drop=drops.append)
    assert "mutex:lateral_svc" not in {n["id"] for n in document["nodes"]}
    assert "sighting-5" not in {n["id"] for n in document["nodes"]}
    assert "unknown-entity-type:mutex" in drops
    assert "sighting-5:unanchored" in drops


def test_empty_entity_key_drops_cleanly(rows):
    rows["sightings"].append(dict(rows["sightings"][0], id=6, entity_key=""))
    drops = []
    build(rows, on_drop=drops.append)
    assert "empty-entity-key" in drops
    assert "sighting-6:unanchored" in drops


def test_no_episode_nodes(rows):
    document = build(rows)
    # The exporter has no episode producer; the kind belongs to the sample data.
    assert nodes_of_kind(document, "episode") == []


def test_hunt_context_fields(rows):
    document = build(rows)
    hunt_002 = next(
        n
        for n in nodes_of_kind(document, "hunt")
        if n["id"] == "investigation:hunt:h-002"
    )
    assert hunt_002["objective"] == "hunt investigation h-002"
    assert hunt_002["startedAt"] == "2026-09-14T08:00:00+00:00"
    assert hunt_002["endedAt"] == "2026-09-15T09:00:00+00:00"


def test_sighting_nodes_carry_the_window(rows):
    document = build(rows)
    sighting_1 = next(
        n for n in nodes_of_kind(document, "sighting") if n["id"] == "sighting-1"
    )
    assert sighting_1["entityKey"] == "domain:evildomain.com"
    assert sighting_1["observedFrom"] == "2026-09-14T08:00:00+00:00"
    assert sighting_1["observedTo"] == "2026-09-14T18:30:00+00:00"
    assert sighting_1["investigationId"] == "investigation:hunt:h-002"


def test_case_significant_types_survive(rows):
    rows["verdicts"][0]["subject_entities"].append(
        "arn:aws:iam::123456789012:role/Admin"
    )
    document = build(rows)
    subjects = {
        link["target"]
        for link in links_of_relation(document, "verdict-subject")
        if link["source"] == "verdict-1"
    }
    # Folding an ARN's resource part would merge two principals into one key.
    assert "arn:aws:iam::123456789012:role/Admin" in subjects
    assert any(
        n["id"] == "arn:aws:iam::123456789012:role/Admin"
        for n in nodes_of_kind(document, "entity")
    )


def test_string_timestamps_pass_through(rows):
    rows["verdicts"][0]["concluded_at"] = "2026-09-15T09:00:00Z"
    document = build(rows)
    verdict_1 = next(
        n for n in nodes_of_kind(document, "verdict") if n["id"] == "verdict-1"
    )
    assert verdict_1["concludedAt"] == "2026-09-15T09:00:00Z"


def test_deterministic_ordering(rows):
    document_a = build(rows)
    document_b = build(rows)
    assert document_a == document_b
    assert document_a["nodes"] == sorted(
        document_a["nodes"], key=lambda n: (n["kind"], n["id"])
    )
    assert document_a["links"] == sorted(
        document_a["links"],
        key=lambda edge: (edge["relation"], edge["source"], edge["target"]),
    )


def test_document_is_json_serializable(rows):
    document = build(rows)
    # The exporter's whole output is one JSON document; nothing may survive
    # that is not round-trippable (datetimes included).
    assert json.loads(json.dumps(document)) == document


def test_transform_is_pure(rows):
    before = json.dumps(rows, sort_keys=True, default=str)
    build(rows)
    assert json.dumps(rows, sort_keys=True, default=str) == before


def test_empty_document_is_valid():
    document = export_memory.rows_to_document(
        [], [], [], [], source="export", generated_at="2026-09-15T09:00:00+00:00"
    )
    assert document == {
        "schemaVersion": 1,
        "generatedAt": "2026-09-15T09:00:00+00:00",
        "source": "export",
        "nodes": [],
        "links": [],
    }
