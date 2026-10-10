"""The deceive verb: triage can speak it, and the prompt offers it."""

import pytest

from services.daemon.config import ProcessingConfig
from services.daemon.probes import ACTIONS
from services.daemon.processor import FindingProcessor

pytestmark = pytest.mark.unit


def _apply(reply: str) -> dict:
    processor = FindingProcessor(ProcessingConfig())
    return processor._apply_triage_result({"finding_id": "f-1"}, reply)


def _prompt() -> str:
    return FindingProcessor(ProcessingConfig())._build_triage_prompt(
        {"title": "t", "description": "d"}
    )


def test_deceive_is_a_listening_word():
    finding = _apply("CONFIDENCE: 0.70\nRECOMMENDED_ACTION: deceive")
    assert finding["recommended_action"] == "deceive"


def test_the_prompt_offers_every_word_in_the_vocabulary():
    """The prompt is generated from ACTIONS, not a second list that can drift."""
    prompt = _prompt()
    for word in ACTIONS:
        assert word in prompt


def test_a_word_outside_the_vocabulary_is_still_ignored():
    finding = _apply("CONFIDENCE: 0.9\nRECOMMENDED_ACTION: wipe_everything")
    assert "recommended_action" not in finding


def test_the_recommendation_ladder_names_deceiving_for_recon():
    """A recon-tagged probe below the review line reads as DECEIVE, with the
    containment bands keeping precedence — asserted in test_recon_correlation."""
    assert "deceive" in ACTIONS
