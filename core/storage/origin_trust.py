"""The origin-trust vocabulary, stored with the column it names.

Every finding carries an ``origin_trust`` tier, set once by the receiver
that accepted it — never read from the payload and never inferred later.
The tiers order::

    unverified < transport < signed

``unverified``
    A webhook accepted without a configured shared secret: the payload
    arrived, but nobody vouches for who sent it.
``transport``
    The channel authenticated the sender: a bearer-keyed push, a credentialed
    pull adapter, or Vigil's own daemon pipeline.
``signed``
    The payload carried a valid HMAC over its bytes, so the receiver proved
    the sender holds the per-source shared secret
    (core/ingestion/webhook_origin.py).

The vocabulary lives in core.storage because the tier is a column on the
finding model and the persistence funnels normalize through it — and the
import-linter tiers contract rightly forbids shared infrastructure from
importing a capability domain. The response policy that acts on tiers (the
origin floor, corroboration) lives in core/response/origin.py, which imports
this module; nothing here may import back.
"""

from __future__ import annotations

from typing import Any

ORIGIN_UNVERIFIED = "unverified"
ORIGIN_TRANSPORT = "transport"
ORIGIN_SIGNED = "signed"

# Rank order for comparisons: a higher rank is a stronger vouch.
ORIGIN_TIERS = (ORIGIN_UNVERIFIED, ORIGIN_TRANSPORT, ORIGIN_SIGNED)

# The tier stamped when nobody vouched: a row whose provenance nobody
# vouched for must never look trusted.
ORIGIN_DEFAULT = ORIGIN_UNVERIFIED

_ORIGIN_RANKS = {name: rank for rank, name in enumerate(ORIGIN_TIERS)}


def tier_rank(tier: Any) -> "int | None":
    """The tier's rank, or None for anything no importer could have stamped.

    A missing or unknown tier can never masquerade as a known one: the caller
    decides what ``None`` means, and every caller here treats it as unproved.
    """
    if not isinstance(tier, str):
        return None
    return _ORIGIN_RANKS.get(tier.strip().lower())


def trusted_tier(value: Any, default: str = ORIGIN_DEFAULT) -> str:
    """The tier ``value`` names, or ``default`` when it names none.

    The storage funnel validates every stamped tier through here: a typo in
    an importer falls back to the caller's default rather than crashing the
    insert or storing a string no tier order can rank. ``default`` is how an
    authenticated funnel raises the floor for rows its importers did not
    stamp (an operator upload job passes ``transport``).
    """
    rank = tier_rank(value)
    return ORIGIN_TIERS[rank] if rank is not None else default
