"""Tier vocabulary: the ceiling is code, not config."""

import pytest

from services.edge.gate.tiers import V1_CEILING, AutonomyTier, parse_tier, tier_label


def test_parse_valid_labels() -> None:
    assert parse_tier("tier0") is AutonomyTier.TIER_0
    assert parse_tier("tier2") is AutonomyTier.TIER_2
    assert parse_tier("TIER2") is AutonomyTier.TIER_2  # case-insensitive
    assert parse_tier(" tier1 ") is AutonomyTier.TIER_1  # whitespace tolerated


def test_parse_unknown_label_raises() -> None:
    with pytest.raises(ValueError, match="unknown tier label"):
        parse_tier("autonomous")


def test_v1_ceiling_is_tier2() -> None:
    assert V1_CEILING is AutonomyTier.TIER_2
    assert AutonomyTier.TIER_3 > V1_CEILING


def test_tier_label_roundtrip() -> None:
    assert tier_label(AutonomyTier.TIER_2) == "tier2"
    assert tier_label(None) == "tier0"  # no bundle is the floor
