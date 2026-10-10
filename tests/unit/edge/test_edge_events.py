"""Direct contracts of the edge journal importer.

The route suite proves the end-to-end path (durable acks, replay dedup,
approval provenance). This suite pins the importer's own edges: batch size
is a programming error (the route bounds it to 413), malformed events are
reported per event rather than failing the batch, and the derived row ids
are stable — a replayed event always lands on the row it created.
"""

from __future__ import annotations

import pytest

from core.edge import events
from core.storage.models import EdgeNode

pytestmark = pytest.mark.unit


def _node(node_id: str = "gw-x") -> EdgeNode:
    return EdgeNode(node_id=node_id, segment_scope={}, credential_hash="x" * 64)


class TestBatchBounds:
    def test_oversized_batch_is_a_caller_error(self):
        with pytest.raises(ValueError, match="exceeds"):
            events.import_events(_node(), [{"event_id": f"e{i}"} for i in range(501)])


class TestValidation:
    def test_each_malformed_shape_is_rejected_with_a_reason(self):
        result = events.import_events(
            _node(),
            [
                "not-a-dict",
                {
                    "event_id": "",
                    "kind": "observation",
                    "occurred_at": "2026-10-09T00:00:00Z",
                },
                {
                    "event_id": "e-kind",
                    "kind": "quantum",
                    "occurred_at": "2026-10-09T00:00:00Z",
                },
                {
                    "event_id": "e-time",
                    "kind": "observation",
                    "occurred_at": "yesterday-ish",
                },
                {
                    "event_id": "e-payload",
                    "kind": "observation",
                    "occurred_at": "2026-10-09T00:00:00Z",
                    "payload": [1],
                },
                {
                    "event_id": "e-action",
                    "kind": "action",
                    "occurred_at": "2026-10-09T00:00:00Z",
                    "action": {"action_type": "quarantine_file", "target": "f"},
                },
            ],
        )
        assert result.accepted == []  # nothing stored without a database anyway
        reasons = [r["reason"] for r in result.rejected]
        assert len(reasons) == 6  # every malformed event reported, none dropped
        assert any("JSON object" in r for r in reasons)
        assert any(r.startswith("kind must be one of") for r in reasons)
        assert any(r.startswith("occurred_at") for r in reasons)
        assert any(r.startswith("payload") for r in reasons)
        assert any(r.startswith("action_type must be one of") for r in reasons)


class TestDerivedIdentity:
    def test_finding_source_is_bounded_and_prefixed(self):
        assert events.finding_source_for("gw-x") == "edge:gw-x"
        assert len(events.finding_source_for("n" * 44)) == 49

    def test_finding_id_is_a_pure_function_of_source_and_event(self):
        first = events._finding_id("edge:gw-x", "ev-1")
        again = events._finding_id("edge:gw-x", "ev-1")
        other = events._finding_id("edge:gw-x", "ev-2")
        assert first == again
        assert first != other
        assert first.startswith("edge-")
        assert len(first) <= 50  # the findings.finding_id column

    def test_confidence_is_clamped_into_the_pipeline_domain(self):
        assert events._bounded_confidence("1.5") == 1.0
        assert events._bounded_confidence(-3) == 0.0
        assert events._bounded_confidence("garbage") == 0.0
        assert events._bounded_confidence(None) == 0.0
        assert events._bounded_confidence(0.87) == 0.87
