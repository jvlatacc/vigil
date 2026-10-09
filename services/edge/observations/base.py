"""The observation contract and the pluggable input interface.

An Observation is the normalized shape every input adapter owes the gate
(design spec, "Observation tail"): timestamp, direction, src/dst, domain,
protocol, and a reference to the raw record — the digest is evidence, the raw
line stays in its file. Inputs implement ObservationInput; v1 ships the
JSON-lines file tail (Suricata EVE and similar). No agent is installed on
monitored hosts — the daemon defends the segment.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, runtime_checkable

DIRECTIONS = ("ingress", "egress", "unknown")


def digest_raw(raw: bytes) -> str:
    """The evidence digest a decision record cites for its observation."""
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    direction: str  # ingress | egress | unknown
    src_ip: str | None
    dest_ip: str | None
    dest_domain: str | None
    proto: str | None
    event_type: str
    raw_digest: str
    raw_ref: str  # file:offset — where the raw record lives

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(
                f"direction must be one of {DIRECTIONS}, got {self.direction!r}"
            )
        if self.timestamp.tzinfo is None:
            raise ValueError("observation timestamp must be timezone-aware")


@runtime_checkable
class ObservationInput(Protocol):
    """A source of observations. run() pumps records to handler until
    cancelled; close() releases whatever the input holds."""

    name: str

    async def run(self, handler: Callable[[Observation], Awaitable[None]]) -> None: ...

    async def close(self) -> None: ...
