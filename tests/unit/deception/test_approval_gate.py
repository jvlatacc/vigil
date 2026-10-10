"""AC3 — the honey row's approval gate: its own floor, human override kept.

A transparent, TTL-reversible redirect auto-approves at its dedicated floor
(0.80) where every other reversible action still needs 0.90; below the floor
— or under ``force_manual_approval`` — it waits for an analyst, with the
deciding rule stamped in the reason.
"""

import pytest

from core.response.approval_service import Reversibility
from core.response.config import ResponseConfig, approval_requirement

pytestmark = pytest.mark.unit

REVERSIBLE = Reversibility.REVERSIBLE
IRREVERSIBLE = Reversibility.IRREVERSIBLE


class TestTheHoneyFloor:
    @pytest.mark.parametrize(
        ("confidence", "required"),
        [(0.79, True), (0.80, False), (0.85, False), (0.90, False)],
    )
    def test_honey_route_auto_approves_at_its_own_floor(self, confidence, required):
        got, rule = approval_requirement(
            False, REVERSIBLE, confidence, ResponseConfig(), action_type="honey_route"
        )
        assert got is required
        assert rule.startswith("response.honey_route_floor")

    def test_the_deny_floor_does_not_leak_into_other_actions(self):
        """Same confidence, different action type: the 0.90 line still governs."""
        honey_got, _ = approval_requirement(
            False, REVERSIBLE, 0.85, ResponseConfig(), action_type="honey_route"
        )
        block_got, block_rule = approval_requirement(
            False, REVERSIBLE, 0.85, ResponseConfig(), action_type="block_ip"
        )
        assert honey_got is False
        assert block_got is True
        assert block_rule.startswith("response.confidence_threshold")

    def test_none_action_type_means_the_old_rule(self):
        got, rule = approval_requirement(False, REVERSIBLE, 0.85, ResponseConfig())
        assert got is True
        assert rule.startswith("response.confidence_threshold")


class TestTheManualOverride:
    def test_force_manual_approval_holds_a_honey_row(self):
        got, rule = approval_requirement(
            True, REVERSIBLE, 0.99, ResponseConfig(), action_type="honey_route"
        )
        assert got is True
        assert rule.startswith("approval.force_manual_approval")

    def test_irreversible_holds_regardless_of_action(self):
        got, _ = approval_requirement(
            False, IRREVERSIBLE, 0.99, ResponseConfig(), action_type="honey_route"
        )
        assert got is True

    def test_a_confidence_outside_zero_to_one_holds_a_honey_row(self):
        got, rule = approval_requirement(
            False, REVERSIBLE, 5.0, ResponseConfig(), action_type="honey_route"
        )
        assert got is True
        assert rule.startswith("response.confidence_range")
