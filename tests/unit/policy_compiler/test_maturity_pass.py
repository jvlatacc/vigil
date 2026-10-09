"""The scheduled pass against a real database: compile, dedupe, drift, staleness.

Marked ``external_service`` so CI's DB-backed unit job selects it and the
no-service unit job skips it (tests/pytest.ini markers; the throwaway-database
fixture in tests/unit/conftest.py provisions and drops the schema). Needs the
POSTGRES_* environment of that job — a disposable server, never a dev database.

The seeding here is deliberately operational-shape: rows exactly as the daemon
and case workflow write them, so a test failure reads as "the job misread the
evidence", not "the fixture invented a shape".
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from core.platform import runtime_config
from core.policy_compiler.maturity import (
    LOCK_OBJECT_ID,
    _try_lock,
    run_maturity_pass_sync,
)
from core.storage.models import (
    Case,
    CaseClosureInfo,
    CompiledPolicy,
    CompiledPolicyDecision,
    Finding,
    FindingMitrePrediction,
    WorkflowRun,
)
from core.storage.models.base import case_findings
from core.storage.unit_of_work import unit_of_work
from core.time import utcnow

pytestmark = [pytest.mark.unit, pytest.mark.external_service]

WORKFLOW = "wf_hunt_cred_stuffing"
SOURCE = "okta.system_log"
TECHNIQUE = "T1110.003"
# Distinct prefixes so the per-test purge touches only this module's rows —
# the throwaway database is session-scoped and shared across the process.
RUN_PREFIX = "mj-wfr-"
FINDING_PREFIX = "mj-find-"
CASE_PREFIX = "mj-case-"


@pytest.fixture(autouse=True)
def _clean(throwaway_database):
    """Purge this module's rows before and after each test."""

    def purge() -> None:
        # The runtime-config cache is module-global with a 60s TTL: a test
        # elsewhere that seeded it with a tunable (T2's config tests cache
        # min_runs=25) must not outvote the defaults inside a pass here.
        runtime_config.clear_cache()
        with unit_of_work() as session:
            session.query(CompiledPolicyDecision).delete(synchronize_session=False)
            session.query(CompiledPolicy).delete(synchronize_session=False)
            session.query(WorkflowRun).filter(
                WorkflowRun.run_id.like(f"{RUN_PREFIX}%")
            ).delete(synchronize_session=False)
            session.query(CaseClosureInfo).filter(
                CaseClosureInfo.case_id.like(f"{CASE_PREFIX}%")
            ).delete(synchronize_session=False)
            session.query(Case).filter(Case.case_id.like(f"{CASE_PREFIX}%")).delete(
                synchronize_session=False
            )
            session.query(Finding).filter(
                Finding.finding_id.like(f"{FINDING_PREFIX}%")
            ).delete(synchronize_session=False)

    purge()
    yield
    purge()


def _seed_run(
    session: Session,
    i: int,
    *,
    now,
    source: str = SOURCE,
    technique: str = TECHNIQUE,
    closure_category: str = "resolved",
    retracted: bool = False,
    entity_context: dict | None = None,
    enrichment: dict | None = None,
) -> None:
    """One terminal run + trigger finding + prediction + closed case."""
    fid = f"{FINDING_PREFIX}{i:04d}"
    cid = f"{CASE_PREFIX}{i:04d}"
    closed_at = now - timedelta(days=2)

    session.add(
        WorkflowRun(
            run_id=f"{RUN_PREFIX}{i:04d}",
            workflow_id=WORKFLOW,
            workflow_name="Credential Stuffing Hunt",
            status="completed",
            trigger_context={"finding_id": fid, "run_kind": "hunt"},
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=2),
        )
    )
    session.add(
        Finding(
            finding_id=fid,
            data_source=source,
            title=f"Password spraying from 10.0.0.{i}",
            description="Observed across many accounts",
            timestamp=now - timedelta(days=3),
            severity="high",
            status="new",
            entity_context=(
                entity_context
                if entity_context is not None
                else {"src_ips": ["10.0.0.1"], "usernames": ["svc-backup"]}
            ),
            ai_enrichment=(
                enrichment
                if enrichment is not None
                else {
                    "severity": "high",
                    "category": "credential_stuffing",
                    "recommended_action": "investigate",
                    "triage_reasoning": "consistent pattern",
                }
            ),
        )
    )
    session.add(
        FindingMitrePrediction(finding_id=fid, technique_id=technique, confidence=0.9)
    )
    session.add(Case(case_id=cid, title=f"Case {i}", status="closed"))
    # A Core insert does not autoflush the pending Case row — flush it or the
    # case_findings FK fails.
    session.flush()
    session.execute(insert(case_findings).values(case_id=cid, finding_id=fid))
    session.add(
        CaseClosureInfo(
            case_id=cid,
            closure_category=closure_category if not retracted else "unspecified",
            closed_by="nestor",
            closed_by_kind="analyst",
            closed_at=closed_at,
        )
    )
    if retracted:
        # What reopen_case leaves behind: the category reset, the case open.
        reopened_case = session.get(Case, cid)
        assert reopened_case is not None
        reopened_case.status = "open"
        reopened_case.updated_at = now - timedelta(days=1)


def _seed_archetype(
    session: Session,
    *,
    n: int = 10,
    now=None,
    retracted: set[int] | None = None,
    **kwargs,
) -> None:
    now = now or utcnow()
    retracted = retracted or set()
    for i in range(n):
        _seed_run(session, i, now=now, retracted=i in retracted, **kwargs)


def _policy_rows(session: Session) -> list[CompiledPolicy]:
    return (
        session.execute(select(CompiledPolicy).order_by(CompiledPolicy.version))
        .scalars()
        .all()
    )


# --- Compile -----------------------------------------------------------------


def test_the_pass_compiles_eligible_evidence_into_a_shadowing_policy(
    throwaway_database,
):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["archetypes_eligible"] == 1
    assert report["shadowed"] == 1
    with Session(_engine()) as session:
        rows = _policy_rows(session)
        assert len(rows) == 1
        row = rows[0]
        assert row.state == "shadow"
        assert row.compiled_by == "maturity-job"
        assert row.policy_ir["renders"].keys() == {
            "rego",
            "snort",
            "suricata",
            "iptables",
        }
        assert row.maturity_evidence["outcomes"] == {"resolved": 10}


def test_an_unchanged_archetype_recompiles_to_nothing(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()

    run_maturity_pass_sync(now=now)
    report = run_maturity_pass_sync(now=now)

    assert report["unchanged"] == 1
    assert report["candidates_written"] == 0
    with Session(_engine()) as session:
        assert len(_policy_rows(session)) == 1


def test_a_reopened_case_blocks_compilation(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        # One reopened case among ten resolved: still ineligible.
        _seed_archetype(
            session, n=10, now=now, retracted={9}, closure_category="resolved"
        )
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["archetypes_eligible"] == 0
    with Session(_engine()) as session:
        assert _policy_rows(session) == []


def test_duplicate_closures_do_not_qualify(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now, closure_category="duplicate")
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["archetypes_eligible"] == 0
    with Session(_engine()) as session:
        assert _policy_rows(session) == []


# --- Single-flight ------------------------------------------------------------


def test_the_lock_is_exclusive_across_sessions(throwaway_database):
    engine = _engine()
    with Session(engine) as first, Session(engine) as second:
        assert _try_lock(first)
        assert not _try_lock(second)
        first.rollback()
        assert _try_lock(second)


def test_concurrent_passes_never_double_compile(throwaway_database):
    import threading

    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()

    barrier = threading.Barrier(2)
    reports: list[dict[str, int]] = []

    import concurrent.futures

    def one_pass() -> dict[str, int]:
        barrier.wait()
        return run_maturity_pass_sync(now=now)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: one_pass(), range(2)))

    # Whatever the interleaving — one pass wins the lock, or two ran serially
    # and the second deduped by content hash — the store holds one version.
    with Session(_engine()) as session:
        assert len(_policy_rows(session)) == 1
    skipped = sum(r["lock_skipped"] for r in reports)
    compiled_or_deduped = sum(r["shadowed"] + r["unchanged"] for r in reports)
    assert skipped + compiled_or_deduped == 2


def test_the_lock_object_id_is_a_valid_postgres_key(throwaway_database):
    from sqlalchemy import text

    assert -(2**63) <= LOCK_OBJECT_ID < 2**63
    # Postgres itself accepts the key: the same call the pass makes.
    with _engine().connect() as conn:
        granted = conn.execute(
            text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_OBJECT_ID}
        ).scalar()
        assert granted in (True, False)


# --- Drift and staleness ------------------------------------------------------


def _insert_disagreements(session: Session, row: CompiledPolicy, count: int) -> None:
    for i in range(count):
        session.add(
            CompiledPolicyDecision(
                finding_id=f"{FINDING_PREFIX}{i:04d}",
                policy_id=row.policy_id,
                policy_version=row.version,
                content_hash=row.content_hash,
                mode="shadow",
                outcome="shadow_logged",
                decision={"severity": "high"},
                actual_decision={"severity": "low"},
                agreement_source="llm",
                agrees=False,
                evaluation_us=42,
            )
        )


def test_drift_over_the_limit_suspends(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        _insert_disagreements(session, row, 4)
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["suspended"] == 1
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "suspended"
        assert row.suspended_by == "maturity-job"
        assert row.suspended_at is not None


def test_drift_at_the_limit_does_not_suspend(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        _insert_disagreements(session, row, 3)
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["suspended"] == 0
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "shadow"


def test_an_analyst_reopen_of_a_policy_triaged_closure_is_drift(
    throwaway_database,
):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        # What the console's audited promotion writes (the DB CHECK requires
        # the attribution pair on any active row).
        row.state = "active"
        row.promoted_by = "nestor"
        row.promoted_at = now
        # The policy applied to a seeded finding; three LLM disagreements on
        # top of the reopened case carry the summed counter past the limit of 3.
        _insert_disagreements(session, row, 3)
        session.add(
            CompiledPolicyDecision(
                finding_id=f"{FINDING_PREFIX}0005",
                policy_id=row.policy_id,
                policy_version=row.version,
                content_hash=row.content_hash,
                mode="active",
                outcome="applied",
                decision={"severity": "high"},
                evaluation_us=42,
            )
        )
        reopened = session.get(Case, f"{CASE_PREFIX}0005")
        assert reopened is not None
        reopened.status = "open"
        reopened.updated_at = now
        session.commit()

    report = run_maturity_pass_sync(now=now)

    assert report["suspended"] == 1
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "suspended"


def test_a_policy_nothing_matches_retires(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    # A window that contains none of the evidence: everything aged out.
    report = run_maturity_pass_sync(now=now + timedelta(days=40))

    assert report["retired"] == 1
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "retired"
        assert row.retired_by == "maturity-job"


def test_a_policy_with_a_matching_finding_stays_live(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    report = run_maturity_pass_sync(now=now)

    assert report["retired"] == 0
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "shadow"


def test_staleness_asks_the_evaluator_not_the_timestamps(throwaway_database):
    now = utcnow()
    with Session(_engine()) as session:
        _seed_archetype(session, n=10, now=now)
        session.commit()
    run_maturity_pass_sync(now=now)

    # Thirty-five days on: the compile evidence has aged out of the window,
    # but a fresh finding the policy does NOT match is in it — the scan finds
    # rows, the evaluator rejects each one, and that is what makes it stale.
    later = now + timedelta(days=35)
    with Session(_engine()) as session:
        session.add(
            Finding(
                finding_id=f"{FINDING_PREFIX}fresh",
                data_source=SOURCE,
                title="Password spraying, different shape",
                timestamp=later - timedelta(days=1),
                severity="high",
                status="new",
            )
        )
        session.add(
            FindingMitrePrediction(
                finding_id=f"{FINDING_PREFIX}fresh",
                technique_id="T9999.001",
                confidence=0.9,
            )
        )
        session.commit()

    report = run_maturity_pass_sync(now=later)

    assert report["retired"] == 1
    with Session(_engine()) as session:
        (row,) = _policy_rows(session)
        assert row.state == "retired"


def _engine():
    from core.storage.connection import get_db_manager

    return get_db_manager().engine
