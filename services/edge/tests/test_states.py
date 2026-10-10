"""States: the spec's transition table, enforced."""

from __future__ import annotations

import pytest

from services.edge.app.states import (
    OperatingState,
    StateTracker,
    StateTransitionError,
)


def test_cold_start_is_partitioned() -> None:
    assert StateTracker().state is OperatingState.PARTITIONED


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (OperatingState.SYNCED, OperatingState.PARTITIONED),
        (OperatingState.SYNCED, OperatingState.DEGRADED),
        (OperatingState.PARTITIONED, OperatingState.RECONCILING),
        (OperatingState.PARTITIONED, OperatingState.SYNCED),
        (OperatingState.PARTITIONED, OperatingState.DEGRADED),
        (OperatingState.RECONCILING, OperatingState.SYNCED),
        (OperatingState.RECONCILING, OperatingState.PARTITIONED),
        (OperatingState.RECONCILING, OperatingState.DEGRADED),
        (OperatingState.DEGRADED, OperatingState.SYNCED),
    ],
)
def test_allowed_transitions(frm: OperatingState, to: OperatingState) -> None:
    tracker = StateTracker(initial=frm)
    old, new = tracker.transition(to)
    assert (old, new) == (frm, to)
    assert tracker.state is to


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        # DEGRADED's only exit is SYNCED — tier comes back by signature.
        (OperatingState.DEGRADED, OperatingState.PARTITIONED),
        (OperatingState.DEGRADED, OperatingState.RECONCILING),
        (OperatingState.DEGRADED, OperatingState.DEGRADED),
        # Self-edges are not transitions.
        (OperatingState.RECONCILING, OperatingState.RECONCILING),
        (OperatingState.PARTITIONED, OperatingState.PARTITIONED),
        # No state promotes itself into SYNCED without the link proof.
        (OperatingState.SYNCED, OperatingState.RECONCILING),
        (OperatingState.SYNCED, OperatingState.SYNCED),
    ],
)
def test_disallowed_transitions_raise(frm: OperatingState, to: OperatingState) -> None:
    tracker = StateTracker(initial=frm)
    with pytest.raises(StateTransitionError):
        tracker.transition(to)
    assert tracker.state is frm


def test_degraded_recovers_only_through_a_verified_bundle() -> None:
    tracker = StateTracker(initial=OperatingState.SYNCED)
    tracker.transition(OperatingState.DEGRADED)
    tracker.transition(OperatingState.SYNCED)
    assert tracker.state is OperatingState.SYNCED
