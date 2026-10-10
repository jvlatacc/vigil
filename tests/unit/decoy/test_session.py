"""The session event contract: every payload the decoys emit carries the
spec's JSON contract keys plus the ingest envelope (finding_id, data_source),
and the capture bounds hold under floods (spec criteria 7 — the shape the
daemon's ingest and dedupe rely on)."""

from datetime import datetime, timedelta, timezone

import pytest

from services.decoy.session import (
    CREDENTIAL_CANARY,
    CREDENTIAL_REJECTED,
    DATA_SOURCE,
    DroppedFile,
    DecoySession,
    mitre_from_activity,
)

pytestmark = pytest.mark.unit

# The spec's JSON contract, plus the ingest envelope keys (finding_id and
# data_source) that poller.py requires to attribute and dedupe the event.
CONTRACT_KEYS = {
    "decoy_service",
    "attacker_entity_key",
    "session_start",
    "session_end",
    "routing_action_id",
    "auth_attempts",
    "commands",
    "files_dropped",
    "mitre_techniques",
    "raw",
    "finding_id",
    "data_source",
}


def _session(**kwargs) -> DecoySession:
    kwargs.setdefault("decoy_service", "ssh-decoy")
    kwargs.setdefault("attacker_ip", "203.0.113.7")
    kwargs.setdefault("ttl_seconds", 3600)
    return DecoySession(**kwargs)


def test_payload_carries_exactly_the_contract_keys():
    payload = _session().build_payload()
    assert set(payload.keys()) == CONTRACT_KEYS


def test_entity_key_uses_the_ip_prefix():
    payload = _session().build_payload()
    assert payload["attacker_entity_key"] == "ip:203.0.113.7"


def test_finding_id_is_stable_and_session_scoped():
    session = _session()
    first = session.build_payload()
    second = session.build_payload()
    assert first["finding_id"] == second["finding_id"]
    assert first["finding_id"].startswith("decoy-")
    # Distinct sessions dedupe apart — one finding per decoy session.
    assert _session().build_payload()["finding_id"] != first["finding_id"]


def test_data_source_marks_decoy_traffic():
    assert _session().build_payload()["data_source"] == DATA_SOURCE == "vigil-decoy"


def test_routing_action_id_defaults_to_none():
    assert _session().build_payload()["routing_action_id"] is None


def test_routing_action_id_survives_when_set():
    session = _session(routing_action_id="action-20261009-200102-ab12cd")
    assert (
        session.build_payload()["routing_action_id"]
        == "action-20261009-200102-ab12cd"
    )


def test_canary_auth_attempt_shape():
    session = _session()
    session.record_auth(user="root", success=True, credential=CREDENTIAL_CANARY)
    payload = session.build_payload()
    assert payload["auth_attempts"] == [
        {"user": "root", "result": "success", "credential": "canary"}
    ]


def test_rejected_auth_attempt_shape():
    session = _session()
    session.record_auth(user="admin", success=False, credential=CREDENTIAL_REJECTED)
    (attempt,) = session.build_payload()["auth_attempts"]
    assert attempt == {
        "user": "admin",
        "result": "failure",
        "credential": "rejected",
    }


def test_dropped_file_shape_is_marked_simulated():
    session = _session()
    session.record_file(
        DroppedFile(name="x.sh", sha256="ab" * 32, source="simulated-download")
    )
    assert session.build_payload()["files_dropped"] == [
        {
            "name": "x.sh",
            "sha256": "ab" * 32,
            "source": "simulated-download",
            "simulated": True,
        }
    ]


def test_command_flood_is_bounded():
    session = _session()
    for i in range(6000):
        session.record_command(f"cmd-{i}")
    payload = session.build_payload()
    assert len(payload["commands"]) == 5000
    assert payload["commands"][0] == "cmd-0"


def test_file_flood_is_bounded():
    session = _session()
    for i in range(1200):
        session.record_file(DroppedFile(name=f"f{i}", sha256="ab" * 32, source="t"))
    assert len(session.build_payload()["files_dropped"]) == 1000


def test_recording_never_raises_on_odd_input():
    session = _session()
    session.record_auth(user="", success=False, credential=CREDENTIAL_REJECTED)
    session.record_command("")
    session.record_command("  whitespace  ")
    # Capture is the point — none of the above may raise, and evidence is
    # stored verbatim: the decoy never mangles what it captured.
    payload = session.build_payload()
    assert payload["commands"] == ["", "  whitespace  "]


def test_session_expires_at_ttl():
    started = datetime.now(timezone.utc) - timedelta(seconds=3601)
    assert _session(started=started).expired() is True


def test_session_not_expired_while_fresh():
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert _session(started=started).expired() is False


def test_activity_pushes_the_idle_expiry_back():
    # A long-lived session whose last activity was recent stays open even
    # past the idle window; an abandoned one expires instead of holding
    # its capture forever.
    started = datetime.now(timezone.utc) - timedelta(seconds=301)
    session = _session(started=started)
    session.touch()
    assert session.expired() is False


def test_idle_session_expires():
    started = datetime.now(timezone.utc) - timedelta(seconds=301)
    session = _session(started=started)
    session.last_activity = started  # no activity since open
    assert session.expired() is True


def test_mitre_valid_account_on_canary_success():
    attempts = [type("A", (), {"result": "success"})()]
    assert "T1078" in mitre_from_activity(attempts, [])


def test_mitre_password_guessing_after_repeated_failures():
    attempts = [type("A", (), {"result": "failure"})() for _ in range(3)]
    assert "T1110.001" in mitre_from_activity(attempts, [])


def test_mitre_shell_and_discovery_from_commands():
    techniques = mitre_from_activity([], ["whoami", "cat /etc/passwd", "ip a", "ls"])
    assert "T1059.004" in techniques  # Unix Shell
    assert "T1033" in techniques  # whoami
    assert "T1087" in techniques  # Account Discovery (cat /etc/passwd)
    assert "T1016" in techniques  # Network config
    assert "T1083" in techniques  # File discovery


def test_mitre_mapping_is_deterministic():
    commands = ["whoami", "uname -a", "netstat -an"]
    assert mitre_from_activity([], commands) == mitre_from_activity([], commands)


def test_iso_timestamps_are_utc_zulu():
    payload = _session(
        started=datetime(2026, 10, 9, 20, 31, 2, tzinfo=timezone.utc)
    ).build_payload(ended=datetime(2026, 10, 9, 20, 44, 51, tzinfo=timezone.utc))
    assert payload["session_start"] == "2026-10-09T20:31:02Z"
    assert payload["session_end"] == "2026-10-09T20:44:51Z"
