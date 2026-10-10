"""The decoy capture plane's pure decisions (spec plane 04, criterion 7).

What a session event may become, before any database is involved: the wire
contract's parse (a malformed event is refused, never coerced — a session
captured wrong is worse than a session refused), the ATT&CK mapping through
the shared vocabulary, and the IOC/key extraction the intel pipeline joins
on. The writer itself is proven against a real PostgreSQL in
tests/integration/test_decoy_session_capture.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytest

from core.cases.decoy_session_capture import (
    DecoySessionEvent,
    _description_for,
    _severity_for,
    entity_keys_for_iocs,
    iocs_from_event,
    mitre_names_from_techniques,
    mitre_predictions_from_techniques,
    parse_session_event,
)
from services.decoy.session import DecoySession, DroppedFile

pytestmark = pytest.mark.unit


def _emitted_session(
    *,
    with_canary_success: bool = True,
    with_dropped_file: bool = True,
    routing_action_id: str | None = "action-20261009-200102-ab12cd",
) -> Dict[str, Any]:
    """A payload rendered by the real emitter — the wire shape by
    construction, not by hand-copying it."""
    session = DecoySession(
        decoy_service="ssh-decoy-01",
        attacker_ip="203.0.113.7",
        ttl_seconds=3600,
        routing_action_id=routing_action_id,
        started=datetime(2026, 10, 9, 20, 31, 2),
    )
    session.record_auth("root", with_canary_success, "canary")
    session.record_command("whoami")
    session.record_command("cat /etc/passwd")
    if with_dropped_file:
        session.record_file(
            DroppedFile(
                name="x.sh",
                sha256="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                source="simulated-download",
            )
        )
    return session.build_payload(ended=datetime(2026, 10, 9, 20, 44, 51))


# ---------------------------------------------------------------------------
# parse_session_event — the wire contract, validated
# ---------------------------------------------------------------------------


def test_emitter_payload_parses_into_the_event():
    event = parse_session_event(_emitted_session())
    assert event.session_id.startswith("decoy-")
    assert event.decoy_service == "ssh-decoy-01"
    assert event.attacker_ip == "203.0.113.7"
    assert event.attacker_entity_key == "ip:203.0.113.7"
    assert event.session_start == datetime(2026, 10, 9, 20, 31, 2)
    assert event.session_end == datetime(2026, 10, 9, 20, 44, 51)
    assert event.auth_successes == 1
    assert event.commands == ["whoami", "cat /etc/passwd"]


def test_canary_success_is_counted_so_severity_can_mean_the_attacker_is_in():
    assert parse_session_event(_emitted_session()).auth_successes == 1
    assert (
        parse_session_event(_emitted_session(with_canary_success=False)).auth_successes
        == 0
    )


def test_wrong_data_source_is_refused_not_coerced():
    payload = _emitted_session()
    payload["data_source"] = "webhook"
    with pytest.raises(ValueError, match="data_source"):
        parse_session_event(payload)


def test_missing_or_non_ip_attacker_key_is_refused():
    payload = _emitted_session()
    payload["attacker_entity_key"] = "host:fyodor-l"
    with pytest.raises(ValueError, match="attacker_entity_key"):
        parse_session_event(payload)
    payload["attacker_entity_key"] = "ip:not-an-address"
    with pytest.raises(ValueError, match="unparseable"):
        parse_session_event(payload)


def test_malformed_timestamp_is_refused():
    payload = _emitted_session()
    payload["session_start"] = "yesterday, maybe"
    with pytest.raises(ValueError, match="session_start"):
        parse_session_event(payload)


def test_session_id_longer_than_the_finding_id_column_is_refused():
    payload = _emitted_session()
    payload["finding_id"] = "decoy-" + "a" * 50
    with pytest.raises(ValueError, match="finding_id column"):
        parse_session_event(payload)


def test_malformed_lists_are_refused_instead_of_partially_read():
    for field, junk in (
        ("commands", ["ok", 42]),
        ("auth_attempts", ["not-a-dict"]),
        ("files_dropped", ["not-a-dict"]),
        ("mitre_techniques", [1, 2]),
        ("raw", "not-a-dict"),
    ):
        payload = _emitted_session()
        payload[field] = junk
        with pytest.raises(ValueError, match=field):
            parse_session_event(payload)


def test_optional_absent_fields_default_to_empty_not_none():
    payload = _emitted_session(with_dropped_file=False)
    payload["routing_action_id"] = None
    payload["auth_attempts"] = None
    payload["commands"] = None
    payload["mitre_techniques"] = None
    payload["raw"] = None
    event = parse_session_event(payload)
    assert event.auth_attempts == []
    assert event.commands == []
    assert event.files_dropped == []
    assert event.mitre_techniques == []
    assert event.raw == {}
    assert event.routing_action_id is None


def test_timezone_aware_stamp_is_normalized_to_naive_utc():
    payload = _emitted_session()
    payload["session_end"] = "2026-10-09T20:44:51+00:00"
    event = parse_session_event(payload)
    assert event.session_end.tzinfo is None
    assert event.session_end == datetime(2026, 10, 9, 20, 44, 51)


def test_parsed_event_is_frozen():
    event = parse_session_event(_emitted_session())
    with pytest.raises(Exception):
        event.session_id = "decoy-forged"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MITRE mapping — through the shared vocabulary, not a decoy-local table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "techniques,expected",
    [
        (["T1110.001"], {"T1110.001": 1.0}),
        (["t1110.001"], {"T1110.001": 1.0}),  # emitter tags are canonical;
        # a lowercase variant still maps to the same prediction
        ([" T1110.001 "], {"T1110.001": 1.0}),
        (["T1110.001", "T1110.001"], {"T1110.001": 1.0}),  # dedupe
        (["T1078"], {"T1078": 1.0}),
        (["T1059.004"], {"T1059.004": 1.0}),
        ([], {}),
    ],
)
def test_session_techniques_map_to_predictions(techniques, expected):
    assert mitre_predictions_from_techniques(techniques) == expected


@pytest.mark.parametrize(
    "junk", ["not-a-tech", "T12", "G1234", "S1234", "T12345", "", "T1110.00"]
)
def test_technique_tags_that_are_not_canonical_ids_are_dropped(junk):
    assert mitre_predictions_from_techniques([junk]) == {}


def test_observed_confidence_is_present_not_scored():
    # The decoy observes activity; it does not score it. The prediction
    # carries presence (the webhook's own convention), never a fabricated
    # model confidence.
    predictions = mitre_predictions_from_techniques(["T1110.001"])
    assert predictions == {"T1110.001": 1.0}


def test_mapped_techniques_resolve_names_through_the_shared_vocabulary():
    names = mitre_names_from_techniques(["T1110.001", "T1078", "T1016"])
    assert names["T1110.001"] == "Password Guessing"
    assert names["T1078"] == "Valid Accounts"
    assert names["T1016"] == "System Network Configuration Discovery"


# ---------------------------------------------------------------------------
# IOCs and entity keys — the shapes the intel pipeline joins on
# ---------------------------------------------------------------------------


def test_iocs_are_the_attacker_ip_and_each_dropped_hash():
    event = parse_session_event(_emitted_session())
    iocs = iocs_from_event(event)
    assert ("ip", "203.0.113.7") in iocs
    assert (
        "hash",
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    ) in iocs


def test_dropped_file_without_a_sha256_contributes_no_ioc():
    session = DecoySession(
        decoy_service="http-decoy-01",
        attacker_ip="203.0.113.9",
        ttl_seconds=3600,
        started=datetime(2026, 10, 9, 20, 0, 0),
    )
    payload = session.build_payload()
    # A drop the decoy could not hash: the file name is evidence, the
    # absent hash contributes no IOC.
    payload["files_dropped"] = [{"name": "probe.txt"}]
    iocs = iocs_from_event(parse_session_event(payload))
    assert len([pair for pair in iocs if pair[0] == "hash"]) == 0


def test_iocs_are_deduped_in_first_seen_order():
    event = parse_session_event(_emitted_session())
    event.files_dropped.extend(
        [
            {
                "name": "again.sh",
                "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            }
        ]
    )
    hashes = [value for ioc_type, value in iocs_from_event(event) if ioc_type == "hash"]
    assert (
        hashes.count("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
        == 1
    )


def test_entity_keys_are_minted_by_the_one_rule():
    keys = entity_keys_for_iocs(
        iocs_from_event(parse_session_event(_emitted_session()))
    )
    assert "ip:203.0.113.7" in keys
    assert any(key.startswith("hash:") for key in keys)


# ---------------------------------------------------------------------------
# The finding's display shape — counts, never transcript content
# ---------------------------------------------------------------------------


def _event_with(
    *, successes: int = 0, failures: int = 0, commands: List[str] | None = None
) -> DecoySessionEvent:
    session = DecoySession(
        decoy_service="ssh-decoy-01",
        attacker_ip="203.0.113.7",
        ttl_seconds=3600,
        started=datetime(2026, 10, 9, 20, 31, 2),
    )
    for _ in range(successes):
        session.record_auth("root", True, "canary")
    for _ in range(failures):
        session.record_auth("admin", False, "rejected")
    for command in commands or []:
        session.record_command(command)
    return parse_session_event(
        session.build_payload(ended=datetime(2026, 10, 9, 20, 44, 51))
    )


def test_a_canary_success_is_high_severity_and_a_failure_only_session_is_medium():
    # A canary success means the attacker believes they are in — the one
    # severity distinction a decoy session can honestly make.
    assert _severity_for(parse_session_event(_emitted_session())) == "high"
    assert (
        _severity_for(parse_session_event(_emitted_session(with_canary_success=False)))
        == "medium"
    )
    assert _severity_for(_event_with(successes=1)) == "high"
    assert _severity_for(_event_with(failures=3)) == "medium"


def test_description_carries_counts_only_no_transcript_content():
    event = _event_with(successes=1, failures=1, commands=["cat /etc/shadow"])
    description = _description_for(event)
    assert "2 auth attempts" in description
    assert "1 commands" in description
    assert "/etc/shadow" not in description
    # "canary" is the auth attempt's credential marker — transcript content
    # that must stay in the JSONB payload, never reach the description.
    assert "canary" not in description
