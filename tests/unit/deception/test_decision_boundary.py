"""AC2 — the honey band is additive: its floor moves nothing above it.

The boundary values the task names — 0.79 / 0.80 / 0.90 / 0.91 — decided
exactly what they decided before feature 5 whenever the deception signal is
absent, and the deny-shaped bands keep priority when it is present.
"""

import pytest

from core.response.config import ResponseConfig, response_action_decision

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("severity", "recommended", "confidence", "expected_action"),
    [
        # The reversible auto-approve bar: 0.90.
        ("critical", "isolate", 0.90, "isolate"),
        ("critical", "isolate", 0.91, "isolate"),
        ("high", "block", 0.90, "block"),
        ("high", "block", 0.79, None),
        # The severity-conditioned floors: 0.70 / 0.80.
        ("critical", "investigate", 0.70, "isolate"),
        ("critical", "investigate", 0.69, None),
        ("high", "investigate", 0.80, "investigate"),
        ("high", "investigate", 0.79, None),
        # Below every band.
        ("low", "investigate", 0.70, None),
        ("low", "investigate", 0.85, None),
    ],
)
def test_the_existing_bands_decide_as_before(severity, recommended, confidence, expected_action):
    decided = response_action_decision(severity, confidence, recommended, ResponseConfig())
    if expected_action is None:
        assert decided is None
    else:
        action, _rule = decided
        assert action == expected_action


@pytest.mark.parametrize(
    ("severity", "recommended", "confidence", "expected_action"),
    [
        ("critical", "isolate", 0.90, "isolate"),
        ("critical", "isolate", 0.91, "isolate"),
        ("high", "block", 0.90, "block"),
        ("high", "block", 0.79, None),
        ("critical", "investigate", 0.70, "isolate"),
        ("critical", "investigate", 0.69, None),
        ("high", "investigate", 0.80, "investigate"),
        ("high", "investigate", 0.79, None),
        ("low", "investigate", 0.70, None),
        # (low, investigate, 0.85) steers once a signal is present — that is
        # the additive band working; asserted in TestTheHoneyBand.
    ],
)
def test_the_existing_bands_ignore_the_deception_signal(
    severity, recommended, confidence, expected_action
):
    """Deny bands evaluate FIRST and unchanged, signal present or not."""
    decided = response_action_decision(
        severity, confidence, recommended, ResponseConfig(), deception_signal=True
    )
    if expected_action is None:
        assert decided is None
    else:
        action, _rule = decided
        assert action == expected_action


class TestTheHoneyBand:
    @pytest.mark.parametrize(
        ("confidence", "expected"),
        [(0.79, None), (0.80, "honey_route"), (0.90, "honey_route"), (0.91, "honey_route")],
    )
    def test_the_boundary_values(self, confidence, expected):
        config = ResponseConfig(honey_route_enabled=True)
        decided = response_action_decision(
            "low", confidence, "investigate", config, deception_signal=True
        )
        if expected is None:
            assert decided is None
        else:
            action, rule = decided
            assert action == "honey_route"
            assert rule.startswith("response.honey_route_floor=0.80")
            assert rule.endswith("(%.2f)" % confidence)

    def test_no_signal_means_no_honey_route_at_any_confidence(self):
        config = ResponseConfig(honey_route_enabled=True)
        for confidence in (0.79, 0.80, 0.90, 0.91, 0.99):
            assert (
                response_action_decision(
                    "low", confidence, "investigate", config, deception_signal=False
                )
                is None
            )

    def test_the_posture_disabled_never_mints_honey_route(self):
        config = ResponseConfig(honey_route_enabled=False)
        assert (
            response_action_decision(
                "low", 0.95, "investigate", config, deception_signal=True
            )
            is None
        )

    def test_a_deny_recommendation_above_the_deny_bar_wins_over_honey(self):
        config = ResponseConfig(honey_route_enabled=True)
        action, _ = response_action_decision(
            "low", 0.95, "isolate", config, deception_signal=True
        )
        assert action == "isolate"

    def test_auto_response_off_decides_nothing_even_for_recon(self):
        config = ResponseConfig(honey_route_enabled=True, auto_response_enabled=False)
        assert (
            response_action_decision(
                "low", 0.91, "investigate", config, deception_signal=True
            )
            is None
        )

    def test_a_confidence_outside_zero_to_one_never_steers(self):
        config = ResponseConfig(honey_route_enabled=True)
        assert (
            response_action_decision(
                "low", 1.5, "investigate", config, deception_signal=True
            )
            is None
        )
