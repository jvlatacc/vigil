"""Origin trust policy: what unattended containment may act on.

The tier vocabulary itself lives beside the column it names
(core/storage/origin_trust.py) and is re-exported here so the response layer
has one import home. This module adds the response policy: the origin floor
(``ResponseConfig.min_origin_trust``) bounds what unattended containment may
act on — a row whose finding sits below the floor waits for a person unless
enough distinct data sources named the same target inside the corroboration
window. Independent claims beat a single unverified one.

A tier proves who sent an alert, never that the alert is true. The
never-quarantine invariants (PR1) bound what even a trusted feed can cause;
this module never tries to detect the lie, only to price the vouch.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.storage.origin_trust import (  # noqa: F401  (re-exported vocabulary)
    ORIGIN_DEFAULT,
    ORIGIN_SIGNED,
    ORIGIN_TIERS,
    ORIGIN_TRANSPORT,
    ORIGIN_UNVERIFIED,
    tier_rank,
    trusted_tier,
)

# The audit key a row's parameters carry, naming the finding the action
# responds to and the tier it claimed at decision time.
FINDING_CONTEXT_KEY = "finding"


def tier_name(rank: Optional[int]) -> str:
    """The tier a rank names; an out-of-range rank has no name."""
    if rank is None or rank < 0 or rank >= len(ORIGIN_TIERS):
        return ORIGIN_DEFAULT
    return ORIGIN_TIERS[rank]


def corroboration_probe(
    target: Optional[str], parameters: Optional[Mapping[str, Any]]
) -> Optional[Dict[str, Any]]:
    """The JSONB containment probe matching findings that name the target.

    Address targets match ``src_ips``; a hostname-keyed row (isolate_host
    without a usable IP) matches ``hostnames``. A probe of None means the
    target cannot be tied to findings at all — a range with no anchor, an
    opaque string — and the caller holds the action rather than guess.
    """
    if not isinstance(target, str) or not target.strip():
        return None
    candidate = target.strip()
    if candidate.count("/") == 1 and candidate.split("/", 1)[1].isdigit():
        # A CIDR range: individual src_ips entries cannot contain-match it.
        return None
    return {"src_ips": [candidate]}


def origin_probe_from_hostname(
    parameters: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The probe for a row whose actionable target was a hostname."""
    if not parameters:
        return None
    hostname = parameters.get("hostname")
    if not isinstance(hostname, str) or not hostname.strip():
        return None
    return {"hostnames": [hostname.strip()]}
