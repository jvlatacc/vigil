"""Mode-machine tests: transitions from locally observable facts only."""

from __future__ import annotations

from datetime import timedelta

from services.warden.modes import ModeMachine, OperatingMode
from services.warden.sync import SyncOutcome
from tests.unit.warden.helpers import WARDEN_NOW, FakeClock

OK = SyncOutcome(ok=True)
FAIL = SyncOutcome(ok=False, codes=("S-TRANSPORT",))
REVOKED = SyncOutcome(ok=False, revoked=True, codes=("S-AUTH",))


def machine(**overrides: object) -> tuple[ModeMachine, FakeClock]:
    clock = FakeClock()
    grace = overrides.pop("grace_window_seconds", 900.0)
    threshold = overrides.pop("missed_syncs_threshold", 3)
    return (
        ModeMachine(
            grace_window_seconds=grace,  # type: ignore[arg-type]
            missed_syncs_threshold=threshold,  # type: ignore[arg-type]
        ),
        clock,
    )


class TestBootstrap:
    def test_failed_syncs_leave_bootstrap_waiting(self) -> None:
        m, clock = machine()
        for _ in range(10):
            m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.BOOTSTRAP
        assert not m.can_enforce()

    def test_first_verified_pack_enters_synced(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        assert m.mode is OperatingMode.SYNCED
        assert m.missed_syncs == 0


class TestDegrade:
    def test_three_missed_syncs_degrade(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        m.note_sync(FAIL, now=clock())
        m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.SYNCED
        m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.DEGRADED

    def test_recovery_resets_the_count(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        for _ in range(3):
            m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.DEGRADED
        m.note_sync(OK, now=clock())
        assert m.mode is OperatingMode.SYNCED
        # A later single miss must not carry the old count into degrade.
        m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.SYNCED
        assert m.missed_syncs == 1


class TestAutonomous:
    def test_grace_elapsed_with_pack_in_force(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        for _ in range(3):
            m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.DEGRADED
        clock.advance(seconds=901)
        m.note_grace_check(now=clock(), pack_in_force=True)
        assert m.mode is OperatingMode.AUTONOMOUS
        assert m.can_enforce()

    def test_grace_not_elapsed_stays_degraded(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        for _ in range(3):
            m.note_sync(FAIL, now=clock())
        clock.advance(seconds=899)
        m.note_grace_check(now=clock(), pack_in_force=True)
        assert m.mode is OperatingMode.DEGRADED
        assert not m.can_enforce()

    def test_grace_without_a_pack_never_autonomous(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        for _ in range(3):
            m.note_sync(FAIL, now=clock())
        clock.advance(seconds=901)
        m.note_grace_check(now=clock(), pack_in_force=False)
        assert m.mode is OperatingMode.DEGRADED

    def test_configurable_threshold(self) -> None:
        m, clock = machine(missed_syncs_threshold=2)
        m.note_sync(OK, now=clock())
        m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.SYNCED
        m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.DEGRADED


class TestPassive:
    def test_expiry_from_enforcing_mode(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        m.mode = OperatingMode.AUTONOMOUS  # forced: the ladder to AUTONOMOUS
        m.note_pack_expiry(now=clock())
        assert m.mode is OperatingMode.PASSIVE
        assert not m.can_enforce()

    def test_expiry_from_bootstrap_is_a_no_op(self) -> None:
        m, clock = machine()
        m.note_pack_expiry(now=clock())
        assert m.mode is OperatingMode.BOOTSTRAP

    def test_fresh_pack_recovers_to_synced(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        m.note_sync(FAIL, now=clock())
        m.note_sync(FAIL, now=clock())
        m.note_sync(FAIL, now=clock())
        m.note_pack_expiry(now=clock())
        assert m.mode is OperatingMode.PASSIVE
        m.note_sync(OK, now=clock())
        assert m.mode is OperatingMode.SYNCED

    def test_passive_does_not_degrade_on_failed_syncs(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        m.note_pack_expiry(now=clock())
        for _ in range(5):
            m.note_sync(FAIL, now=clock())
        assert m.mode is OperatingMode.PASSIVE


class TestRevoked:
    def test_observed_revocation_is_terminal(self) -> None:
        m, clock = machine()
        m.note_sync(OK, now=clock())
        m.note_sync(REVOKED, now=clock())
        assert m.mode is OperatingMode.REVOKED
        # Later syncs — even successful ones — never loosen a revocation.
        m.note_sync(OK, now=clock())
        m.note_sync(FAIL, now=clock())
        clock.advance(seconds=timedelta(days=1).seconds)
        m.note_grace_check(now=clock(), pack_in_force=True)
        assert m.mode is OperatingMode.REVOKED
        assert not m.can_enforce()

    def test_revocation_from_bootstrap(self) -> None:
        m, clock = machine()
        m.note_sync(REVOKED, now=clock())
        assert m.mode is OperatingMode.REVOKED


class TestStatus:
    def test_status_reports_the_facts(self) -> None:
        m, clock = machine()
        m.note_sync(FAIL, now=clock())
        status = m.status()
        assert status["mode"] == "BOOTSTRAP"
        assert status["missed_syncs"] == 1
        assert status["first_miss_at"] == WARDEN_NOW.isoformat()
