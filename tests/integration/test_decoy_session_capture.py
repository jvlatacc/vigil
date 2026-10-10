"""The decoy capture plane against a real PostgreSQL (spec criterion 7).

One decoy session event becomes exactly one Finding (``data_source
="vigil-decoy"``, ``external_id`` = session id, ATT&CK prediction rows), one
``CaseEvidence`` transcript whose ``analysis_results`` carries the whole
session, and ``CaseIOC`` rows (attacker IP + dropped-file hashes,
``source="decoy"``) — written atomically or not at all. A replayed event is
a duplicate, never a second write; a capture that dies halfway leaves no
half-written evidence. The credential invariant is asserted where it
matters: attacker-typed content lives in evidence/IOC JSONB, never in the
finding's indexed columns.

Payloads come from the real emitter (``DecoySession.build_payload``) — the
wire shape by construction.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.storage.connection
from core.cases.decoy_session_capture import (
    DECOY_INTEL_CASE_ID,
    DECOY_SESSION_DATA_SOURCE,
    capture_session_event,
    parse_session_event,
)
from core.storage.models import (
    Case,
    CaseEvidence,
    CaseIOC,
    Finding,
    FindingMitrePrediction,
    MtdDecoyRegistry,
    case_findings,
)
from services.decoy.session import DecoySession, DroppedFile

pytestmark = [pytest.mark.integration, pytest.mark.database]

SCRATCH_DB = "vigil_test_decoy_capture"

# These fixtures CREATE and DROP a database. Only ever against a loopback
# host — a developer whose POSTGRES_HOST points at a shared or staging
# server must get a skip, not a dropped database.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "0.0.0.0"}
_CONNECT_ARGS = {"connect_timeout": 5}


def _host() -> str:
    return os.getenv("POSTGRES_HOST", "localhost")


def _url(database: str) -> str:
    user = os.getenv("POSTGRES_USER", "deeptempo")
    password = os.getenv("POSTGRES_PASSWORD", "deeptempo_secure_password_change_me")
    return (
        f"postgresql+psycopg2://{user}:{password}@"
        f"{_host()}:{os.getenv('POSTGRES_PORT', '5432')}/{database}"
    )


def _admin_engine():
    return create_engine(
        _url("postgres"), isolation_level="AUTOCOMMIT", connect_args=_CONNECT_ARGS
    )


# The tables the capture touches, in dependency order (Postgres resolves FK
# targets at DDL time).
_TABLES = [
    Case.__table__,
    Finding.__table__,
    case_findings,
    FindingMitrePrediction.__table__,
    CaseEvidence.__table__,
    CaseIOC.__table__,
    MtdDecoyRegistry.__table__,
]


@pytest.fixture
def capture_db():
    reason = None
    if _host() not in _LOCAL_HOSTS:
        reason = f"refusing to CREATE/DROP a database on non-local host {_host()!r}"
    else:
        try:
            with _admin_engine().connect():
                pass
        except Exception as e:  # noqa: BLE001
            reason = f"requires a local PostgreSQL (docker compose up -d postgres): {e}"
    if reason:
        pytest.skip(reason)

    admin = _admin_engine()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    scratch = create_engine(_url(SCRATCH_DB), connect_args=_CONNECT_ARGS)
    with scratch.connect() as c:
        # The Finding model's GIN index needs pg_trgm — the repo's own init
        # creates it the same way (infra/database/init/01_init_schema.sql).
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        c.commit()
    for table in _TABLES:
        table.create(scratch)

    yield scratch

    scratch.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
    admin.dispose()


def _emitted_payload(
    *, attacker_ip: str = "203.0.113.7", with_canary_success: bool = True
) -> Dict[str, Any]:
    session = DecoySession(
        decoy_service="ssh-decoy-01",
        attacker_ip=attacker_ip,
        ttl_seconds=3600,
        routing_action_id="action-20261009-200102-ab12cd",
        started=datetime(2026, 10, 9, 20, 31, 2),
    )
    session.record_auth("root", with_canary_success, "canary")
    session.record_auth("admin", False, "rejected")
    session.record_command("whoami")
    session.record_command("cat /etc/passwd")
    session.record_file(
        DroppedFile(
            name="x.sh",
            sha256="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            source="simulated-download",
        )
    )
    return session.build_payload(ended=datetime(2026, 10, 9, 20, 44, 51))


def test_session_event_becomes_finding_evidence_and_iocs_in_one_write(
    capture_db,
):
    payload = _emitted_payload()
    event = parse_session_event(payload)

    with Session(capture_db) as s:
        result = capture_session_event(event, session=s)
        s.commit()

    assert result["status"] == "created"

    with Session(capture_db) as s:
        finding = s.get(Finding, event.session_id)
        assert finding is not None, "one Finding per session"
        assert finding.data_source == DECOY_SESSION_DATA_SOURCE
        assert finding.external_id == event.session_id
        assert finding.title == "Decoy session on ssh-decoy-01"
        assert finding.severity == "high"  # a canary success: the attacker is in
        assert finding.anomaly_score is None  # nothing scored this session
        assert finding.entity_context["src_ip"] == "203.0.113.7"
        assert finding.entity_context["decoy_service"] == "ssh-decoy-01"
        assert "ip:203.0.113.7" in finding.entity_context["entity_keys"]

        predictions = {
            p.technique_id: p.confidence for p in finding.mitre_prediction_rows
        }
        # whoami → system-owner discovery; cat /etc/passwd → account
        # discovery; a canary success → valid accounts.
        assert predictions["T1033"] == 1.0
        assert predictions["T1087"] == 1.0
        assert predictions["T1078"] == 1.0

        # The transcript lives in the evidence's analysis_results, exactly
        # once, round-tripped through the JSONB.
        evidence_rows = (
            s.query(CaseEvidence).filter_by(case_id=DECOY_INTEL_CASE_ID).all()
        )
        assert len(evidence_rows) == 1
        transcript = evidence_rows[0].analysis_results
        assert transcript["commands"] == ["whoami", "cat /etc/passwd"]
        assert len(transcript["auth_attempts"]) == 2
        assert transcript["mitre_techniques"] == [
            "T1078",
            "T1059.004",
            "T1033",
            "T1087",
        ]
        assert transcript["mitre_names"]["T1033"] == "System Owner/User Discovery"
        assert evidence_rows[0].evidence_type == "decoy_session"
        assert evidence_rows[0].source == DECOY_SESSION_DATA_SOURCE

        iocs = {
            (row.ioc_type, row.value): row
            for row in s.query(CaseIOC).filter_by(case_id=DECOY_INTEL_CASE_ID).all()
        }
        assert ("ip", "203.0.113.7") in iocs
        assert (
            "hash",
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        ) in iocs
        for row in iocs.values():
            assert row.source == "decoy"
            assert row.enrichment_data["entity_key"].startswith(("ip:", "hash:"))
            assert row.enrichment_data["decoy_sessions"] == [event.session_id]
        assert iocs[("ip", "203.0.113.7")].threat_level == "high"

        # The standing case links the finding and unions the techniques.
        case = s.get(Case, DECOY_INTEL_CASE_ID)
        assert case is not None
        assert [f.finding_id for f in case.findings] == [event.session_id]
        for technique in ("T1033", "T1078", "T1087"):
            assert technique in case.mitre_techniques


def test_replayed_event_is_a_duplicate_and_writes_nothing_twice(capture_db):
    payload = _emitted_payload()
    event = parse_session_event(payload)

    with Session(capture_db) as s:
        first = capture_session_event(event, session=s)
        s.commit()
    with Session(capture_db) as s:
        second = capture_session_event(event, session=s)
        s.commit()

    assert first["status"] == "created"
    assert second["status"] == "duplicate"

    with Session(capture_db) as s:
        assert s.query(Finding).count() == 1
        assert s.query(CaseEvidence).count() == 1
        assert s.query(CaseIOC).count() == 2
        assert (
            s.query(FindingMitrePrediction)
            .filter_by(finding_id=event.session_id)
            .count()
            == 4
        )


def test_the_unique_pair_itself_refuses_a_second_write(capture_db):
    # The replay dedupe leans on the (data_source, external_id) unique
    # constraint — the pair, not the pre-check, is the guarantee that holds
    # when two workers race. Prove the schema's own rule.
    payload = _emitted_payload()
    event = parse_session_event(payload)

    with Session(capture_db) as s:
        capture_session_event(event, session=s)
        s.commit()
        impostor = Finding(
            finding_id="decoy-different-id",
            external_id=event.session_id,
            data_source=DECOY_SESSION_DATA_SOURCE,
            title="same (data_source, external_id), different row",
        )
        s.add(impostor)
        with pytest.raises(IntegrityError):
            s.commit()


def test_partial_failure_leaves_no_half_writes(capture_db, monkeypatch):
    payload = _emitted_payload()
    event = parse_session_event(payload)

    import core.cases.decoy_session_capture as capture

    def _explode(**kwargs):
        raise RuntimeError("IOC store exploded mid-capture")

    monkeypatch.setattr(capture, "_ensure_ioc", _explode)

    with pytest.raises(RuntimeError, match="exploded"):
        with Session(capture_db) as s:
            capture_session_event(event, session=s)
            s.commit()

    with Session(capture_db) as s:
        # The finding and the transcript it promised must never exist alone:
        # a half-written session reads as evidence it is not.
        assert s.query(Finding).count() == 0
        assert s.query(CaseEvidence).count() == 0
        assert s.query(CaseIOC).count() == 0
        assert s.query(FindingMitrePrediction).count() == 0
        # The standing case itself is rolled back with the rest — it is
        # part of the same transaction, whatever created it.
        assert s.query(Case).count() == 0


def test_a_second_session_from_the_same_attacker_refreshes_iocs_not_duplicates(
    capture_db,
):
    first = parse_session_event(_emitted_payload())
    second = parse_session_event(
        _emitted_payload(with_canary_success=False)
        | {"finding_id": "decoy-ffffff0123456789"}
    )

    with Session(capture_db) as s:
        capture_session_event(first, session=s)
        s.commit()
    with Session(capture_db) as s:
        capture_session_event(second, session=s)
        s.commit()

    with Session(capture_db) as s:
        assert s.query(Finding).count() == 2
        iocs = (
            s.query(CaseIOC)
            .filter_by(ioc_type="ip")
            .filter_by(value="203.0.113.7")
            .all()
        )
        assert len(iocs) == 1, "the attacker IP is one IOC, refreshed per session"
        sessions = iocs[0].enrichment_data["decoy_sessions"]
        assert first.session_id in sessions and second.session_id in sessions
        assert iocs[0].last_seen == second.session_end


def test_attacker_typed_content_stays_in_jsonb_not_in_indexed_columns(
    capture_db,
):
    # The transcript is the payload and belongs in analysis_results. The
    # indexed columns carry the session's shape (counts, ids, addresses) —
    # greppable intel, not transcript content.
    payload = _emitted_payload()
    event = parse_session_event(payload)

    with Session(capture_db) as s:
        capture_session_event(event, session=s)
        s.commit()

    with Session(capture_db) as s:
        finding = s.get(Finding, event.session_id)
        blob = " ".join(
            str(finding.__dict__[column])
            for column in ("title", "description", "source_metadata", "entity_context")
        )
        assert "/etc/passwd" not in blob
        assert "whoami" not in blob


def test_rotation_stamps_rotated_at_on_active_rows(capture_db, monkeypatch):
    with Session(capture_db) as s:
        s.add(
            MtdDecoyRegistry(
                decoy_id="decoy-a",
                name="ssh-decoy-01",
                kind="ssh",
                endpoint="decoy-ssh-01:2222",
                status="active",
                canary_credential_ref="DECOY_CANARY_PASSWORD",
            )
        )
        s.add(
            MtdDecoyRegistry(
                decoy_id="decoy-b",
                name="ssh-decoy-02",
                kind="ssh",
                endpoint="decoy-ssh-02:2222",
                status="retired",
                canary_credential_ref="DECOY_CANARY_PASSWORD",
            )
        )
        s.commit()

    written: list = []

    def _set_secret(ref: str, value: str) -> bool:
        written.append({"ref": ref, "value": value})
        return True

    class _Manager:
        def refresh_if_stale(self):
            pass

        def get_session(self):
            return Session(capture_db)

        @contextmanager
        def session_scope(self):
            s = Session(capture_db)
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()

    import core.response.decoy_rotation as rotation

    monkeypatch.setattr(core.storage.connection, "get_db_manager", lambda: _Manager())
    monkeypatch.setattr(rotation, "set_secret", _set_secret)

    result = rotation.rotate_active_canaries()

    assert result == {"scanned": 1, "rotated": 1, "failed": 0}
    assert len(written) == 1
    assert written[0]["ref"] == "DECOY_CANARY_PASSWORD"
    assert written[0]["value"].startswith("vigil-canary-")

    with Session(capture_db) as s:
        active = s.get(MtdDecoyRegistry, "decoy-a")
        retired = s.get(MtdDecoyRegistry, "decoy-b")
        assert active.rotated_at is not None, "an active decoy's rotation is stamped"
        assert retired.rotated_at is None, "a retired decoy is not rotated"
