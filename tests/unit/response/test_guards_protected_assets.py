"""The never-quarantine invariant holds whatever the confidence says (#944).

Three layers, mirroring ``test_approval_confidence_gate``:

1. The matching matrix — pure rules, no database: what is protected and
   what is not, including the /24 sibling and longest-prefix cases.
2. Fail-closed — an invariant set that cannot be verified protects
   everything; one that is verified empty protects nothing.
3. The gate end to end — a 0.99-confidence isolate of a DNS asset waits
   for a person with the gate's rationale on the row and lands in the
   human queue; the executor refuses (and durably records) a planted
   person-less row while a person-approved row passes, the deliberate
   emergency valve.

Escalation itself is the responder's severity path (Slack/PagerDuty); what
the gate guarantees is that the row waits for a person, which is what the
human queue surfaces.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest

from core.response import protected_assets
from core.response.approval_service import ActionStatus, ApprovalService
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import ResponseConfig
from core.response.protected_assets import (
    ProtectedAssetIndex,
    ProtectedRule,
    invalidate_cache,
    protected_asset_hit,
)

pytestmark = pytest.mark.unit

DNS = ProtectedRule.validated(
    match_kind="ip",
    match_value="10.0.0.53",
    asset_class="dns",
    label="prod-dns-1",
)
DMZ = ProtectedRule.validated(
    match_kind="cidr",
    match_value="10.0.0.0/24",
    asset_class="gateway",
    label="dmz-edge",
)
CAMPUS = ProtectedRule.validated(
    match_kind="cidr",
    match_value="10.0.0.0/16",
    asset_class="other",
    label="campus",
)
DC = ProtectedRule.validated(
    match_kind="hostname",
    match_value="DC01.corp.example.com",
    asset_class="domain_controller",
    label="primary-dc",
)


@pytest.fixture(autouse=True)
def cold_cache():
    """Every test starts and ends with an empty module cache."""
    invalidate_cache()
    yield
    invalidate_cache()


def _index(monkeypatch, *rules):
    """Point the cache's read seam at rules without a database."""
    monkeypatch.setattr(
        protected_assets, "_read_active_rules", lambda *a, **k: tuple(rules)
    )


# --- 1. The matching matrix -------------------------------------------------


class TestMatchingMatrix:
    def test_a_protected_slash24_matches_its_host_not_the_sibling(self, monkeypatch):
        _index(monkeypatch, DMZ)

        hit = protected_asset_hit("10.0.0.53", None)
        miss = protected_asset_hit("10.0.1.53", None)

        assert hit is not None and hit.match_value == "10.0.0.0/24"
        assert miss is None

    def test_the_most_specific_cidr_wins_on_overlap(self, monkeypatch):
        _index(monkeypatch, CAMPUS, DMZ)

        hit = protected_asset_hit("10.0.0.53", None)

        assert hit is not None and hit.match_value == "10.0.0.0/24"

    def test_an_exact_ip_beats_a_covering_cidr(self, monkeypatch):
        _index(monkeypatch, DMZ, DNS)

        hit = protected_asset_hit("10.0.0.53", None)

        assert hit is not None and hit.match_value == "10.0.0.53"

    def test_hostname_matches_case_insensitively_and_exactly(self, monkeypatch):
        _index(monkeypatch, DC)

        assert protected_asset_hit(None, "dc01.corp.example.com") is not None
        assert protected_asset_hit(None, "DC01.CORP.EXAMPLE.COM") is not None
        # Exact, not suffix: a lookalike host is not the domain controller.
        assert protected_asset_hit(None, "evil-dc01.corp.example.com") is None
        assert protected_asset_hit(None, "dc01.corp.example.com.attacker.io") is None

    def test_a_hostname_rule_does_not_match_an_ip_and_vice_versa(self, monkeypatch):
        _index(monkeypatch, DC, DNS)

        assert protected_asset_hit("10.0.0.53", None) is not None
        assert protected_asset_hit(None, "10.0.0.53") is None
        assert protected_asset_hit(None, "dc01.corp.example.com") is not None

    def test_unknown_or_unroutable_targets_match_nothing(self, monkeypatch):
        _index(monkeypatch, DMZ)

        assert protected_asset_hit("203.0.113.7", None) is None
        assert protected_asset_hit(None, None) is None
        assert protected_asset_hit("not-an-ip", None) is None

    def test_the_rule_renders_the_decision_rule_convention(self):
        hit = ProtectedAssetIndex((DNS,)).match("10.0.0.53", None)
        assert hit is not None
        rule = hit.rule()

        assert "response.protected_asset" in rule
        assert "10.0.0.53" in rule
        assert "asset_class=dns" in rule


# --- canonicalisation refuses what it cannot honour -------------------------


class TestCanonicalisation:
    def test_a_bare_ip_declared_as_cidr_is_a_host_route(self):
        rule = ProtectedRule.validated(
            match_kind="cidr",
            match_value="10.0.0.53",
            asset_class="dns",
            label="x",
        )

        assert rule.match_value == "10.0.0.53/32"

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(
                match_kind="ip", match_value="10.0.0.999", asset_class="dns", label="x"
            ),
            dict(
                match_kind="cidr",
                match_value="10.0.0.0/33",
                asset_class="dns",
                label="x",
            ),
            dict(
                match_kind="cidr",
                match_value="10.0.0.0/-1",
                asset_class="dns",
                label="x",
            ),
            dict(
                match_kind="hostname",
                match_value="*.corp.example.com",
                asset_class="dns",
                label="x",
            ),
            dict(
                match_kind="hostname",
                match_value="DC01/../etc/passwd",
                asset_class="domain_controller",
                label="x",
            ),
            dict(
                match_kind="multicast",
                match_value="10.0.0.53",
                asset_class="dns",
                label="x",
            ),
        ],
    )
    def test_invalid_entries_are_refused(self, kwargs):
        with pytest.raises(ValueError):
            ProtectedRule.validated(**kwargs)


# --- 2. Fail-closed ---------------------------------------------------------


class TestFailClosed:
    def test_an_unverifiable_index_protects_every_target(self, monkeypatch):
        def _down(*a, **k):
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(protected_assets, "_read_active_rules", _down)

        hit = protected_asset_hit("203.0.113.7", None)

        assert hit is not None and hit.fail_closed
        assert "response.protected_asset" in hit.rule()
        assert protected_asset_hit(None, "anything.example.com") is not None

    def test_a_verified_empty_index_protects_nothing(self, monkeypatch):
        _index(monkeypatch)

        assert protected_asset_hit("203.0.113.7", None) is None

    def test_a_stale_cache_still_protects_when_the_database_dies_later(
        self, monkeypatch
    ):
        _index(monkeypatch, DNS)

        def _down(*a, **k):
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(protected_assets, "_read_active_rules", _down)

        # No invalidation: the stale in-memory set is the last known truth.
        assert protected_asset_hit("10.0.0.53", None) is not None


# --- 3. The gate end to end -------------------------------------------------


def _matches(row, stmt) -> bool:
    for clause in stmt._where_criteria:
        if getattr(row, clause.left.key) != clause.right.value:
            return False
    return True


@pytest.fixture
def no_db(monkeypatch):
    """The suite's database stand-in: rows live in a list, not PostgreSQL."""
    stored = []
    session = MagicMock()

    session.add.side_effect = stored.append

    def execute(stmt):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            row for row in stored if _matches(row, stmt)
        ]
        # The idempotency lookup asks for one row; none is stored yet.
        result.scalar_one_or_none.return_value = None
        return result

    session.execute.side_effect = execute
    manager = MagicMock()

    @contextmanager
    def _scope():
        yield session

    manager.session_scope = _scope

    config_store = Mock()
    config_store.read_system_config.return_value = {"enabled": False}
    monkeypatch.setattr(
        "core.response.approval_service.get_db_manager", lambda: manager
    )
    monkeypatch.setattr(
        "core.response.approval_service.get_config_service", lambda: config_store
    )
    return stored


def _service():
    return AutonomousResponseService(
        approvals=ApprovalService(config=ResponseConfig()),
        config=ResponseConfig(),
    )


class TestCreatePathGate:
    def test_a_099_confidence_isolate_of_a_dns_asset_waits_for_a_person(
        self, monkeypatch, no_db
    ):
        _index(monkeypatch, DNS)
        service = _service()

        result = service.create_isolation_action(
            ip_address="10.0.0.53",
            hostname=None,
            confidence=0.99,
            reason="Automated response to finding-1",
            evidence=["finding-1"],
            correlation_data={},
        )

        assert result["status"] == "pending_approval"
        assert result["requires_approval"] is True
        (row,) = no_db
        assert row.requires_approval is True
        assert row.status == ActionStatus.PENDING.value
        assert "response.protected_asset" in row.reason
        assert "10.0.0.53" in row.reason and "dns" in row.reason

        # Escalation substrate: the row the gate forced is exactly what the
        # human approval queue surfaces to a person.
        queue = service.approval_service.list_actions(status=ActionStatus.PENDING)
        assert [a.action_id for a in queue] == [row.action_id]

    def test_the_same_confidence_against_an_unprotected_target_auto_approves(
        self, monkeypatch, no_db
    ):
        _index(monkeypatch, DNS)
        service = _service()

        service.create_isolation_action(
            ip_address="203.0.113.7",
            hostname=None,
            confidence=0.99,
            reason="Automated response to finding-1",
            evidence=["finding-1"],
            correlation_data={},
        )

        (row,) = no_db
        assert row.requires_approval is False
        assert "response.protected_asset" not in row.reason

    def test_the_gate_fires_on_a_hostname_target_too(self, monkeypatch, no_db):
        _index(monkeypatch, DC)
        service = _service()

        service.create_isolation_action(
            ip_address="203.0.113.7",
            hostname="dc01.corp.example.com",
            confidence=0.99,
            reason="Automated response to finding-1",
            evidence=["finding-1"],
            correlation_data={},
        )

        (row,) = no_db
        assert row.requires_approval is True
        assert "response.protected_asset" in row.reason


class TestExecutorRecheck:
    def _service(self, rows):
        service = AutonomousResponseService.__new__(AutonomousResponseService)
        service.approval_service = _RecordingService(rows)
        service._execute_cloudflare_action = lambda **_: {"success": True}
        return service

    def test_a_planted_person_less_row_on_a_protected_asset_is_refused_and_recorded(
        self, monkeypatch
    ):
        _index(monkeypatch, DNS)
        planted = _pending_row("planted", requires_approval=False, approved_by=None)
        person = _pending_row("person", requires_approval=True, approved_by="alice")
        service = self._service([planted, person])

        results = service.execute_approved_actions()

        assert [r["action_id"] for r in results] == ["person"]
        assert service.approval_service.executed == ["person"]
        assert service.approval_service.refused == [("planted", planted_refused_rule())]

    def test_fail_closed_refuses_every_person_less_row(self, monkeypatch):
        def _down(*a, **k):
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(protected_assets, "_read_active_rules", _down)
        auto = _pending_row("auto", requires_approval=False, approved_by=None)
        service = self._service([auto])

        results = service.execute_approved_actions()

        assert results == []
        assert service.approval_service.executed == []
        assert len(service.approval_service.refused) == 1
        assert "response.protected_asset" in service.approval_service.refused[0][1]

    def test_a_person_approved_row_is_the_emergency_valve(self, monkeypatch):
        _index(monkeypatch, DNS)
        person = _pending_row("person", requires_approval=True, approved_by="alice")
        service = self._service([person])

        results = service.execute_approved_actions()

        assert [r["action_id"] for r in results] == ["person"]
        assert service.approval_service.refused == []


class _RecordingService:
    """Executor seams without a database: rows in, records out."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []
        self.refused = []

    def list_actions(self, status=None, **_):
        return self._rows

    def mark_executed(self, action_id, result):
        self.executed.append(action_id)

    def mark_failed(self, action_id, error):
        self.executed.append(action_id)

    def refuse_auto_action(self, action_id, reason):
        self.refused.append((action_id, reason))


def _pending_row(action_id, *, requires_approval, approved_by):
    from core.response.approval_service import PendingAction

    return PendingAction(
        action_id=action_id,
        action_type="waf_block",
        title="t",
        description="d",
        target="10.0.0.53",
        confidence=0.99,
        reason="r",
        evidence=[],
        created_at="",
        created_by="responder",
        requires_approval=requires_approval,
        status="approved",
        approved_by=approved_by,
        parameters={},
    )


def planted_refused_rule():
    hit = ProtectedAssetIndex((DNS,)).match("10.0.0.53", None)
    assert hit is not None
    return hit.rule()
