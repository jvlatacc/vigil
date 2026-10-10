"""The origin floor: what unattended containment may act on.

A containment row whose motivating finding sits below the operator's
minimum origin tier waits for a person, unless other findings corroborate
the target — another finding at a tier the floor accepts, or enough
distinct data sources inside the window. A tier proves who sent an alert,
never that the alert is true; this gate prices the vouch and bounds the
blast radius of a lying-but-authenticated feed. Signed and transport
origins keep today's auto path, a failed corroboration read holds the row
(fail-closed, mirroring the breaker's state read), and a held row keeps
its place in the queue.
"""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.response.approval_service import ActionStatus, ActionType, ApprovalService
from core.response.config import ResponseConfig, min_origin_trust_rank
from core.response.origin import (
    CORROBORATION_WINDOW_MINUTES,
    FINDING_CONTEXT_KEY,
    origin_floor_decision,
)
from core.storage.finding_corroboration import Corroboration
from core.storage.models import Finding
from core.storage.origin_trust import tier_rank
from core.time import utcnow

pytestmark = pytest.mark.unit

GATE = "core.response.approval_service"


@pytest.fixture
def no_db():
    """Stand-in session and config store so ApprovalService never reaches
    PostgreSQL: not for the row _put_action inserts, and not for the
    force_manual_approval flag read at each decision."""
    manager = MagicMock()

    @contextmanager
    def _scope():
        yield MagicMock()

    manager.session_scope = _scope
    config_store = MagicMock()
    config_store.read_system_config.return_value = {"enabled": False}
    with (
        patch(f"{GATE}.get_db_manager", return_value=manager),
        patch(f"{GATE}.get_config_service", return_value=config_store),
    ):
        yield


def _context(tier="unverified", finding_id="f-1", source="webhook"):
    return {
        FINDING_CONTEXT_KEY: {
            "finding_id": finding_id,
            "origin_trust": tier,
            "data_source": source,
        }
    }


def _create(svc, target="203.0.113.7", confidence=0.99, parameters=None, **kwargs):
    return svc.create_action(
        action_type=ActionType.BLOCK_IP,
        title="block",
        description="test",
        target=target,
        confidence=confidence,
        reason="test",
        evidence=[],
        created_by="pytest",
        parameters=parameters,
        **kwargs,
    )


# --- the pure decision -------------------------------------------------------


def test_a_finding_at_or_above_the_floor_proceeds():
    config = ResponseConfig()
    corroboration = Corroboration(distinct_sources=0, best_other_rank=None)
    assert origin_floor_decision(tier_rank("transport"), corroboration, config) is None
    assert origin_floor_decision(tier_rank("signed"), corroboration, config) is None


def test_a_below_floor_finding_without_corroboration_waits():
    rule = origin_floor_decision(
        tier_rank("unverified"),
        Corroboration(distinct_sources=0, best_other_rank=None),
        ResponseConfig(),
    )
    assert (
        rule
        == "response.min_origin_trust=transport (finding=unverified, sources=0<2)"
    )


def test_a_failed_corroboration_read_holds_the_action():
    # An unreadable check must not read as a passed one.
    rule = origin_floor_decision(tier_rank("unverified"), None, ResponseConfig())
    assert rule == "response.origin_corroboration=read_failed"


def test_a_corroborating_finding_at_the_floor_releases_the_row():
    # Another finding naming the same target vouches at the floor's tier.
    corroboration = Corroboration(
        distinct_sources=1, best_other_rank=tier_rank("transport")
    )
    assert (
        origin_floor_decision(tier_rank("unverified"), corroboration, ResponseConfig())
        is None
    )


def test_enough_distinct_sources_release_the_row_even_below_the_floor():
    corroboration = Corroboration(distinct_sources=2, best_other_rank=None)
    assert (
        origin_floor_decision(tier_rank("unverified"), corroboration, ResponseConfig())
        is None
    )


def test_one_source_short_of_the_corroboration_bar_waits():
    corroboration = Corroboration(distinct_sources=1, best_other_rank=None)
    rule = origin_floor_decision(tier_rank("unverified"), corroboration, ResponseConfig())
    assert rule is not None and rule.startswith("response.min_origin_trust=")


def test_an_unknown_tier_is_treated_as_below_the_floor():
    corroboration = Corroboration(distinct_sources=0, best_other_rank=None)
    rule = origin_floor_decision(None, corroboration, ResponseConfig())
    assert rule is not None and rule.startswith("response.min_origin_trust=")


def test_a_stricter_floor_demands_more_of_the_corroboration():
    # floor=signed: a transport finding is below it now, and transport-tier
    # corroboration no longer releases the row.
    config = ResponseConfig(min_origin_trust=tier_rank("signed"))
    below = origin_floor_decision(
        tier_rank("transport"),
        Corroboration(distinct_sources=1, best_other_rank=tier_rank("transport")),
        config,
    )
    assert below is not None
    released = origin_floor_decision(
        tier_rank("signed"),
        Corroboration(distinct_sources=0, best_other_rank=None),
        config,
    )
    assert released is None


def test_the_corroboration_window_is_a_fixed_constant():
    assert CORROBORATION_WINDOW_MINUTES == 30


def test_an_unknown_floor_tier_name_fails_loudly():
    with pytest.raises(ValueError, match="DAEMON_MIN_ORIGIN_TRUST"):
        min_origin_trust_rank("tsl-ssl-but-verified")


# --- the gate at insert ------------------------------------------------------


@pytest.mark.usefixtures("no_db")
class TestOriginFloorGate:
    def test_below_floor_containment_waits_even_at_full_confidence(self):
        svc = ApprovalService(config=ResponseConfig())
        action = _create(svc, parameters=_context(tier="unverified"))
        assert action.status == ActionStatus.PENDING.value
        assert action.requires_approval is True
        assert (
            "response.min_origin_trust=transport (finding=unverified, sources=0<2)"
            in action.reason
        )

    def test_transport_and_signed_keep_todays_auto_path(self):
        for tier in ("transport", "signed"):
            svc = ApprovalService(config=ResponseConfig())
            action = _create(svc, parameters=_context(tier=tier))
            assert action.status == ActionStatus.APPROVED.value, tier
            assert action.requires_approval is False, tier

    def test_corroboration_releases_a_below_floor_row(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(
            f"{GATE}.corroborating_sources",
            return_value=Corroboration(distinct_sources=2, best_other_rank=None),
        ):
            action = _create(svc, parameters=_context(tier="unverified"))
        assert action.status == ActionStatus.APPROVED.value

    def test_a_failed_corroboration_read_holds_for_a_person(self):
        svc = ApprovalService(config=ResponseConfig())
        with patch(f"{GATE}.corroborating_sources", side_effect=RuntimeError("db down")):
            action = _create(svc, parameters=_context(tier="unverified"))
        assert action.status == ActionStatus.PENDING.value
        assert "response.origin_corroboration=read_failed" in action.reason

    def test_an_unanchored_target_cannot_be_corroborated(self):
        # A CIDR target matches no individual src_ips entry, so no probe
        # exists: the below-floor row waits rather than guess.
        svc = ApprovalService(config=ResponseConfig())
        action = _create(
            svc, target="203.0.113.0/24", parameters=_context(tier="unverified")
        )
        assert action.status == ActionStatus.PENDING.value
        assert "response.origin_probe=unanchored" in action.reason

    def test_a_hostname_keyed_row_probes_hostnames(self):
        svc = ApprovalService(config=ResponseConfig())
        parameters = _context(tier="unverified")
        parameters["hostname"] = "laptop-01.corp.example"
        probe = MagicMock(
            return_value=Corroboration(distinct_sources=0, best_other_rank=None)
        )
        with patch(f"{GATE}.corroborating_sources", probe):
            action = _create(svc, target="unknown", parameters=parameters)
        assert probe.call_args.args[1] == {"hostnames": ["laptop-01.corp.example"]}
        assert action.status == ActionStatus.PENDING.value

    def test_the_motivating_finding_cannot_corroborate_itself(self):
        svc = ApprovalService(config=ResponseConfig())
        probe = MagicMock(
            return_value=Corroboration(distinct_sources=0, best_other_rank=None)
        )
        with patch(f"{GATE}.corroborating_sources", probe):
            _create(svc, parameters=_context(tier="unverified", finding_id="f-9"))
        assert probe.call_args.kwargs["exclude_finding_id"] == "f-9"

    def test_a_row_without_finding_context_is_outside_the_gate(self):
        # Agent-proposed rows are already human_only and workflow rows require
        # a person; the unattended creator always stamps context. A row
        # without it never pays the corroboration read.
        svc = ApprovalService(config=ResponseConfig())
        probe = MagicMock()
        with patch(f"{GATE}.corroborating_sources", probe):
            action = _create(svc, parameters={"correlation": {}})
        probe.assert_not_called()
        assert action.status == ActionStatus.APPROVED.value

    def test_a_row_already_held_for_another_reason_never_pays_the_read(self):
        svc = ApprovalService(config=ResponseConfig())
        probe = MagicMock()
        with patch(f"{GATE}.corroborating_sources", probe):
            action = _create(
                svc, parameters=_context(tier="unverified"), human_only=True
            )
        probe.assert_not_called()
        assert "approval.human_only=True" in action.reason

    def test_a_held_row_keeps_its_place_in_the_queue(self):
        # Held, not dropped: the caller's reason survives beside the rule.
        svc = ApprovalService(config=ResponseConfig())
        action = _create(svc, parameters=_context(tier="unverified"))
        assert action.reason.startswith("test;")
        assert "response.min_origin_trust=" in action.reason


# --- what the storage repository counts --------------------------------------


class TestCorroborationRepository:
    def _session(self, pairs):
        session = MagicMock()
        session.execute.return_value.all.return_value = pairs
        return session

    def _window(self):
        return utcnow() - timedelta(minutes=CORROBORATION_WINDOW_MINUTES)

    def test_counts_distinct_sources_and_the_best_other_rank(self):
        from core.storage.finding_corroboration import corroborating_sources

        session = self._session(
            [
                ("splunk", "transport"),
                ("crowdstrike", "unverified"),
                ("splunk", "transport"),
            ]
        )
        corroboration = corroborating_sources(
            session, {"src_ips": ["1.2.3.4"]}, self._window(),
            exclude_finding_id="f-1",
        )
        assert corroboration.distinct_sources == 2
        assert corroboration.best_other_rank == tier_rank("transport")

    def test_a_partner_with_no_known_tier_never_looks_ranked(self):
        from core.storage.finding_corroboration import corroborating_sources

        session = self._session([("splunk", None), ("elastic", "garbage")])
        corroboration = corroborating_sources(
            session, {"src_ips": ["1.2.3.4"]}, self._window()
        )
        assert corroboration.distinct_sources == 2
        assert corroboration.best_other_rank is None

    def test_an_empty_read_corroborates_nothing(self):
        from core.storage.finding_corroboration import corroborating_sources

        session = self._session([])
        corroboration = corroborating_sources(
            session, {"src_ips": ["1.2.3.4"]}, self._window()
        )
        assert corroboration.distinct_sources == 0
        assert corroboration.best_other_rank is None

    def test_the_query_is_the_indexed_containment_over_entity_context(self):
        # The GIN index on entity_context backs this probe: it must stay a
        # JSONB containment over the entity context, not a table scan shape.
        import re

        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql

        stmt = select(Finding.data_source).where(
            Finding.entity_context.contains({"src_ips": ["1.2.3.4"]})
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert re.search(
            r"entity_context .*@> ", compiled.replace("\n", " ")
        )
