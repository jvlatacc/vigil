"""The Warden operating-mode machine.

Warden's behavior changes with one question: is the control plane
reachable, and is the verified policy still fresh? This module owns the
answer as a small explicit state machine over **locally observable
facts** — sync outcomes, pack validity, the node's own clock. No
transition is ever driven by a server-authored field, because anything
the control plane says can be forged during a partition. The one
exception is observed revocation (a 401/403 at sync time), and it can
only tighten: it halts the node, never loosens it.

Ladder (spec §Autonomy is a mode, not a switch):

    BOOTSTRAP ──first verified pack──▶ SYNCED ──3 missed syncs──▶ DEGRADED
    DEGRADED ──grace window lapses, pack still in force──▶ AUTONOMOUS
    AUTONOMOUS ──link restored──▶ RECONCILING (the journal drains to the
                                     control plane; enforcement blocked)
    RECONCILING ──all batches accepted──▶ SYNCED
    RECONCILING ──sync fails──▶ DEGRADED (the partition ladder re-arms)
    any non-BOOTSTRAP mode ──pack expiry observed──▶ PASSIVE
    any mode ──observed 401/403──▶ REVOKED (terminal)
    PASSIVE ──fresh verified pack──▶ SYNCED

PASSIVE never enforces on stale authority: the loop undoes live
reversible actions on entry, and enforcement is gated on AUTONOMOUS.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from services.warden.sync import SyncOutcome

__all__ = [
    "MISSED_SYNCS_FOR_DEGRADED",
    "ENFORCING_MODES",
    "OperatingMode",
    "ModeMachine",
]


class OperatingMode(str, Enum):
    """The modes of the spec's lifecycle table."""

    BOOTSTRAP = "BOOTSTRAP"
    SYNCED = "SYNCED"
    DEGRADED = "DEGRADED"
    AUTONOMOUS = "AUTONOMOUS"
    RECONCILING = "RECONCILING"
    PASSIVE = "PASSIVE"
    REVOKED = "REVOKED"


#: Modes in which local enforcement may run. v1 envelopes carry no
#: synced-mode enforcement, so AUTONOMOUS is the only enforcing mode —
#: SYNCED, DEGRADED, and RECONCILING observe and journal, nothing more
#: (RECONCILING runs journal-driven undos; it never enforces).
ENFORCING_MODES = frozenset({OperatingMode.AUTONOMOUS})

#: Consecutive failed syncs that take SYNCED into DEGRADED.
MISSED_SYNCS_FOR_DEGRADED = 3


class ModeMachine:
    """Transitions from locally observable facts only.

    The machine records *observations* (``note_sync``, ``note_pack_expiry``,
    ``note_grace_check``) and derives the mode; it never syncs, never
    enforces, and reads no clock of its own — callers inject ``now`` so
    mode behavior is deterministic under a controllable clock.
    """

    def __init__(
        self,
        *,
        grace_window_seconds: float,
        missed_syncs_threshold: int = MISSED_SYNCS_FOR_DEGRADED,
    ) -> None:
        self.grace_window = timedelta(seconds=grace_window_seconds)
        self.missed_syncs_threshold = missed_syncs_threshold
        self.mode = OperatingMode.BOOTSTRAP
        self.missed_syncs = 0
        self._first_miss_at: datetime | None = None

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def note_sync(self, outcome: SyncOutcome, *, now: datetime) -> None:
        """Fold one sync cycle's outcome into the mode state.

        REVOKED is terminal: observed once, never left. A successful sync
        recovers to SYNCED from any live mode (BOOTSTRAP's first pack,
        DEGRADED's recovery, PASSIVE's fresh authority) — except from
        AUTONOMOUS, which hands to RECONCILING: the journal drains before
        the node may call itself SYNCED again. Failures only ever count;
        they degrade SYNCED or RECONCILING and leave BOOTSTRAP and
        PASSIVE to wait for the facts that can actually move them.
        """
        if self.mode is OperatingMode.REVOKED:
            return
        if outcome.revoked:
            self.mode = OperatingMode.REVOKED
            return
        if outcome.ok:
            self.missed_syncs = 0
            self._first_miss_at = None
            if self.mode is OperatingMode.AUTONOMOUS:
                self.mode = OperatingMode.RECONCILING
            elif self.mode is not OperatingMode.RECONCILING:
                self.mode = OperatingMode.SYNCED
            return
        self.missed_syncs += 1
        if self._first_miss_at is None:
            self._first_miss_at = now
        if (
            self.mode in (OperatingMode.SYNCED, OperatingMode.RECONCILING)
            and self.missed_syncs >= self.missed_syncs_threshold
        ):
            self.mode = OperatingMode.DEGRADED

    def note_reconcile_complete(self) -> None:
        """The journal drained: RECONCILING closes back to SYNCED.

        Only the Reconciler calls this — an ok sync HOLDS RECONCILING, so
        a drained journal, not sync cadence, decides when the node may
        re-enter the enforcing postures. No-op outside RECONCILING.
        """
        if self.mode is OperatingMode.RECONCILING:
            self.mode = OperatingMode.SYNCED

    def note_pack_expiry(self, *, now: datetime) -> None:
        """The clock passed ``not_after`` on the verified pack.

        Authority lapsed: PASSIVE, from every mode that ever held a pack.
        BOOTSTRAP never held authority (nothing to lapse), and REVOKED is
        terminal — neither moves.
        """
        del now  # the observation is the caller's clock read
        if self.mode in (OperatingMode.BOOTSTRAP, OperatingMode.REVOKED):
            return
        self.mode = OperatingMode.PASSIVE

    def note_grace_check(self, *, now: datetime, pack_in_force: bool) -> None:
        """DEGRADED past the grace window with a pack still in force.

        AUTONOMOUS requires both facts — elapsed grace AND unexpired
        signed authority. A lapsed pack is PASSIVE's business, handled by
        :meth:`note_pack_expiry`; without a pack at all the node stays
        DEGRADED (a partition with no policy defends nothing).
        """
        if self.mode is not OperatingMode.DEGRADED or self._first_miss_at is None:
            return
        if not pack_in_force:
            return
        if now - self._first_miss_at >= self.grace_window:
            self.mode = OperatingMode.AUTONOMOUS

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def can_enforce(self) -> bool:
        """Whether local enforcement may run in the current mode."""
        return self.mode in ENFORCING_MODES

    def status(self) -> dict[str, object]:
        """The mode facts health/status surfaces to the operator."""
        return {
            "mode": self.mode.value,
            "missed_syncs": self.missed_syncs,
            "grace_window_seconds": self.grace_window.total_seconds(),
            "first_miss_at": (
                self._first_miss_at.isoformat() if self._first_miss_at else None
            ),
        }
