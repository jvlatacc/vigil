"""Decoy telemetry normalizers: one decoy log line -> one Vigil finding payload.

These are the functions the shipper applies to every tailed line before
posting to Vigil's generic ingest webhook (spec AC10). The fixtures mirror
the real formats: cowrie's ``output_jsonlog`` events, OpenCanary's
``CanaryLogger.log`` alerts (logtype integers verified from the 0.9.10
wheel), and http_decoy.py's request events.
"""

import json

import pytest

from services.decoy_farm import telemetry

FARM = "farm-x"
FALLBACK_TS = "2026-10-10T10:00:03+00:00"


def _cowrie_line(record: dict) -> str:
    return json.dumps(record)


class TestFindingId:
    def test_id_is_stable_for_identical_content(self):
        line = _cowrie_line({"eventid": "cowrie.login.failed", "src_ip": "203.0.113.7"})
        first = telemetry.finding_id_for(FARM, "cowrie", line)
        second = telemetry.finding_id_for(FARM, "cowrie", line)
        assert first == second
        assert first.startswith("decoy-cowrie-")

    def test_id_differs_by_kind_and_line(self):
        line = _cowrie_line({"eventid": "cowrie.login.failed", "src_ip": "203.0.113.7"})
        assert telemetry.finding_id_for(
            FARM, "cowrie", line
        ) != telemetry.finding_id_for(FARM, "http-decoy", line)
        assert telemetry.finding_id_for(
            FARM, "cowrie", line
        ) != telemetry.finding_id_for(FARM, "cowrie", line + "\n")


class TestCowrie:
    def test_failed_login_maps_technique_and_entity(self):
        record = {
            "eventid": "cowrie.login.failed",
            "src_ip": "203.0.113.7",
            "username": "root",
            "password": "toor",
            "timestamp": "2026-10-10T10:00:01Z",
            "session": "sess-1",
            "message": "login failed",
        }
        finding = telemetry.cowrie_finding(
            record, farm_id=FARM, raw_line=_cowrie_line(record), fallback_ts=FALLBACK_TS
        )
        assert finding["data_source"] == "decoy-farm"
        assert finding["severity"] == "high"
        assert finding["timestamp"] == "2026-10-10T10:00:01Z"
        assert finding["entity_context"]["src_ip"] == "203.0.113.7"
        assert finding["entity_context"]["decoy"] == "cowrie"
        assert finding["entity_context"]["session"] == "sess-1"
        assert finding["mitre_predictions"] == {"T1021.004": 0.9}
        assert "root" in finding["description"]

    def test_connect_probe_maps_to_recon_technique(self):
        record = {"eventid": "cowrie.session.connect", "src_ip": "203.0.113.7"}
        finding = telemetry.cowrie_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["mitre_predictions"] == {"T1595.001": 0.7}
        assert finding["title"].startswith("Decoy SSH/Telnet:")

    def test_unknown_eventid_is_lenient_with_no_technique(self):
        record = {"eventid": "cowrie.session.closed", "src_ip": "203.0.113.7"}
        finding = telemetry.cowrie_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["mitre_predictions"] == {}
        assert "session closed" in finding["title"]

    def test_missing_source_address_is_described_not_dropped(self):
        record = {"eventid": "cowrie.session.connect"}
        finding = telemetry.cowrie_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert "src_ip" not in finding["entity_context"]
        assert "[no source address in the event]" in finding["description"]
        # The finding still exists: intel value survives even without an IP.
        assert finding["finding_id"].startswith("decoy-cowrie-")


class TestOpenCanary:
    def test_smb_file_open_logtype_5000(self):
        record = {
            "logtype": 5000,
            "src_host": "203.0.113.7",
            "dst_host": "10.0.5.12",
            "dst_port": 445,
            "node_id": "opencanary-node",
            "local_time": "2026-10-10 10:00:00",
            "logdata": {"SHARE": "FAKESHARE", "USER": "nobody"},
        }
        finding = telemetry.opencanary_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["entity_context"]["src_ip"] == "203.0.113.7"
        assert finding["entity_context"]["dst_ip"] == "10.0.5.12"
        assert finding["entity_context"]["dst_port"] == "445"
        assert finding["entity_context"]["logtype"] == 5000
        assert finding["mitre_predictions"] == {"T1021.002": 0.9}
        assert finding["timestamp"] == "2026-10-10 10:00:00"

    def test_unknown_logtype_is_lenient_with_no_technique(self):
        record = {"logtype": 999999, "src_host": "203.0.113.7"}
        finding = telemetry.opencanary_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["mitre_predictions"] == {}
        assert "999999" in finding["title"]

    def test_non_integer_logtype_does_not_raise(self):
        record = {"logtype": None, "src_host": "203.0.113.7"}
        finding = telemetry.opencanary_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["mitre_predictions"] == {}


class TestHttpDecoy:
    def test_probe_maps_to_recon_technique(self):
        record = {
            "method": "GET",
            "path": "/admin",
            "src_ip": "203.0.113.7",
            "user_agent": "curl/8.0",
            "ts": "2026-10-10T10:00:02Z",
        }
        finding = telemetry.http_decoy_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["entity_context"]["src_ip"] == "203.0.113.7"
        assert finding["entity_context"]["path"] == "/admin"
        assert finding["mitre_predictions"] == {"T1595.002": 0.7}

    def test_post_login_maps_to_password_guessing(self):
        record = {
            "method": "POST",
            "path": "/login",
            "src_ip": "203.0.113.7",
            "username": "admin",
            "ts": "2026-10-10T10:00:02Z",
        }
        finding = telemetry.http_decoy_finding(
            record, farm_id=FARM, raw_line="x", fallback_ts=FALLBACK_TS
        )
        assert finding["mitre_predictions"] == {"T1110.001": 0.8}
        assert "admin" in finding["description"]


class TestBuildFinding:
    @pytest.mark.parametrize("raw", ["not json", "null", '"a string"', "[1, 2, 3]", ""])
    def test_unusable_lines_return_none(self, raw):
        assert (
            telemetry.build_finding(
                "cowrie", raw, farm_id=FARM, fallback_ts=FALLBACK_TS
            )
            is None
        )

    def test_unknown_kind_returns_none(self):
        assert (
            telemetry.build_finding(
                "samba-direct", "{}", farm_id=FARM, fallback_ts=FALLBACK_TS
            )
            is None
        )

    def test_roundtrip_cowrie(self):
        record = {
            "eventid": "cowrie.command.input",
            "src_ip": "203.0.113.7",
            "session": "sess-1",
            "message": "uname -a",
            "timestamp": "2026-10-10T10:00:02Z",
        }
        finding = telemetry.build_finding(
            "cowrie", _cowrie_line(record), farm_id=FARM, fallback_ts=FALLBACK_TS
        )
        assert finding is not None
        assert finding["mitre_predictions"] == {"T1059.004": 0.8}
        assert finding["entity_context"]["src_ip"] == "203.0.113.7"

    def test_every_payload_carries_the_ingest_contract_fields(self):
        record = {"eventid": "cowrie.session.connect", "src_ip": "203.0.113.7"}
        finding = telemetry.build_finding(
            "cowrie", _cowrie_line(record), farm_id=FARM, fallback_ts=FALLBACK_TS
        )
        # The daemon webhook requires these to queue the finding cleanly:
        # a stable finding_id, the data_source, and a mitre dict — not a list.
        assert finding["finding_id"]
        assert finding["data_source"] == "decoy-farm"
        assert isinstance(finding["mitre_predictions"], dict)
        assert finding["entity_context"]
