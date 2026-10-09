"""Edge wire-format primitives: strict JSON and the one timestamp shape.

Shared by the envelope verifier (``verify.py``) and the policy parser
(``policy.py``) so both sides of the mesh read bytes identically. The
strictness here is load-bearing, not pedantic: duplicate JSON keys mean a
reviewer and the loader could read different values from the same signed
bytes, and NaN/Infinity must never survive into a confidence comparison.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

# The single timestamp wire format for edge envelopes and policies. Kept to a
# strict shape so a comparison against a parsed value can never depend on
# locale or fractional-second parsing.
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_ts(value: str) -> datetime:
    """Parse the edge wire timestamp (``2026-10-09T12:00:00Z``) as UTC."""
    return datetime.strptime(value, TS_FORMAT).replace(tzinfo=UTC)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON keys")
    return dict(pairs)


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard constant {name}")


def strict_json_loads(data: bytes) -> Any:
    """``json.loads`` that refuses duplicate keys, NaN/Infinity, and trailing data.

    Raises ``ValueError`` (or ``UnicodeDecodeError``) on any input a careful
    reviewer would read differently than a naive parser would.
    """
    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
    )
