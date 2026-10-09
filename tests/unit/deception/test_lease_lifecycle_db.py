"""The durable half of the spine, against the throwaway Postgres.

AC3/AC4 — approval rows and per-attacker idempotency over real tables;
AC6 — the sweep with a fake clock: expiry, renewal under the cap, orphans;
AC7 — the kill-switch from its two sources, and the steer refusal it causes.
"""

import asyncio
from datetime import timedelta

import pytest

from tests.unit.deception.fixtures import ATTACKER, VICTIM

from core.deception.backends import DryRunBackend
from core.deception.config import KILL_SWITCH_CONFIG_KEY, DeceptionConfig
from core.deception.leases import DeceptionLeaseService
from core.deception.signals import DeceptionSignalService
from core.response.approval_service import ActionType, ApprovalService
from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import ResponseConfig
from core.time import utcnow

pytestmark = [pytest.mark.unit, pytest.mark.external_service]

T0 = utcnow().replace(microsecond=0)


@pytest.fixture(autouse=True)
def _clean_deception_tables():
    """Empty the state these tests write, before each test.

    The throwaway database is session-scoped: without this, one test's probes
    and leases corroborate the next test's attacker. Order honours the lease
    → approval foreign key.
    """
    from core.storage.connection import get_db_manager
    from core.storage.models.config import SystemConfig
    from core.storage.models.deception import DeceptionLease, DeceptionProbe
    from core.storage.models.workflow import ApprovalAction

    with get_db_manager().session_scope() as session:
        session.query(DeceptionProbe).delete()
        session.query(DeceptionLease).delete()
        session.query(ApprovalAction).filter_by(action_type="honey_route").delete()
        session.query(SystemConfig).filter_by(key=KILL_SWITCH_CONFIG_KEY).delete()
    yield


def _lease_config(**overrides):
    config = DeceptionConfig(
        enabled=True, ttl_seconds=3600, max_duration_seconds=86400, min_observations=3
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _service(config=None, backend=None) -> DeceptionLeaseService:
    return DeceptionLeaseService(config=config or _lease_config(), backend=backend or DryRunBackend())


def _mint_steered(config=None, attacker=ATTACKER, now=None):
    service = _service(config)
    now = now or T0
    lease_id = service.mint(
        attacker_ip=attacker,
        destination_ips=[VICTIM],
        ports=[445],
        action_id=None,
        ttl_seconds=config.ttl_seconds if config else 3600,
        now=now,
    )
    result = asyncio.run(service.steer_lease(lease_id, now=now))
    assert result["success"], result
    return service, lease_id, now


def _probes(config, ip, at, count, prefix="f"):
    signals = DeceptionSignalService(config=config)
    for i in range(count):
        signals.record_probe(ip, f"{prefix}-{i}", {}, now=at)


class TestActionCreationAndIdempotency:
    def _response(self, config: ResponseConfig):
        return AutonomousResponseService(approvals=ApprovalService(config=config), config=config)

    def test_an_auto_approved_row_executes_through_the_dry_run_backend(self):
        response = self._response(ResponseConfig(honey_route_enabled=True))
        result = response.create_honey_route_action(
            attacker_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445, 3389],
            confidence=0.85,
            reason="corroborated recon",
            evidence=["find-1"],
        )
        assert result["status"] == "executed"
        # execution_result carries the lease record the sweep unsteers from.
        assert result["result"]["lease_id"]
        assert result["result"]["ttl"] == 3600
        assert result["result"]["rollback"] == f"DELETE /steer/{result['result']['lease_id']}"
        assert result["result"]["backend"] == "dry_run"

        lease = _service().by_action(result["action_id"])
        assert lease is not None and lease.status == "active"
        assert lease.attacker_ip == ATTACKER

    def test_below_the_floor_the_row_waits_for_an_analyst(self):
        response = self._response(ResponseConfig(honey_route_enabled=True))
        result = response.create_honey_route_action(
            attacker_ip=ATTACKER,
            destination_ips=[VICTIM],
            ports=[445],
            confidence=0.75,
            reason="corroborated recon",
            evidence=["find-1"],
        )
        assert result["status"] == "pending_approval"
        assert result["requires_approval"] is True

    def test_one_attacker_probing_many_hosts_yields_one_lease(self):
        response = self._response(ResponseConfig(honey_route_enabled=True))
        first = response.create_honey_route_action(
            attacker_ip=ATTACKER, destination_ips=[VICTIM], ports=[445],
            confidence=0.75, reason="r", evidence=[],
        )
        for victim in ("10.0.4.26", "10.0.4.27"):  # more victims, same attacker
            again = response.create_honey_route_action(
                attacker_ip=ATTACKER, destination_ips=[victim], ports=[22],
                confidence=0.75, reason="r", evidence=[],
            )
            assert again["reused"] is True
            assert again["action_id"] == first["action_id"]

        rows = response.approval_service.list_actions(action_type=ActionType.HONEY_ROUTE)
        assert len(rows) == 1

    def test_a_failed_row_permits_a_re_mint(self):
        response = self._response(ResponseConfig(honey_route_enabled=True))
        # The first mint fails (a backend outage); the row is FAILED.
        with pytest.MonkeyPatch.context() as patched:
            class _Broken:
                name = "broken"

                async def steer(self, scope):
                    return {"success": False, "error": "outage"}

                async def unsteer(self, lease_id, backend_ref):
                    return {"success": True}

                async def status(self, lease_id):
                    return {"success": False}

            from core.deception import leases as leases_module

            def _broken_service(**_):
                return DeceptionLeaseService(config=_lease_config(), backend=_Broken())

            patched.setattr(leases_module, "DeceptionLeaseService", _broken_service)
            first = response.create_honey_route_action(
                attacker_ip="198.51.100.9", destination_ips=[VICTIM], ports=[445],
                confidence=0.85, reason="r", evidence=[],
            )
        assert first["status"] == "failed"

        second = response.create_honey_route_action(
            attacker_ip="198.51.100.9", destination_ips=[VICTIM], ports=[445],
            confidence=0.85, reason="r", evidence=[],
        )
        assert second["status"] == "executed"  # re-minted, not blocked by the failure
        assert second["action_id"] != first["action_id"]


class TestTheSweep:
    def test_an_empty_registry_is_a_no_op(self):
        out = asyncio.run(_service().sweep(now=T0))
        assert out == {"released": [], "renewed": [], "expired": [], "failed": []}

    def test_an_expired_lease_is_unsteered_and_released_with_audit(self):
        service, lease_id, t0 = _mint_steered()
        out = asyncio.run(service.sweep(now=t0 + timedelta(seconds=3700)))
        assert out["expired"] == [lease_id]
        row = service.get(lease_id)
        assert row.status == "released"
        assert row.release_reason == "ttl_expired"
        assert row.released_at is not None
        assert row.rollback_result["success"] is True

    def test_a_corroborated_lease_renews_under_the_cap(self):
        config = _lease_config()
        service, lease_id, t0 = _mint_steered(config)
        later = t0 + timedelta(seconds=3300)  # past half the TTL
        _probes(config, ATTACKER, later - timedelta(seconds=60), 3)
        out = asyncio.run(service.sweep(now=later, signals=DeceptionSignalService(config=config)))
        assert out["renewed"] == [lease_id]
        row = service.get(lease_id)
        assert row.renewal_count == 1
        assert row.expires_at > later

    def test_a_quiet_lease_is_left_to_expire(self):
        config = _lease_config()
        service, lease_id, t0 = _mint_steered(config)
        later = t0 + timedelta(seconds=3300)
        out = asyncio.run(service.sweep(now=later, signals=DeceptionSignalService(config=config)))
        assert out["renewed"] == [] and out["expired"] == []
        row = service.get(lease_id)
        assert row.renewal_count == 0

    def test_the_max_duration_cap_releases_a_renewed_lease(self):
        config = _lease_config(max_duration_seconds=1800)
        service, lease_id, t0 = _mint_steered(config)
        later = t0 + timedelta(seconds=1800)  # at the cap, inside renewal window
        _probes(config, ATTACKER, later - timedelta(seconds=60), 3)
        out = asyncio.run(service.sweep(now=later, signals=DeceptionSignalService(config=config)))
        assert out["expired"] == [lease_id]
        row = service.get(lease_id)
        assert row.release_reason == "max_duration"

    def test_an_orphaned_pending_row_is_released(self):
        service = _service()
        lease_id = service.mint(
            attacker_ip=ATTACKER, destination_ips=[VICTIM], ports=[445],
            action_id=None, ttl_seconds=3600, now=T0,
        )  # minted, never steered
        out = asyncio.run(service.sweep(now=T0 + timedelta(seconds=2 * 3600 + 1)))
        assert out["released"] == [lease_id]
        assert service.get(lease_id).release_reason == "orphaned_pending"


class TestTheKillSwitch:
    def test_the_env_override_refuses_to_steer(self):
        config = _lease_config(kill_switch=True)
        service = _service(config)
        backend = service.backend
        lease_id = service.mint(
            attacker_ip=ATTACKER, destination_ips=[VICTIM], ports=[445],
            action_id=None, ttl_seconds=3600, now=T0,
        )
        result = asyncio.run(service.steer_lease(lease_id, now=T0))
        assert result["success"] is False
        assert result["error"] == "kill_switch_active"
        assert backend.steered == []  # nothing was programmed
        row = service.get(lease_id)
        assert row.status == "released"
        assert row.release_reason == "kill_switch"

    def test_the_stored_toggle_trips_the_switch(self):
        from core.storage.config_service import get_config_service

        config = _lease_config()
        service = _service(config)
        signals = DeceptionSignalService(config=config)
        assert signals.kill_switch_active(now=T0) is False
        # A live lease first...
        lease_id = service.mint(
            attacker_ip=ATTACKER, destination_ips=[VICTIM], ports=[445],
            action_id=None, ttl_seconds=3600, now=T0,
        )
        assert asyncio.run(service.steer_lease(lease_id, now=T0))["success"] is True
        # ...then the operator trips the stored toggle.
        assert get_config_service().set_system_config(
            key=KILL_SWITCH_CONFIG_KEY, value={"enabled": True},
            description="test", change_reason="test",
        )
        try:
            assert signals.kill_switch_active(now=T0) is True
            # New steering is refused...
            refused = service.mint(
                attacker_ip="198.51.100.9", destination_ips=[VICTIM], ports=[445],
                action_id=None, ttl_seconds=3600, now=T0,
            )
            assert asyncio.run(service.steer_lease(refused, now=T0))["success"] is False
            # ...and the sweep releases what was already open.
            out = asyncio.run(service.sweep(now=T0, signals=signals))
            assert lease_id in out["released"]
        finally:
            from core.storage.connection import get_db_manager
            from core.storage.models.config import SystemConfig

            with get_db_manager().session_scope() as session:
                row = (
                    session.query(SystemConfig).filter_by(key=KILL_SWITCH_CONFIG_KEY).first()
                )
                if row:
                    session.delete(row)

    def test_a_failed_toggle_read_answers_pessimistically(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("config store down")

        monkeypatch.setattr(
            "core.storage.config_service.get_config_service", _boom
        )
        signals = DeceptionSignalService(config=_lease_config())
        assert signals.kill_switch_active(now=T0) is True


class TestCorroboration:
    def test_distinct_findings_count_re_deliveries_do_not(self):
        config = _lease_config()
        service = DeceptionSignalService(config=config)
        for i in range(3):
            service.record_probe(ATTACKER, "find-1" if i < 2 else f"find-{i}", {}, now=T0)
        assert service.is_corroborated(ATTACKER, now=T0 + timedelta(seconds=1)) is False

        service.record_probe(ATTACKER, "find-3", {}, now=T0 + timedelta(seconds=2))
        assert service.is_corroborated(ATTACKER, now=T0 + timedelta(seconds=3)) is True

    def test_probes_outside_the_window_do_not_corroborate(self):
        config = _lease_config(window_seconds=3600)
        service = DeceptionSignalService(config=config)
        for i in range(4):
            service.record_probe(ATTACKER, f"find-{i}", {}, now=T0 - timedelta(seconds=3700))
        assert service.is_corroborated(ATTACKER, now=T0) is False

    def test_the_prune_drops_only_stale_evidence(self):
        config = _lease_config(window_seconds=3600)
        service = DeceptionSignalService(config=config)
        service.record_probe(ATTACKER, "old", {}, now=T0 - timedelta(seconds=8000))
        service.record_probe(ATTACKER, "new", {}, now=T0)
        pruned = service.prune(now=T0)
        assert pruned == 1
        assert service.is_corroborated(ATTACKER, now=T0) is False  # only "new" remains
