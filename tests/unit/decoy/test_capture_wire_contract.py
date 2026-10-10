"""The capture plane's wire contract, pinned in both directions.

Two literals cross the decoy → daemon boundary — the session data_source and
the canary marker — and each side defines its own copy (core cannot import
services, so the capture module owns core-side constants). Static agreement
is how this repo keeps cross-layer literals from drifting (the recall
contract's mechanism): these tests fail the build if either side moves
alone.

The round-trip test is the deeper half: a payload rendered by the real
emitter must parse through the capture's validator unchanged in meaning —
proving the SHAPE agreement, not just the words.
"""

from __future__ import annotations

import pytest

from core.cases.decoy_session_capture import (
    DECOY_SESSION_DATA_SOURCE,
    parse_session_event,
)
from core.response.decoy_rotation import CANARY_MARKER, generate_canary_value
from services.decoy.config import CANARY_MARKER as DECOY_CANARY_MARKER
from services.decoy.session import DATA_SOURCE, DecoySession

pytestmark = pytest.mark.unit


def test_session_data_source_literal_agrees_on_both_sides():
    assert DECOY_SESSION_DATA_SOURCE == DATA_SOURCE == "vigil-decoy"


def test_canary_marker_literal_agrees_on_both_sides():
    assert CANARY_MARKER == DECOY_CANARY_MARKER == "vigil-canary"


def test_a_fresh_session_emits_a_payload_the_capture_validator_accepts():
    session = DecoySession(
        decoy_service="ssh-decoy-01", attacker_ip="203.0.113.7", ttl_seconds=3600
    )
    session.record_auth("root", True, "canary")
    session.record_command("whoami")
    event = parse_session_event(session.build_payload())
    assert event.session_id == session.session_id
    assert event.decoy_service == "ssh-decoy-01"
    assert event.attacker_ip == "203.0.113.7"
    assert event.commands == ["whoami"]


def test_generated_canary_values_are_marked_and_unique():
    first, second = generate_canary_value(), generate_canary_value()
    assert first.startswith(CANARY_MARKER)
    assert second.startswith(CANARY_MARKER)
    assert first != second
