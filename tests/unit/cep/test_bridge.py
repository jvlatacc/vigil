"""Unit tests for the CEP response bridge (spec AC 4).

The contract under test: every completed sequence becomes exactly one
``ApprovalService.create_action`` call — mapped ActionType, the match's
confidence untouched, the ``cep:`` idempotency key, and rendered rule
evidence — and the bridge never bypasses the gate: it proposes and the
service decides. A duplicate match inside the dedupe TTL produces no
second call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from core.cep.bridge import (
    CEP_ENGINE_ACTOR,
    CEP_SOURCE,
    CepResponseBridge,
    match_id,
    render_match_evidence,
)
from core.cep.engine import SequenceMatch
from core.response.approval_service import ActionType, ApprovalService, PendingAction


class RecordingApprovals:
    """The gate as a record: every create_action call lands in ``calls``
    verbatim (keyword arguments), and a minimal PendingAction comes back.
    Any other method appearing here would mean the bridge reached past
    create_action — the tests assert it never does."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def create_action(self, **kwargs: Any) -> PendingAction:
        self.calls.append(kwargs)
        return PendingAction(
            action_id=f"action-{len(self.calls)}",
            action_type=kwargs["action_type"],
            title=kwargs["title"],
            description=kwargs["description"],
            target=kwargs["target"],
            confidence=kwargs["confidence"],
            reason=kwargs["reason"],
            evidence=kwargs["evidence"],
            created_at="2026-10-09T00:00:00+00:00",
            created_by=kwargs["created_by"],
            requires_approval=True,
            status="pending",
        )


def _match(**overrides: Any) -> SequenceMatch:
    values: Dict[str, Any] = {
        "rule_id": "ransomware-staging-2src",
        "action_type": "isolate_host",
        "target_field": "host",
        "entity_key": "host=WKS-1",
        "entities": {"host": "WKS-1"},
        "finding_ids": ("cs-1", "spl-1"),
        "sources": ("crowdstrike", "splunk"),
        "confidence": 0.92,
        "started_at": 1000.0,
        "completed_at": 1060.0,
        "window_bucket": 1,
        "graph_path": ("finding:cs-1", "host:WKS-1"),
    }
    values.update(overrides)
    return SequenceMatch(**values)


def _bridge(
    approvals: Any = None, **kwargs: Any
) -> Tuple[CepResponseBridge, RecordingApprovals]:
    approvals = approvals if approvals is not None else RecordingApprovals()
    return CepResponseBridge(approvals, **kwargs), approvals


def test_match_becomes_exactly_one_create_action() -> None:
    bridge, approvals = _bridge()
    action = bridge.fire(_match())

    assert action is not None
    assert len(approvals.calls) == 1
    kwargs = approvals.calls[0]
    # The rule's mapped action type and the target resolved from the
    # match's entity key.
    assert kwargs["action_type"] is ActionType.ISOLATE_HOST
    assert kwargs["target"] == "WKS-1"
    assert kwargs["idempotency_key"] == match_id(_match())
    assert kwargs["created_by"] == CEP_ENGINE_ACTOR
    # Exactly one call even if the same match is fired again immediately.
    bridge.fire(_match())
    assert len(approvals.calls) == 1


def test_idempotency_key_is_cep_namespaced_with_event_time() -> None:
    bridge, approvals = _bridge()
    bridge.fire(_match())
    kwargs = approvals.calls[0]

    assert kwargs["idempotency_key"] == (
        "cep:ransomware-staging-2src:host=WKS-1:1060.000000"
    )


def test_confidence_passes_through_and_no_gating_arguments() -> None:
    bridge, approvals = _bridge()
    bridge.fire(_match(confidence=0.71))
    kwargs = approvals.calls[0]

    # Untouched: the bands are the service's call, and nudging confidence
    # here would be gaming the gate.
    assert kwargs["confidence"] == pytest.approx(0.71)
    for gated in ("human_only", "force_manual_approval", "dry_run", "execute"):
        assert gated not in kwargs


def test_only_the_gate_is_touched() -> None:
    # A spec'd mock records every attribute the bridge reaches for; a
    # bypass (direct execution, an executor call) would show up here.
    gate = MagicMock(spec=ApprovalService)
    gate.create_action.return_value = PendingAction(
        action_id="action-1",
        action_type="isolate_host",
        title="t",
        description="d",
        target="WKS-1",
        confidence=0.92,
        reason="r",
        evidence=["e"],
        created_at="2026-10-09T00:00:00+00:00",
        created_by=CEP_ENGINE_ACTOR,
        requires_approval=True,
        status="pending",
    )
    bridge = CepResponseBridge(gate)
    bridge.fire(_match())

    touched = {name.split(".")[0] for name, _, _ in gate.mock_calls}
    assert touched == {"create_action"}
    gate.create_action.assert_called_once()


def test_duplicate_match_inside_ttl_window_produces_no_second_call() -> None:
    bridge, approvals = _bridge()
    first = bridge.fire(_match())
    second = bridge.fire(_match())  # same match id, inside the TTL

    assert first is not None
    assert second is None
    assert len(approvals.calls) == 1


def test_dedupe_expires_after_ttl() -> None:
    now = [1000.0]

    def clock() -> float:
        return now[0]

    bridge, approvals = _bridge(dedupe_ttl_s=10.0, clock=clock)
    assert bridge.fire(_match()) is not None

    now[0] += 11.0  # past the TTL: the same match id may propose again
    assert bridge.fire(_match()) is not None
    assert len(approvals.calls) == 2


def test_evidence_renders_the_sequence() -> None:
    evidence = render_match_evidence(_match())

    assert evidence == [
        "cep.rule=ransomware-staging-2src",
        "cep.entity_key=host=WKS-1",
        "cep.sequence_started=1970-01-01T00:16:40+00:00",
        "cep.sequence_completed=1970-01-01T00:17:40+00:00",
        "cep.finding[0]=cs-1",
        "cep.finding[1]=spl-1",
        "cep.sources=crowdstrike,splunk",
        "cep.confidence=0.92",
        "cep.window_bucket=1",
        "cep.graph_path=finding:cs-1 -> host:WKS-1",
    ]
    bridge, approvals = _bridge()
    bridge.fire(_match())
    assert approvals.calls[0]["evidence"] == evidence


def test_match_without_graph_path_omits_the_line() -> None:
    evidence = render_match_evidence(_match(graph_path=None))
    assert not any(line.startswith("cep.graph_path=") for line in evidence)

    bridge, approvals = _bridge()
    bridge.fire(_match(graph_path=None))
    assert approvals.calls[0]["parameters"]["graph_path"] is None


def test_origin_stamp_rides_the_row() -> None:
    bridge, approvals = _bridge()
    bridge.fire(_match())
    params = approvals.calls[0]["parameters"]

    assert params["source"] == CEP_SOURCE
    assert params["rule_id"] == "ransomware-staging-2src"
    assert params["entity_key"] == "host=WKS-1"
    assert params["finding_ids"] == ["cs-1", "spl-1"]
    assert params["data_sources"] == ["crowdstrike", "splunk"]
    assert params["sequence_started_at"] == "1970-01-01T00:16:40+00:00"
    assert params["sequence_completed_at"] == "1970-01-01T00:17:40+00:00"
    assert params["graph_path"] == ["finding:cs-1", "host:WKS-1"]


def test_proposed_action_counter_counts_gate_proposals_only() -> None:
    """Spec AC 8: every proposal that reaches the gate counts once; a
    dedupe-swallowed re-emission is not a proposal and does not count."""
    bridge = CepResponseBridge(RecordingApprovals())
    assert bridge.stats["cep_actions_proposed"] == 0

    assert bridge.fire(_match()) is not None
    assert bridge.fire(_match()) is None  # same match id, inside the TTL

    assert bridge.stats["cep_actions_proposed"] == 1
