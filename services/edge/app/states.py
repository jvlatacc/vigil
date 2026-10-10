"""Operating states: partition changes what the daemon may do, never whether it runs.

Four states, one floor. Every state may demote to Tier 0 (observe and journal
only); nothing here may promote itself (design spec, "Partition is a state,
not an error"). Transitions are validated against the spec's state table so
the caller can journal each one and the offline window reconstructs from the
record.
"""

from __future__ import annotations

from enum import StrEnum


class OperatingState(StrEnum):
    SYNCED = "synced"
    PARTITIONED = "partitioned"
    RECONCILING = "reconciling"
    DEGRADED = "degraded"


class StateTransitionError(ValueError):
    """A transition the state machine does not allow."""


# The edges of the design spec's state table. DEGRADED's only exit is a new
# verified bundle -> SYNCED: tier is restored by a signature, not by the clock.
ALLOWED: frozenset[tuple[OperatingState, OperatingState]] = frozenset(
    {
        (OperatingState.SYNCED, OperatingState.PARTITIONED),
        (OperatingState.SYNCED, OperatingState.DEGRADED),
        (OperatingState.PARTITIONED, OperatingState.RECONCILING),
        (OperatingState.PARTITIONED, OperatingState.SYNCED),
        (OperatingState.PARTITIONED, OperatingState.DEGRADED),
        (OperatingState.RECONCILING, OperatingState.SYNCED),
        (OperatingState.RECONCILING, OperatingState.PARTITIONED),
        (OperatingState.RECONCILING, OperatingState.DEGRADED),
        (OperatingState.DEGRADED, OperatingState.SYNCED),
    }
)


class StateTracker:
    """Holds the current state. :meth:`transition` returns ``(old, new)`` so
    the caller journals the transition; a disallowed edge raises rather than
    quietly holding a state the record will not show.

    Cold start is PARTITIONED: until a heartbeat (the sync client's job)
    proves otherwise, the control plane is unreachable.
    """

    def __init__(self, initial: OperatingState = OperatingState.PARTITIONED) -> None:
        self._state = initial

    @property
    def state(self) -> OperatingState:
        return self._state

    def transition(self, to: OperatingState) -> tuple[OperatingState, OperatingState]:
        edge = (self._state, to)
        if edge not in ALLOWED:
            raise StateTransitionError(
                f"{self._state.value} -> {to.value} is not an allowed transition"
            )
        old, self._state = self._state, to
        return old, to
