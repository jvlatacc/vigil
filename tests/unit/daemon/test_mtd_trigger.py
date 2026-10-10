"""The daemon's MTD trigger matrix: when a probe is honey-routed, and when not.

Mirrors the no-DB patch pattern of tests/unit/response: the approval
service runs its real row logic against a fake session, so the reuse and
honest-exit rules are tested without PostgreSQL.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.response.approval_service import ApprovalService
from core.response.config import MtdConfig
from services.daemon.config import EscalationConfig, ResponseConfig
from services.daemon.responder import AutonomousResponder

pytestmark = pytest.mark.unit


class _RowQuery:
    """Serves one configured row for a registry/exclusion lookup."""

    def __init__(self, row):
        self.row = row

    def filter(self, *criteria):
        return self

    def order_by(self, *criteria):
        return self

    def first(self):
        return self.row


class _ScalarResult:
    """Serves ``scalar_one_or_none`` for the keyed-approval select."""

    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _FakeSession:
    """Answers the reads the MTD path makes.

    ``query(entity)`` serves the exclusion and decoy lookups;
    ``execute(select(...))`` serves the approval service's dedupe, backed
    by the rows added during the test — the reuse a real database gives
    the second probe of one attacker, without PostgreSQL.
    """

    def __init__(self, exclusion=None, decoy=None):
        self.exclusion = exclusion
        self.decoy = decoy
        self.added = []

    def query(self, entity):
        name = entity.__name__
        if name == "MtdIpExclusion":
            return _RowQuery(self.exclusion)
        return _RowQuery(self.decoy)

    def execute(self, statement):
        return _ScalarResult(self.added[-1] if self.added else None)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        return None

    def refresh(self, row):
        return None


class _FakeManager:
    def __init__(self, session):
        self._session = session

    @contextmanager
    def session_scope(self):
        yield self._session


@contextmanager
def _no_db(exclusion=None, decoy=None):
    """Patches every DB seam the MTD path touches with one fake session."""
    session = _FakeSession(exclusion=exclusion, decoy=decoy)
    manager = _FakeManager(session)
    config_store = Mock()
    config_store.read_system_config.return_value = {"enabled": False}
    with (
        patch("services.daemon.responder.get_db_manager", return_value=manager),
        patch("core.response.approval_service.get_db_manager", return_value=manager),
        patch(
            "core.response.approval_service.get_config_service",
            return_value=config_store,
        ),
    ):
        yield session


def _decoy(kind="ssh"):
    endpoint = "10.0.0.42:2222" if kind == "ssh" else "10.0.0.42:8080"
    return SimpleNamespace(decoy_id=f"decoy-{kind}-01", kind=kind, endpoint=endpoint)


def _probe_finding(**overrides):
    """A scanning probe against an internal host, triaged to monitor."""
    finding = {
        "finding_id": "f-mtd-1",
        "severity": "low",
        "recommended_action": "monitor",
        "triage_confidence": 0.90,
        "mitre_predictions": {"T1046": "Network Service Scanning"},
        "entity_context": {
            "src_ips": ["203.0.113.7"],
            "dest_ips": ["10.0.0.42"],
        },
    }
    finding.update(overrides)
    return finding


def _responder(mtd_config=None, response_config=None):
    return AutonomousResponder(
        response_config or ResponseConfig(),
        EscalationConfig(),
        response_service=Mock(),
        approvals=ApprovalService(config=ResponseConfig()),
        mtd_config=mtd_config or MtdConfig(enabled=True),
    )


class TestTheTriggerMatrix:
    """A probe at or above the floor is routed exactly once; every refusal
    is honest and writes nothing."""

    @pytest.mark.asyncio
    async def test_a_probe_at_the_floor_is_routed_once_per_attacker(self):
        """Two probes of one attacker share the idempotent row."""
        with _no_db(decoy=_decoy()) as session:
            responder = _responder()
            await responder._evaluate_response(_probe_finding())
            await responder._evaluate_response(_probe_finding(finding_id="f-mtd-2"))
            assert len(session.added) == 1
            row = session.added[0]
            assert row.idempotency_key == "honey_route:203.0.113.7"
            assert responder.stats["honey_routed"] == 2

    @pytest.mark.asyncio
    async def test_the_proposal_carries_the_audit_contract(self):
        with _no_db(decoy=_decoy()) as session:
            responder = _responder()
            await responder._evaluate_response(_probe_finding())
            row = session.added[0]
            assert row.created_by == "auto_responder"
            assert row.reversibility == "reversible"
            assert row.status == "approved"
            assert row.action_type == "honey_route"
            assert row.reason.startswith("mtd.confidence_floor")
            assert row.parameters["decoy_id"] == "decoy-ssh-01"
            assert row.parameters["finding_id"] == "f-mtd-1"
            assert row.parameters["session_ttl_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_below_the_auto_line_the_row_waits_for_a_person(self):
        with _no_db(decoy=_decoy()) as session:
            responder = _responder()
            await responder._evaluate_response(_probe_finding(triage_confidence=0.85))
            assert len(session.added) == 1
            assert session.added[0].status == "pending"
            assert responder.stats["pending_approval"] == 1

    @pytest.mark.asyncio
    async def test_a_disabled_band_reads_nothing_and_creates_nothing(self):
        """Default-off: no row, and not even a registry or exclusion read."""
        db = Mock()
        with patch("services.daemon.responder.get_db_manager", return_value=db):
            responder = _responder(mtd_config=MtdConfig())
            await responder._evaluate_response(_probe_finding())
            db.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_excluded_destination_is_never_routed(self):
        exclusion = SimpleNamespace(ip="10.0.0.42", status="active")
        with _no_db(exclusion=exclusion, decoy=_decoy()) as session:
            responder = _responder()
            with patch.object(responder._approval_service, "create_action") as create:
                await responder._evaluate_response(_probe_finding())
                create.assert_not_called()
            assert session.added == []

    @pytest.mark.asyncio
    async def test_no_active_decoy_creates_nothing(self):
        with _no_db(decoy=None) as session:
            responder = _responder()
            await responder._evaluate_response(_probe_finding())
            assert session.added == []

    @pytest.mark.asyncio
    async def test_a_probe_with_no_usable_attacker_address_creates_nothing(self):
        finding = _probe_finding(
            entity_context={"src_ips": ["127.0.0.1"], "dest_ips": ["10.0.0.42"]}
        )
        with _no_db(decoy=_decoy()) as session:
            responder = _responder()
            await responder._evaluate_response(finding)
            assert session.added == []

    @pytest.mark.asyncio
    async def test_dry_run_logs_and_writes_nothing(self, caplog):
        with _no_db(decoy=_decoy()) as session:
            responder = _responder(response_config=ResponseConfig(dry_run=True))
            with caplog.at_level("INFO", logger="services.daemon.responder"):
                await responder._evaluate_response(_probe_finding())
            assert session.added == []
            assert "[DRY RUN] Would create honey_route" in caplog.text

    @pytest.mark.asyncio
    async def test_every_refusal_records_its_rule(self, caplog):
        with _no_db(decoy=None) as session:
            responder = _responder()
            with caplog.at_level("INFO", logger="services.daemon.responder"):
                await responder._evaluate_response(_probe_finding())
            assert "mtd.no_decoy_available" in caplog.text
