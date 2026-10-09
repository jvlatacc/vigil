"""The autonomy envelope's runtime semantics: allowlist, reversibility, budget."""

from __future__ import annotations

from datetime import timedelta

from core.edge.envelope import (
    REVERSIBLE_ACTION_TYPES,
    HourlyBudget,
    action_allowed,
    budget_for,
)
from core.edge.policy import AutonomyEnvelope

from .helpers import NOW

ENVELOPE = AutonomyEnvelope(
    allowed_actions=("block_ip",),
    max_actions_per_hour=5,
    max_action_ttl_minutes=30,
    require_reversible=True,
    confidence_floor=0.90,
    allow_slm_decisions=False,
)


class TestHourlyBudget:
    def test_take_consumes_the_limit(self):
        budget = HourlyBudget(limit=3)
        taken = [budget.take(NOW) for _ in range(4)]
        assert taken == [True, True, True, False]
        assert budget.taken == 3

    def test_budget_resets_at_the_hour_boundary(self):
        budget = HourlyBudget(limit=1)
        late = NOW.replace(minute=59, second=59)
        next_hour = NOW + timedelta(hours=1)
        assert budget.take(late) is True
        # The new clock hour starts a fresh count — no carry-over.
        assert budget.take(next_hour) is True
        assert budget.take(next_hour + timedelta(seconds=1)) is False

    def test_zero_limit_allows_nothing(self):
        # The schema documents max_actions_per_hour=0 as an envelope that
        # allows nothing; the budget must make that literal.
        budget = HourlyBudget(limit=0)
        assert budget.take(NOW) is False
        assert budget.taken == 0


class TestEnvelopeSemantics:
    def test_action_allowed_reads_the_signed_allowlist(self):
        assert action_allowed(ENVELOPE, "block_ip") is True
        assert action_allowed(ENVELOPE, "process_kill") is False

    def test_unknown_action_type_is_not_known_reversible(self):
        # The set is closed: block_ip's nftables add/delete is reversible by
        # construction; anything else must fail the require_reversible gate
        # until an executor gives it a reversible story.
        assert "block_ip" in REVERSIBLE_ACTION_TYPES
        assert "process_kill" not in REVERSIBLE_ACTION_TYPES

    def test_budget_for_derives_the_signed_cap(self):
        assert budget_for(ENVELOPE).limit == ENVELOPE.max_actions_per_hour
