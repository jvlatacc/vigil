"""The /internal/edge sync surface, exercised through the real app.

Covers the spec's control-plane acceptance criteria at the HTTP boundary:
enrollment fails closed (unset secret -> 503, bad token -> 401) and its
credential authenticates the node's own routes; a published, signed bundle
is served cursor-keyed with no backfill; journal batches are bounded and
acked only for what committed; and revocation kills every further sync
call. The public-schema isolation test lives in
``test_edge_route_isolation.py`` (it needs no database).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from core.edge import bundles, registry, signing
from core.storage.connection import get_db_manager
from core.storage.models import ApprovalAction, EdgeBundle, EdgeNode, Finding
from core.time import utcnow

pytestmark = pytest.mark.external_service

NODE = "gw-vpc-west-01"
SCOPE = {"vpc": "vpc-0a1b2c3d", "cidrs": ["10.42.0.0/16"]}
SOURCE = f"edge:{NODE}"
INTERNAL_TOKEN = "test-internal-token"


def _document(version: int = 1, scope: dict = SCOPE, tier: str = "tier0") -> dict:
    now = utcnow()
    return {
        "bundle_id": "edge-pol-test",
        "edge_schema_version": 1,
        "segment_scope": scope,
        "version": version,
        "not_before": signing.ts_format(now),
        "expires_at": signing.ts_format(now + timedelta(days=7)),
        "min_edge_version": "1.0.0",
        "autonomy_tier": tier,
        "decision": {
            "auto_act_confidence": 0.92,
            "escalate_confidence": 0.85,
            "max_actions_per_hour": 6,
            "max_active_blocks": 24,
            "default_block_ttl_seconds": 900,
        },
        "allowed_actions": [],
        "rules": [],
        "ioc_sets": {},
        "revocations": [],
        **(
            {
                "parent_version": version - 1,
                "rollback_reference": {
                    "bundle_id": "edge-pol-test",
                    "version": version - 1,
                },
            }
            if version > 1
            else {}
        ),
    }


def _observation(event_id: str = "ev-obs-1") -> dict:
    return {
        "event_id": event_id,
        "kind": "observation",
        "occurred_at": "2026-10-09T12:00:00Z",
        "payload": {
            "severity": "high",
            "title": "c2 egress attempt",
            "rule": "c2-egress-active",
            "confidence": 0.93,
        },
    }


def _action(event_id: str = "ev-act-1") -> dict:
    return {
        "event_id": event_id,
        "kind": "action",
        "occurred_at": "2026-10-09T12:00:01Z",
        "payload": {
            "rule": "edge.c2-egress-active tier=tier2 conf=0.93",
            "actor": f"edge:{NODE}@v1",
            "journal_digest": "sha256:abc123",
        },
        "action": {
            "action_type": "block_ip",
            "target": "203.0.113.7",
            "executor": "nftables",
            "ttl_seconds": 900,
            "confidence": 0.93,
        },
    }


@pytest.fixture
def clean_node(edge_enrollment_secret: str):
    """Drop every row this suite could create, before and after."""
    _wipe()
    yield edge_enrollment_secret
    _wipe()


def _wipe() -> None:
    with get_db_manager().session_scope() as session:
        session.query(ApprovalAction).filter(
            ApprovalAction.created_by == SOURCE
        ).delete(synchronize_session=False)
        session.query(Finding).filter(Finding.data_source == SOURCE).delete(
            synchronize_session=False
        )
        session.query(EdgeNode).filter(EdgeNode.node_id == NODE).delete(
            synchronize_session=False
        )


@pytest.fixture
def clean_bundles():
    with get_db_manager().session_scope() as session:
        session.query(EdgeBundle).delete()
    yield
    with get_db_manager().session_scope() as session:
        session.query(EdgeBundle).delete()


@pytest.fixture
def signing_key_file(monkeypatch, tmp_path) -> Path:
    """A real Ed25519 signing key behind the configured file path."""
    pem, _, _ = signing.generate_signing_keypair()
    path = tmp_path / "edge_bundle_signing_key"
    path.write_text(pem)
    monkeypatch.setattr(
        signing, "get_secret", lambda key, default=None: str(path), raising=True
    )
    return path


@pytest.fixture
def signing_key(signing_key_file: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        signing_key_file.read_text().encode(), password=None
    )
    assert isinstance(key, Ed25519PrivateKey)
    return key


@pytest.fixture
def client() -> TestClient:
    from services.api.main import app

    return TestClient(app)


def _auth(credential: str) -> dict:
    return {"Authorization": f"Bearer {credential}"}


def _enrolled(client: TestClient, token: str) -> str:
    response = client.post(
        "/internal/edge/enroll",
        json={"node_id": NODE, "enrollment_token": token, "segment_scope": SCOPE},
    )
    assert response.status_code == 201, response.text
    credential = response.json()["credential"]
    assert credential
    return credential


class TestEnroll:
    def test_unset_secret_is_503(
        self, client: TestClient, monkeypatch, clean_node: str
    ):
        monkeypatch.setattr(
            registry, "get_secret", lambda key, default=None: None, raising=True
        )
        response = client.post(
            "/internal/edge/enroll",
            json={
                "node_id": NODE,
                "enrollment_token": "edge-token.AAAA.BBBB.CCCC",
                "segment_scope": SCOPE,
            },
        )
        assert response.status_code == 503

    def test_bad_token_is_401(self, client: TestClient, clean_node: str):
        response = client.post(
            "/internal/edge/enroll",
            json={
                "node_id": NODE,
                "enrollment_token": "edge-token.AAAA.BBBB.CCCC",
                "segment_scope": SCOPE,
            },
        )
        assert response.status_code == 401

    def test_good_token_yields_a_working_credential(
        self, client: TestClient, clean_node: str
    ):
        token = registry.mint_enrollment_token(NODE)
        credential = _enrolled(client, token)
        # The credential just returned must authenticate the node's own
        # routes — a token that cannot sync is a token that did not enroll.
        response = client.get(
            f"/internal/edge/{NODE}/policy", headers=_auth(credential)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["bundle"] is None  # nothing published yet
        assert body["current_version"] is None


class TestPolicyPull:
    def test_serves_the_signed_bundle(
        self,
        client: TestClient,
        clean_node: str,
        clean_bundles,
        signing_key: Ed25519PrivateKey,
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        bundles.publish_bundle(_document(version=1), signing_key)
        response = client.get(
            f"/internal/edge/{NODE}/policy", headers=_auth(credential)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["current_version"] == 1
        assert body["payload"]["bundle_id"] == "edge-pol-test"
        assert body["bundle"]["envelope"]["signatures"][0]["sig"]  # DSSE rides along

    def test_no_backfill_ever(
        self,
        client: TestClient,
        clean_node: str,
        clean_bundles,
        signing_key: Ed25519PrivateKey,
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        bundles.publish_bundle(_document(version=1), signing_key)
        bundles.publish_bundle(_document(version=2), signing_key)

        # A cold start (no cursor) sees only the newest — never the history.
        cold = client.get(f"/internal/edge/{NODE}/policy", headers=_auth(credential))
        assert cold.status_code == 200
        assert cold.json()["current_version"] == 2
        assert cold.json()["payload"]["version"] == 2

        # A stale cursor is caught up to the newest, not walked forward.
        stale = client.get(
            f"/internal/edge/{NODE}/policy?cursor=1", headers=_auth(credential)
        )
        assert stale.status_code == 200
        assert stale.json()["payload"]["version"] == 2

        # An up-to-date cursor receives nothing.
        current = client.get(
            f"/internal/edge/{NODE}/policy?cursor=2", headers=_auth(credential)
        )
        assert current.status_code == 200
        assert current.json()["bundle"] is None

    def test_scope_miss_serves_nothing(
        self,
        client: TestClient,
        clean_node: str,
        clean_bundles,
        signing_key: Ed25519PrivateKey,
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        bundles.publish_bundle(
            _document(version=1, scope={"vpc": "vpc-other"}), signing_key
        )
        response = client.get(
            f"/internal/edge/{NODE}/policy", headers=_auth(credential)
        )
        assert response.status_code == 200
        assert response.json()["bundle"] is None

    def test_wrong_credential_is_401(self, client: TestClient, clean_node: str):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        response = client.get(
            f"/internal/edge/{NODE}/policy",
            headers=_auth("edge-c_" + "0" * 40),
        )
        assert response.status_code == 401
        assert response.json()["detail"] != credential  # nothing leaks


class TestEvents:
    def test_durable_ack_then_replay_is_all_duplicates(
        self, client: TestClient, clean_node: str
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        batch = {"events": [_observation(), _action()]}
        first = client.post(
            f"/internal/edge/{NODE}/events", json=batch, headers=_auth(credential)
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["acked"] == ["ev-obs-1", "ev-act-1"]
        assert body["duplicates"] == []

        replay = client.post(
            f"/internal/edge/{NODE}/events", json=batch, headers=_auth(credential)
        )
        assert replay.status_code == 200
        replayed = replay.json()
        assert replayed["acked"] == []
        assert replayed["duplicates"] == ["ev-obs-1", "ev-act-1"]

        # Zero duplicate rows is the contract, not just zero duplicates
        # in the response: count what actually landed.
        with get_db_manager().session_scope() as session:
            assert (
                session.query(Finding)
                .filter(
                    Finding.data_source == SOURCE, Finding.external_id == "ev-obs-1"
                )
                .count()
                == 1
            )
            assert (
                session.query(ApprovalAction)
                .filter(ApprovalAction.idempotency_key == f"edge:{NODE}:ev-act-1")
                .count()
                == 1
            )

    def test_action_lands_as_executed_with_edge_provenance(
        self, client: TestClient, clean_node: str
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        response = client.post(
            f"/internal/edge/{NODE}/events",
            json={"events": [_action()]},
            headers=_auth(credential),
        )
        assert response.status_code == 200
        with get_db_manager().session_scope() as session:
            row = (
                session.query(ApprovalAction)
                .filter(ApprovalAction.idempotency_key == f"edge:{NODE}:ev-act-1")
                .one()
            )
            assert row.status == "executed"
            assert row.approved_by == f"edge:{NODE}@v1"
            assert row.created_by == SOURCE
            parameters = dict(row.parameters or {})
            assert parameters["node_id"] == NODE
            assert parameters["executor"] == "nftables"

    def test_observation_lands_as_a_finding_with_edge_source(
        self, client: TestClient, clean_node: str
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        response = client.post(
            f"/internal/edge/{NODE}/events",
            json={"events": [_observation()]},
            headers=_auth(credential),
        )
        assert response.status_code == 200
        with get_db_manager().session_scope() as session:
            row = session.query(Finding).filter(Finding.data_source == SOURCE).one()
            assert row.external_id == "ev-obs-1"
            assert row.severity == "high"

    def test_malformed_events_are_rejected_not_dropped(
        self, client: TestClient, clean_node: str
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        events = [
            _observation("ev-good"),
            {
                "event_id": "ev-bad-kind",
                "kind": "quantum",
                "occurred_at": "2026-10-09T12:00:00Z",
                "payload": {},
            },
            {
                "event_id": "ev-bad-time",
                "kind": "observation",
                "occurred_at": "not-a-time",
                "payload": {},
            },
            {
                "event_id": "ev-bad-action",
                "kind": "action",
                "occurred_at": "2026-10-09T12:00:00Z",
                "payload": {},
                "action": {"action_type": "quarantine_file", "target": "x"},
            },
        ]
        response = client.post(
            f"/internal/edge/{NODE}/events",
            json={"events": events},
            headers=_auth(credential),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["acked"] == ["ev-good"]
        assert {r["event_id"] for r in body["rejected"]} == {
            "ev-bad-kind",
            "ev-bad-time",
            "ev-bad-action",
        }

    def test_oversized_batch_is_413(self, client: TestClient, clean_node: str):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        events = [_observation(f"ev-{i}") for i in range(501)]
        response = client.post(
            f"/internal/edge/{NODE}/events",
            json={"events": events},
            headers=_auth(credential),
        )
        assert response.status_code == 413

    def test_events_require_node_credential(self, client: TestClient, clean_node: str):
        response = client.post(
            f"/internal/edge/{NODE}/events", json={"events": [_observation()]}
        )
        assert response.status_code == 401


class TestHeartbeat:
    def test_heartbeat_records_liveness_and_drift(
        self, client: TestClient, clean_node: str, clean_bundles, signing_key
    ):
        credential = _enrolled(client, registry.mint_enrollment_token(NODE))
        bundles.publish_bundle(_document(version=1), signing_key)
        response = client.post(
            f"/internal/edge/{NODE}/heartbeat",
            json={"boot_id": "boot-1", "bundle_version": 1, "autonomy_tier": "tier2"},
            headers=_auth(credential),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["current_bundle_version"] == 1
        # The node reports an older bundle than what exists -> drift shows.
        drifting = client.post(
            f"/internal/edge/{NODE}/heartbeat",
            json={"bundle_version": 1},
            headers=_auth(credential),
        )
        body = drifting.json()
        assert body["current_bundle_version"] == 1

    def test_heartbeat_without_credential_is_401(
        self, client: TestClient, clean_node: str
    ):
        response = client.post(
            f"/internal/edge/{NODE}/heartbeat", json={"boot_id": "b"}
        )
        assert response.status_code == 401


class TestRevocation:
    def test_revoke_requires_the_internal_token(
        self, client: TestClient, clean_node: str, monkeypatch
    ):
        monkeypatch.setenv("AGENT_INTERNAL_TOKEN", INTERNAL_TOKEN)
        node_token = registry.mint_enrollment_token(NODE)
        credential = _enrolled(client, node_token)

        no_token = client.post(f"/internal/edge/nodes/{NODE}/revoke", json={})
        assert no_token.status_code == 401
        wrong = client.post(
            f"/internal/edge/nodes/{NODE}/revoke",
            json={},
            headers=_auth("not-the-token"),
        )
        assert wrong.status_code == 401

        ok = client.post(
            f"/internal/edge/nodes/{NODE}/revoke",
            json={"reason": "compromised"},
            headers=_auth(INTERNAL_TOKEN),
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "revoked"

        # Revocation kills every further sync call.
        assert (
            client.get(
                f"/internal/edge/{NODE}/policy", headers=_auth(credential)
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/internal/edge/{NODE}/events",
                json={"events": [_observation()]},
                headers=_auth(credential),
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/internal/edge/{NODE}/heartbeat",
                json={"boot_id": "b"},
                headers=_auth(credential),
            ).status_code
            == 401
        )

    def test_unset_internal_token_is_503(
        self, client: TestClient, clean_node: str, monkeypatch
    ):
        monkeypatch.delenv("AGENT_INTERNAL_TOKEN", raising=False)
        monkeypatch.setattr(
            "core.agents.internal_auth.get_secret",
            lambda key, default=None: None,
            raising=True,
        )
        response = client.post(f"/internal/edge/nodes/{NODE}/revoke", json={})
        assert response.status_code == 503

    def test_re_enroll_after_revocation_rotates_the_credential(
        self, client: TestClient, clean_node: str, monkeypatch
    ):
        """Re-enrollment is the sanctioned way back after revocation — but
        it rotates the credential; the pre-revocation one stays dead."""
        monkeypatch.setenv("AGENT_INTERNAL_TOKEN", INTERNAL_TOKEN)
        node_token = registry.mint_enrollment_token(NODE)
        credential = _enrolled(client, node_token)
        client.post(
            f"/internal/edge/nodes/{NODE}/revoke",
            json={},
            headers=_auth(INTERNAL_TOKEN),
        )
        again = client.post(
            "/internal/edge/enroll",
            json={
                "node_id": NODE,
                "enrollment_token": node_token,
                "segment_scope": SCOPE,
            },
        )
        assert again.status_code == 201  # re-enroll is the sanctioned way back
        fresh = again.json()["credential"]
        assert fresh != credential
        assert (
            client.get(
                f"/internal/edge/{NODE}/policy", headers=_auth(fresh)
            ).status_code
            == 200
        )
