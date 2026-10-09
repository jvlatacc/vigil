"""Unit tests for the CEP finding normalizer.

Fixtures mirror the shapes the ingestion adapters actually build
(``core/integrations/crowdstrike/adapter.py``, ``core/integrations/splunk/
adapter.py``); the missing-field tests pin the conservative contract: absent
means absent, never fabricated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from core.cep.normalize import NormalizedFinding, normalize_finding


def _crowdstrike_finding() -> Dict[str, Any]:
    """The dict shape ``_detection_to_finding`` builds."""
    return {
        "finding_id": "cs-abc123",
        "data_source": "crowdstrike",
        "external_id": "abc123",
        "timestamp": "2026-10-09T12:00:00Z",
        "severity": "high",
        "status": "new",
        "title": "Ransomware behavior",
        "description": "Mass file modification",
        "entity_context": {
            "src_ips": ["10.0.0.5"],
            "hostnames": ["WORKSTATION-1"],
            "usernames": ["jdoe"],
            "device_id": "dev-42",
        },
        "raw_event": {},
        "anomaly_score": 0.9,
        "mitre_predictions": {"T1486": 0.9},
    }


def _splunk_finding() -> Dict[str, Any]:
    """The dict shape the Splunk adapter's transform builds."""
    return {
        "finding_id": "splunk-abc",
        "data_source": "splunk",
        "timestamp": "2026-10-09 12:00:00.000",
        "severity": "critical",
        "entity_context": {
            "src_ips": ["203.0.113.7"],
            "dest_ips": ["198.51.100.9"],
            "hostnames": ["DB-01"],
            "usernames": ["svc_backup"],
        },
        "mitre_predictions": {},
    }


def test_crowdstrike_shape_extracts_entities_and_techniques():
    normalized = normalize_finding(_crowdstrike_finding())

    assert normalized.finding_id == "cs-abc123"
    assert normalized.data_source == "crowdstrike"
    assert normalized.severity == "high"
    assert normalized.host == "WORKSTATION-1"
    assert normalized.user == "jdoe"
    assert normalized.src_ip == "10.0.0.5"
    assert normalized.dest_ip is None  # the adapter never set one
    assert normalized.techniques == ("T1486",)
    assert normalized.timestamp == datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def test_splunk_shape_extracts_entities():
    normalized = normalize_finding(_splunk_finding())

    assert normalized.finding_id == "splunk-abc"
    assert normalized.data_source == "splunk"
    assert normalized.severity == "critical"
    assert normalized.host == "DB-01"
    assert normalized.user == "svc_backup"
    assert normalized.src_ip == "203.0.113.7"
    assert normalized.dest_ip == "198.51.100.9"
    assert normalized.techniques == ()
    assert normalized.timestamp == datetime(2026, 10, 9, 12, 0, 0)


def test_missing_fields_stay_absent():
    """The conservative contract: an empty dict normalizes to all-absent."""
    assert normalize_finding({}) == NormalizedFinding()


def test_empty_and_whitespace_strings_stay_absent():
    finding = {
        "finding_id": "   ",
        "data_source": "",
        "severity": None,
        "entity_context": {"hostnames": [""], "src_ips": ["   "]},
    }
    normalized = normalize_finding(finding)

    assert normalized.finding_id is None
    assert normalized.data_source is None
    assert normalized.severity is None
    assert normalized.host is None
    assert normalized.src_ip is None


def test_singular_entity_variants():
    normalized = normalize_finding(
        {
            "entity_context": {
                "src_ip": "10.0.0.1",
                "dst_ip": "10.0.0.2",
                "hostname": "HOST-A",
                "user": "alice",
            }
        }
    )
    assert normalized.src_ip == "10.0.0.1"
    assert normalized.dest_ip == "10.0.0.2"
    assert normalized.host == "HOST-A"
    assert normalized.user == "alice"


def test_users_plural_variant():
    normalized = normalize_finding({"entity_context": {"users": ["bob"]}})
    assert normalized.user == "bob"


def test_first_list_element_wins():
    normalized = normalize_finding(
        {"entity_context": {"hostnames": ["HOST-A", "HOST-B"]}}
    )
    assert normalized.host == "HOST-A"


def test_non_string_scalars_are_skipped_not_coerced():
    normalized = normalize_finding(
        {"entity_context": {"hostnames": [42, "HOST-A"], "src_ips": [1.5]}}
    )
    assert normalized.host == "HOST-A"  # first string is taken
    assert normalized.src_ip is None  # a float is not coerced into an IP


def test_entity_context_non_dict_is_ignored():
    normalized = normalize_finding({"entity_context": ["not", "a", "dict"]})
    assert normalized.host is None
    assert normalized.user is None
    assert normalized.src_ip is None
    assert normalized.dest_ip is None


def test_severity_is_lowercased():
    normalized = normalize_finding({"severity": "HIGH"})
    assert normalized.severity == "high"


def test_techniques_order_preserved_and_deduplicated():
    normalized = normalize_finding(
        {"mitre_predictions": ["T1486", "T1071", "T1486", " T1110 "]}
    )
    assert normalized.techniques == ("T1486", "T1071", "T1110")


def test_techniques_non_string_entries_skipped():
    normalized = normalize_finding({"mitre_predictions": [None, "T1110", 5, {}]})
    assert normalized.techniques == ("T1110",)


def test_techniques_unusual_shapes_treated_as_absent():
    # A bare string is not a canonical shape; the webhook canonicalizer
    # converts it before it lands here, so the normalizer treats it as absent.
    assert normalize_finding({"mitre_predictions": "T1486"}).techniques == ()
    assert normalize_finding({"mitre_predictions": None}).techniques == ()
    assert normalize_finding({"mitre_predictions": 42}).techniques == ()


def test_timestamp_variants():
    aware = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

    # ISO with Z
    assert normalize_finding({"timestamp": "2026-10-09T12:00:00Z"}).timestamp == aware
    # datetime passes through
    assert normalize_finding({"timestamp": aware}).timestamp is aware
    # garbage is absent, never "now"
    assert normalize_finding({"timestamp": "not-a-date"}).timestamp is None
    assert normalize_finding({"timestamp": 12345}).timestamp is None
    assert normalize_finding({}).timestamp is None
