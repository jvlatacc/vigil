"""The response queue admits MTD candidates only while MTD is on.

With the feature off (the default install), the queue sees exactly what
it saw before — bit for bit.
"""

import asyncio
from unittest.mock import patch

import pytest

from core.response.config import MtdConfig
from services.daemon.config import ProcessingConfig
from services.daemon.processor import FindingProcessor

pytestmark = pytest.mark.unit


async def _queue_and_evaluate(mtd_config, finding):
    processor = FindingProcessor(ProcessingConfig(), mtd_config=mtd_config)
    response_queue = asyncio.Queue()
    processor.set_response_queue(response_queue)
    with patch("services.daemon.orchestrator.insert_intake_trigger"):
        await processor._evaluate_for_response(finding)
    return response_queue.qsize()


def _recon_probe(**overrides):
    finding = {
        "finding_id": "f-q",
        "severity": "low",
        "recommended_action": "monitor",
        "triage_confidence": 0.5,
        "mitre_predictions": {"T1046": "Network Service Scanning"},
    }
    finding.update(overrides)
    return finding


@pytest.mark.asyncio
async def test_a_deceive_triage_queues_while_mtd_is_on():
    queued = await _queue_and_evaluate(
        MtdConfig(enabled=True), _recon_probe(recommended_action="deceive")
    )
    assert queued == 1


@pytest.mark.asyncio
async def test_a_recon_tagged_probe_queues_while_mtd_is_on():
    queued = await _queue_and_evaluate(MtdConfig(enabled=True), _recon_probe())
    assert queued == 1


@pytest.mark.asyncio
async def test_a_t1595_subtechnique_queues_too():
    queued = await _queue_and_evaluate(
        MtdConfig(enabled=True), _recon_probe(mitre_predictions={"T1595.002": "x"})
    )
    assert queued == 1


@pytest.mark.asyncio
async def test_a_low_confidence_deceive_still_queues():
    """Queueing is candidacy; the decision's confidence_floor refuses later."""
    queued = await _queue_and_evaluate(
        MtdConfig(enabled=True),
        _recon_probe(recommended_action="deceive", triage_confidence=0.3),
    )
    assert queued == 1


@pytest.mark.asyncio
async def test_mtd_candidates_do_not_queue_while_mtd_is_off():
    for finding in (
        _recon_probe(),
        _recon_probe(recommended_action="deceive"),
        _recon_probe(mitre_predictions={"T1595.002": "x"}),
    ):
        assert await _queue_and_evaluate(MtdConfig(), finding) == 0


@pytest.mark.asyncio
async def test_containment_queueing_is_untouched_when_mtd_is_off():
    queued = await _queue_and_evaluate(
        MtdConfig(), _recon_probe(severity="high", mitre_predictions={})
    )
    assert queued == 1


@pytest.mark.asyncio
async def test_the_deceive_candidate_enqueues_the_response_candidate_shape():
    processor = FindingProcessor(ProcessingConfig(), mtd_config=MtdConfig(enabled=True))
    response_queue = asyncio.Queue()
    processor.set_response_queue(response_queue)
    with patch("services.daemon.orchestrator.insert_intake_trigger"):
        await processor._evaluate_for_response(
            _recon_probe(recommended_action="deceive")
        )
    assert response_queue.qsize() == 1
    item = response_queue.get_nowait()
    assert item["type"] == "response_candidate"
    assert item["finding"]["finding_id"] == "f-q"
