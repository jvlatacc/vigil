"""Decoy-controller HTTP surface — spec AC9.

Runs the real FastAPI app over the ASGI transport (no sockets, no database):
every endpoint must deny unauthenticated calls, reconcile must be idempotent,
and drain must remove every rule the controller created.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from services.decoy_controller.config import ControllerConfig
from services.decoy_controller.main import create_app

TOKEN = "test-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
STEER_BODY = {
    "lease_id": "lease-abc123",
    "source_ip": "203.0.113.7",
    "destination_ips": ["10.0.4.25"],
    "ports": [445, 3389],
    "ttl_seconds": 600,
}


@pytest.fixture
def client():
    config = ControllerConfig(token=TOKEN, sweep_interval=3600, boot_drain=True)
    with TestClient(create_app(config)) as test_client:
        yield test_client


class TestAuth:
    def test_health_is_open_but_dataless(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "driver": "memory"}

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "/steer", STEER_BODY),
            ("delete", "/steer/lease-abc123", None),
            ("get", "/steer/lease-abc123", None),
            ("get", "/reconcile", None),
            ("post", "/drain", {"reason": "test"}),
        ],
    )
    def test_every_endpoint_denies_missing_token(self, client, method, path, body):
        kwargs = {"headers": {}} if body is None else {"json": body, "headers": {}}
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "/steer", STEER_BODY),
            ("delete", "/steer/lease-abc123", None),
            ("get", "/reconcile", None),
            ("post", "/drain", None),
        ],
    )
    def test_every_endpoint_denies_wrong_token(self, client, method, path, body):
        kwargs = {"headers": {"Authorization": "Bearer wrong-token"}}
        if body is not None:
            kwargs["json"] = body
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 401

    def test_scheme_must_be_bearer(self, client):
        resp = client.get("/reconcile", headers={"Authorization": f"Basic {TOKEN}"})
        assert resp.status_code == 401

    def test_configured_without_token_denies_everything(self):
        # The deny-by-default rule: an enforcement plane with no credential
        # never trusts whoever can reach the port.
        config = ControllerConfig(token="", boot_drain=False)
        with TestClient(create_app(config)) as unsecured:
            assert unsecured.get("/reconcile").status_code == 401
            assert unsecured.post("/steer", json=STEER_BODY).status_code == 401


class TestSteer:
    def test_steer_applies_and_reports_a_backend_ref(self, client):
        resp = client.post("/steer", json=STEER_BODY, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["lease_id"] == "lease-abc123"
        assert data["ref"].startswith("memory:")
        assert data["ttl_seconds"] == 600

    def test_ttl_is_capped_at_the_controller_ceiling(self, client):
        body = {**STEER_BODY, "ttl_seconds": 7 * 24 * 3600}
        resp = client.post("/steer", json=body, headers=AUTH)
        assert resp.json()["ttl_capped"] is True
        assert resp.json()["ttl_seconds"] == 86400

    def test_oversized_ttl_is_rejected_before_the_ceiling(self, client):
        body = {**STEER_BODY, "ttl_seconds": 30 * 24 * 3600}
        resp = client.post("/steer", json=body, headers=AUTH)
        assert resp.status_code == 422

    def test_invalid_source_ip_is_rejected(self, client):
        body = {**STEER_BODY, "source_ip": "not-an-ip"}
        assert client.post("/steer", json=body, headers=AUTH).status_code == 422

    def test_validation_rejects_empty_scope(self, client):
        body = {**STEER_BODY, "ports": []}
        assert client.post("/steer", json=body, headers=AUTH).status_code == 422


class TestReconcileIdempotence:
    def test_reconcile_is_a_pure_read(self, client):
        client.post("/steer", json=STEER_BODY, headers=AUTH)
        first = client.get("/reconcile", headers=AUTH).json()
        second = client.get("/reconcile", headers=AUTH).json()
        assert first == second
        assert first["count"] == 1
        assert first["driver"] == "memory"

    def test_resteer_is_idempotent_one_rule_not_two(self, client):
        # Renewal is the same call: one attacker, one lease, one rule.
        client.post("/steer", json=STEER_BODY, headers=AUTH)
        resp = client.post("/steer", json=STEER_BODY, headers=AUTH)
        assert resp.status_code == 200
        assert client.get("/reconcile", headers=AUTH).json()["count"] == 1

    def test_reconcile_reports_what_a_drain_left(self, client):
        client.post("/steer", json=STEER_BODY, headers=AUTH)
        client.post("/drain", json={"reason": "test"}, headers=AUTH)
        assert client.get("/reconcile", headers=AUTH).json()["count"] == 0


class TestDrain:
    def test_drain_removes_every_rule(self, client):
        for i in range(3):
            client.post(
                "/steer",
                json={**STEER_BODY, "lease_id": f"lease-{i}"},
                headers=AUTH,
            )
        resp = client.post("/drain", json={"reason": "kill"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert sorted(data["removed"]) == ["lease-0", "lease-1", "lease-2"]
        assert client.get("/reconcile", headers=AUTH).json()["count"] == 0

    def test_drain_on_an_empty_controller_succeeds(self, client):
        resp = client.post("/drain", headers=AUTH)  # no body at all
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestUnsteer:
    def test_unsteer_removes_one_lease(self, client):
        client.post("/steer", json=STEER_BODY, headers=AUTH)
        resp = client.delete("/steer/lease-abc123", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["removed"] is True
        assert client.get("/reconcile", headers=AUTH).json()["count"] == 0

    def test_unsteering_an_unknown_lease_succeeds(self, client):
        # Idempotent rollback: removing what is not held is still success —
        # the sweep that releases a lease must not fail on a restarted
        # controller that already forgot it.
        resp = client.delete("/steer/never-existed", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["removed"] is False


class TestLeaseStatus:
    def test_status_404s_for_unknown_lease(self, client):
        assert client.get("/steer/nope", headers=AUTH).status_code == 404

    def test_status_shows_the_held_rule(self, client):
        client.post("/steer", json=STEER_BODY, headers=AUTH)
        data = client.get("/steer/lease-abc123", headers=AUTH).json()
        assert data["rule"]["lease_id"] == "lease-abc123"
        assert data["rule"]["source_ip"] == "203.0.113.7"
        assert data["driver"] == "memory"


class TestTtlReaper:
    def test_expired_leases_are_reaped_controller_side(self, client):
        # The controller enforces expiry itself — the client-side sweep is
        # a second line, never the only one.
        controller = client.app.state.controller
        body = {**STEER_BODY, "ttl_seconds": 1}
        client.post("/steer", json=body, headers=AUTH)
        reaped = asyncio.run(controller.reap(now=999999999999.0))
        assert reaped == ["lease-abc123"]
        assert client.get("/reconcile", headers=AUTH).json()["count"] == 0
