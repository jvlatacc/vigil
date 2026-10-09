"""The daemon processor's decoy-session branch.

Two wiring decisions are the whole test here. First, a decoy session event
takes the atomic capture pipeline, not the generic ingestion store — its
Finding, transcript, and IOCs must land as one transaction, which the
generic store cannot give it. Second, once captured, the finding stops
before response evaluation, exactly like the known-answer probe (#923): the
response bands exist to protect production, and acting on a decoy finding —
containing the attacker the deception is holding open — is the tip-off this
feature exists to avoid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from core.cases.decoy_session_capture import DECOY_SESSION_DATA_SOURCE
from services.daemon.config import ProcessingConfig
from services.daemon.processor import FindingProcessor
from services.decoy.session import DecoySession, DroppedFile

pytestmark = pytest.mark.unit


def _session_payload() -> Dict[str, Any]:
    session = DecoySession(
        decoy_service="ssh-decoy-01",
        attacker_ip="203.0.113.7",
        ttl_seconds=3600,
        routing_action_id="action-20261009-200102-ab12cd",
        started=datetime(2026, 10, 9, 20, 31, 2),
    )
    session.record_auth("root", True, "canary")
    session.record_command("whoami")
    session.record_file(
        DroppedFile(
            name="x.sh",
            sha256="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            source="simulated-download",
        )
    )
    return session.build_payload(ended=datetime(2026, 10, 9, 20, 44, 51))


def _processor() -> FindingProcessor:
    return FindingProcessor(
        ProcessingConfig(
            auto_triage_enabled=False,
            auto_enrich_enabled=False,
            max_concurrent_tasks=1,
        )
    )


@pytest.mark.asyncio
async def test_decoy_session_takes_the_capture_pipeline_not_the_generic_store(
    monkeypatch,
):
    payload = _session_payload()
    processor = _processor()

    captured_events: list = []
    import core.cases.decoy_session_capture as capture

    def _record(event):
        captured_events.append(event)
        return {
            "status": "created",
            "finding_id": event.session_id,
            "case_id": "case-decoy-intel",
            "iocs_added": 2,
        }

    monkeypatch.setattr(capture, "capture_session_event", _record)
    processor._store_with_retry = AsyncMock(return_value=True)
    # The background enrich task is this test's business only as wiring —
    # not spawned, so the test observes exactly the store branch.
    processor._spawn_enrich = AsyncMock()

    assert await processor._process_finding(payload) is None
    assert len(captured_events) == 1
    assert captured_events[0].session_id == payload["finding_id"]
    # The generic store must never see a decoy payload.
    processor._store_with_retry.assert_not_awaited()
    assert processor.stats["decoy_sessions_captured"] == 1


@pytest.mark.asyncio
async def test_a_replayed_session_is_a_handled_event_not_a_store_failure(monkeypatch):
    payload = _session_payload()
    processor = _processor()

    import core.cases.decoy_session_capture as capture

    monkeypatch.setattr(
        capture,
        "capture_session_event",
        lambda event: {"status": "duplicate", "finding_id": event.session_id},
    )

    assert await processor._store_decoy_session(payload) is True


@pytest.mark.asyncio
async def test_a_malformed_decoy_payload_is_refused_before_any_write(monkeypatch):
    payload = _session_payload()
    payload["attacker_entity_key"] = "host:fyodor-l"
    processor = _processor()

    import core.cases.decoy_session_capture as capture

    monkeypatch.setattr(
        capture,
        "capture_session_event",
        lambda event: pytest.fail("capture must not run on a malformed event"),
    )

    assert await processor._store_decoy_session(payload) is False


@pytest.mark.asyncio
async def test_a_failed_capture_is_a_store_failure_not_a_silent_loss(monkeypatch):
    payload = _session_payload()
    processor = _processor()

    import core.cases.decoy_session_capture as capture

    def _boom(event):
        raise RuntimeError("database down")

    monkeypatch.setattr(capture, "capture_session_event", _boom)

    assert await processor._store_decoy_session(payload) is False


@pytest.mark.asyncio
async def test_a_captured_decoy_finding_stops_before_response_evaluation():
    payload = _session_payload()
    payload["data_source"] = DECOY_SESSION_DATA_SOURCE
    processor = _processor()
    processor._evaluate_for_response = AsyncMock()

    await processor._enrich_in_background(payload)

    # The deception invariant: nothing past the capture may act on the
    # finding — no response queue, no orchestrator intake, no fastpath.
    processor._evaluate_for_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_generic_finding_still_reaches_response_evaluation():
    payload = _session_payload()
    payload["data_source"] = "vendor-x"  # not a decoy finding
    processor = _processor()
    processor._evaluate_for_response = AsyncMock()

    await processor._enrich_in_background(payload)

    processor._evaluate_for_response.assert_awaited_once()
