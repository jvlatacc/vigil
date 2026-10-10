"""The execution re-check: the gate runs again before anything dispatches.

Creation and execution are different transactions (#944, D1). A row no
person decided is re-judged by the guard chain in
``execute_approved_actions`` — invariant, breaker, hard quota ceiling —
and a held verdict is refused and durably recorded, never executed and
never dropped silently. A row a person decided proceeds whatever the
chain answers: the breaker suspends machine response, and a person's
decision is not machine response — the deliberate emergency valve.

The invariant's read seam is pointed at rules without a database, the
way ``test_guards_protected_assets`` does it; the breaker and quota are
stubbed where their state must be scripted and left real where the
in-memory fallback is the honest subject.
"""

import pytest

from core.response import protected_assets
from core.response.approval_service import PendingAction
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.breaker import CLOSED, OPEN, BreakerStatus
from core.response.config import decision_rule
from core.response.guards import GuardChain
from core.response.guards_config import GuardConfig, GuardConfigError
from core.response.protected_assets import ProtectedAssetIndex, ProtectedRule
from core.response.quotas import QuotaState

pytestmark = pytest.mark.unit

DNS = ProtectedRule.validated(
    match_kind="ip",
    match_value="10.0.0.53",
    asset_class="dns",
    label="prod-dns-1",
)


@pytest.fixture(autouse=True)
def cold_cache():
    """Every test starts and ends with an empty protected-asset cache."""
    protected_assets.invalidate_cache()
    yield
    protected_assets.invalidate_cache()


def _index(monkeypatch, *rules):
    """Point the cache's read seam at rules without a database."""
    monkeypatch.setattr(
        protected_assets, "_read_active_rules", lambda *a, **k: tuple(rules)
    )


class _ScriptedBreaker:
    """The breaker protocol the chain consumes, with scripted state."""

    def __init__(self, state=CLOSED, seconds_left=900):
        self.state = state
        self.seconds_left = seconds_left
        self.invariant_notes = 0
        self.origin_notes = 0
        self.quota_trips = []

    async def status(self):
        return BreakerStatus(state=self.state, seconds_left=self.seconds_left)

    async def note_invariant_block(self):
        self.invariant_notes += 1
        return None

    async def note_origin_unverified(self):
        self.origin_notes += 1
        return None

    async def trip_on_quota(self, signal):
        self.quota_trips.append(signal)


class _ScriptedQuota:
    def __init__(self, state=QuotaState.OK):
        self.state = state
        self.rule = {
            QuotaState.OK: decision_rule("response.quota_ok", True),
            QuotaState.SOFT_EXCEEDED: decision_rule(
                "response.quota_soft_exceeded", "global per-minute 30/30"
            ),
            QuotaState.HARD_EXCEEDED: decision_rule(
                "response.quota_hard_ceiling", "global per-hour 200/200"
            ),
        }[state]
        self.breaker_trip_reason = (
            "quota hard ceiling: global per-hour 200/200"
            if state is QuotaState.HARD_EXCEEDED
            else None
        )
        self.checked = []

    async def check_only(self, action_type, ip, config):
        self.checked.append((action_type, ip))
        return self


def _chain(*, breaker=None, quota=None, config=GuardConfig()) -> GuardChain:
    """A real chain with scripted stores, injected into the service.

    Injection is by instance (``service._guards``), not by patching module
    globals: the lazy ``_guard_chain()`` honors an existing attribute, so
    the test is order-independent however the shared singleton was built.
    """
    return GuardChain(
        config=config,
        breaker=breaker or _ScriptedBreaker(),
        quota=quota or _ScriptedQuota(),
    )


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


def _row(action_id, *, requires_approval, approved_by, target="10.0.0.53"):
    return PendingAction(
        action_id=action_id,
        action_type="waf_block",
        title="t",
        description="d",
        target=target,
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


def _service(rows, chain=None):
    service = AutonomousResponseService.__new__(AutonomousResponseService)
    service.approval_service = _RecordingService(rows)
    service._execute_cloudflare_action = lambda **_: {"success": True}
    if chain is not None:
        service._guards = chain
    return service


def _dns_rule() -> str:
    hit = ProtectedAssetIndex((DNS,)).match("10.0.0.53", None)
    assert hit is not None
    return hit.rule()


class TestExecutionRecheck:
    def test_a_planted_auto_approved_row_on_a_protected_asset_is_refused_and_recorded(
        self, monkeypatch
    ):
        _index(monkeypatch, DNS)
        planted = _row("planted", requires_approval=False, approved_by=None)
        person = _row("person", requires_approval=True, approved_by="alice")
        service = _service([planted, person], chain=_chain())

        results = service.execute_approved_actions()

        assert [r["action_id"] for r in results] == ["person"]
        assert service.approval_service.executed == ["person"]
        assert service.approval_service.refused == [("planted", _dns_rule())]

    def test_fail_closed_refuses_and_records_every_person_less_row(self, monkeypatch):
        def _down(*a, **k):
            raise RuntimeError("database unreachable")

        monkeypatch.setattr(protected_assets, "_read_active_rules", _down)
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=_chain())

        results = service.execute_approved_actions()

        assert results == []
        assert len(service.approval_service.refused) == 1
        assert "response.protected_asset" in service.approval_service.refused[0][1]

    def test_an_open_breaker_refuses_and_records_the_person_less_row(self, monkeypatch):
        _index(monkeypatch)
        chain = _chain(breaker=_ScriptedBreaker(state=OPEN, seconds_left=741))
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=chain)

        results = service.execute_approved_actions()

        assert results == []
        assert service.approval_service.executed == []
        (refused,) = service.approval_service.refused
        assert refused[0] == "auto"
        assert "response.breaker_open" in refused[1]

    def test_a_person_approved_row_executes_while_the_breaker_is_open(
        self, monkeypatch
    ):
        # The emergency valve beats the breaker: the breaker suspends
        # machine response, and a person's decision is not machine response.
        _index(monkeypatch)
        chain = _chain(breaker=_ScriptedBreaker(state=OPEN, seconds_left=741))
        person = _row("person", requires_approval=True, approved_by="alice")
        service = _service([person], chain=chain)

        results = service.execute_approved_actions()

        assert [r["action_id"] for r in results] == ["person"]
        assert service.approval_service.refused == []

    def test_a_hard_ceiling_refuses_the_person_less_row_at_execution(self, monkeypatch):
        # The window went over the hard ceiling between release and
        # execution (D3): the re-check refuses the person-less row without
        # spending a slot, and records the ceiling — not a silent skip.
        _index(monkeypatch)
        chain = _chain(quota=_ScriptedQuota(QuotaState.HARD_EXCEEDED))
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=chain)

        results = service.execute_approved_actions()

        assert results == []
        (refused,) = service.approval_service.refused
        assert "response.quota_hard_ceiling" in refused[1]

    def test_a_soft_window_manufactures_no_refusal(self, monkeypatch):
        # Soft-exceeded is for would-be decisions; only the hard ceiling
        # refuses at execution. A soft window neither executes the row nor
        # records a refusal — the person-decided gate answers as before.
        _index(monkeypatch)
        quota = _ScriptedQuota(QuotaState.SOFT_EXCEEDED)
        chain = _chain(quota=quota)
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=chain)

        results = service.execute_approved_actions()

        assert results == []
        assert service.approval_service.refused == []
        assert quota.checked  # judged read-only, never spent

    def test_an_unbuildable_guard_config_refuses_and_records(self, monkeypatch):
        def _raise():
            raise GuardConfigError("response.subnet_scope_prefix=0: expected 1-32")

        monkeypatch.setattr(GuardConfig, "from_settings", _raise)
        _index(monkeypatch)
        # config=None makes the chain build from settings — which the patch
        # refuses, so this chain is born unavailable, deterministically.
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=GuardChain())

        results = service.execute_approved_actions()

        assert results == []
        (refused,) = service.approval_service.refused
        assert "response.guards_config" in refused[1]

    def test_a_clean_person_less_row_is_still_skipped_for_a_persons_decision(
        self, monkeypatch
    ):
        # No protection, breaker CLOSED, quota under every limit: the
        # re-check holds nothing and records nothing — the row still waits
        # for the person-decided gate, exactly as before the guards (#944):
        # a confidence figure released it, and whoever supplied that figure
        # also chose the outcome.
        _index(monkeypatch)
        auto = _row("auto", requires_approval=False, approved_by=None)
        service = _service([auto], chain=_chain())

        results = service.execute_approved_actions()

        assert results == []
        assert service.approval_service.executed == []
        assert service.approval_service.refused == []
