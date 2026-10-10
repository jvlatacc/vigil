"""Autonomy tiers — fixed in code; the bundle selects, never widens.

Tier 0: observe and journal only. Tier 1: prevent against exact bundle IOCs.
Tier 2: reversible network containment within caps and TTLs — the v1 ceiling.
Tier 3+ exist in the enum because the central pipeline's vocabulary has them,
but they are unsignable in v1: verification refuses any bundle claiming them,
preserving the central rule that irreversible actions always stop for a human
(design spec, "Policy bundle — what the operator actually signs").
"""

from __future__ import annotations

from enum import IntEnum


class AutonomyTier(IntEnum):
    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


V1_CEILING = AutonomyTier.TIER_2
"""The highest tier a v1 bundle may carry. Verification rejects above it."""

UNSIGNABLE: frozenset[AutonomyTier] = frozenset(
    {AutonomyTier.TIER_3, AutonomyTier.TIER_4}
)


def parse_tier(raw: str) -> AutonomyTier:
    """``"tier2"`` -> TIER_2. Unknown labels raise ValueError; the verifier
    maps that to a refusal (B-TIER)."""
    normalized = raw.strip().lower()
    if normalized.startswith("tier") and normalized[4:].isdigit():
        return AutonomyTier(int(normalized[4:]))
    raise ValueError(f"unknown tier label: {raw!r}")


def tier_label(tier: AutonomyTier | None) -> str:
    """Tier 2 -> ``"tier2"``. None (no bundle yet) -> ``"tier0"``: no bundle
    is the floor."""
    if tier is None:
        return "tier0"
    return f"tier{tier.value}"
