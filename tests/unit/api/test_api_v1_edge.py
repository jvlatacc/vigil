"""POST /api/v1/edge — enrollment, node management, policy fetch, reconcile.

The router plumbing: fail-closed auth postures (503 unset enrollment secret,
401 unknown node token, 403 revoked node), the enrollment/revoke lifecycle,
and reconcile's merge/dedup/gap/legality behavior — all without a database
(session operations run against fakes; the DB-backed pass is
``test_api_v1_edge_db.py``). Mounted-route tests run against the real app so
the postures are exercised exactly as wired.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Importing services.api.* (lazily, in tests) pulls auth_service, which refuses
# to load without a JWT secret once DEV_MODE is false — set these first.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-prod")
os.environ.setdefault("DEV_MODE", "true")

pytestmark = pytest.mark.unit

TS = "2026-10-09T13:00:00Z"
SECRET = "enroll-secret-for-tests"
NODE = "wn-7f3a"
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edge():
    import services.api.routers.edge as edge

    return edge


def _fake_node(**kwargs) -> SimpleNamespace:
    defaults = dict(
        node_id=NODE,
        segment_labels=["segment:dmz"],
        status="active",
        last_seen=None,
        enrolled_at=NOW,
        enrolled_by="enrollment-token",
        revoked_at=None,
        revoked_by=None,
        revocation_reason=None,
        token_hash="f" * 64,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_session(node_row=None) -> MagicMock:
    """A session whose query chains answer from ``node_row`` if given."""
    session = MagicMock(name="session")
    filtered = session.query.return_value.filter.return_value
    filtered.first.return_value = node_row
    filtered.order_by.return_value.first.return_value = None
    session.get.return_value = None
    return session


def _chained_records(
    *seqs: int, action_type: str = "block_ip", prev: str | None = None
):
    """A valid journal batch from genesis (or ``prev``); returns (records, head)."""
    from core.edge.journal import record_hash

    records: list[dict] = []
    head = prev if prev is not None else "0" * 64
    for seq in seqs:
        record = {
            "seq": seq,
            "ts": TS,
            "mode": "AUTONOMOUS",
            "idempotency_key": f"{action_type}:198.51.100.{seq}",
            "action_type": action_type,
            "target": "198.51.100.7",
            "decision_rule": "edge-001 met (slm 0.93 >= floor 0.90)",
            "execution": {"status": "executed", "executor": "nftables", "at": TS},
            "prev_hash": head,
        }
        head = record_hash(head, record)
        records.append(record)
    return records, head


def _push(
    records: list[dict], head: str, *, policy_version: int = 42, node_id: str = NODE
):
    """A real JournalPush (pydantic) built from chained record dicts."""
    edge = _edge()

    return edge.JournalPush(
        node_id=node_id,
        policy_version=policy_version,
        chain_head=head,
        records=[edge.JournalRecord(**record) for record in records],
    )


def _policy_row(allowed=("block_ip", "unblock_ip"), status="active") -> SimpleNamespace:
    payload = json.dumps(
        {"autonomy_envelope": {"allowed_actions": list(allowed)}}
    ).encode()
    payload_b64 = base64.b64encode(payload).decode()
    return SimpleNamespace(
        status=status,
        envelope={"payload": payload_b64},
        payload_hash=hashlib.sha256(payload).hexdigest(),
        policy_version=42,
    )


def _freeze_edge_clock(monkeypatch) -> None:
    """Pin the enrollment dependency's clock at NOW."""
    edge = _edge()
    monkeypatch.setattr(edge, "datetime", SimpleNamespace(now=lambda tz: NOW))


@pytest.fixture()
def no_enrollment_secret(monkeypatch):
    monkeypatch.setattr(_edge(), "get_secret", lambda name: None)


@pytest.fixture()
def with_enrollment_secret(monkeypatch):
    monkeypatch.setattr(_edge(), "get_secret", lambda name: SECRET)


@pytest.fixture()
def client():
    """The real app with the DB session swapped for a fake."""
    from fastapi.testclient import TestClient

    from core.routing import request_unit_of_work
    from services.api.main import app

    def _get_session():
        yield _fake_session()

    app.dependency_overrides[request_unit_of_work] = _get_session
    yield TestClient(app)
    app.dependency_overrides.pop(request_unit_of_work, None)


# ---------------------------------------------------------------------------
# Enrollment auth posture (fail-closed)
# ---------------------------------------------------------------------------


class TestEnrollmentAuth:
    def test_unset_secret_is_503_before_anything_else(self, no_enrollment_secret):
        edge = _edge()

        with pytest.raises(edge.HTTPException) as err:
            edge.require_enrollment_token(authorization=None)
        assert err.value.status_code == 503

    def test_missing_header_is_401_when_configured(self, with_enrollment_secret):
        edge = _edge()

        with pytest.raises(edge.HTTPException) as err:
            edge.require_enrollment_token(authorization=None)
        assert err.value.status_code == 401

    def test_expired_token_is_401_naming_the_class(
        self, with_enrollment_secret, monkeypatch
    ):
        edge = _edge()
        from core.edge.enrollment import mint_enrollment_token

        _freeze_edge_clock(monkeypatch)
        token = mint_enrollment_token(
            NODE, secret=SECRET, expires_at=NOW - timedelta(seconds=1)
        )

        with pytest.raises(edge.HTTPException) as err:
            edge.require_enrollment_token(authorization=f"Bearer {token}")
        assert err.value.status_code == 401
        assert "expired" in err.value.detail

    def test_valid_token_returns_its_node_id(self, with_enrollment_secret, monkeypatch):
        edge = _edge()
        from core.edge.enrollment import mint_enrollment_token

        _freeze_edge_clock(monkeypatch)
        token = mint_enrollment_token(
            NODE, secret=SECRET, expires_at=NOW + timedelta(hours=1)
        )

        assert edge.require_enrollment_token(authorization=f"Bearer {token}") == NODE


class TestEdgeNodeAuth:
    def test_unknown_token_is_401(self):
        edge = _edge()
        session = _fake_session(node_row=None)

        with pytest.raises(edge.HTTPException) as err:
            edge.require_edge_node(session, authorization="Bearer nope")
        assert err.value.status_code == 401

    def test_revoked_node_is_403(self):
        edge = _edge()
        session = _fake_session(node_row=_fake_node(status="revoked"))

        with pytest.raises(edge.HTTPException) as err:
            edge.require_edge_node(session, authorization="Bearer dead-token")
        assert err.value.status_code == 403

    def test_active_node_is_returned_with_fresh_last_seen(self):
        edge = _edge()
        node = _fake_node()
        assert node.last_seen is None
        session = _fake_session(node_row=node)

        resolved = edge.require_edge_node(session, authorization="Bearer live-token")

        assert resolved is node
        assert resolved.last_seen is not None  # the heartbeat

    def test_missing_header_is_401(self):
        edge = _edge()
        session = _fake_session()

        with pytest.raises(edge.HTTPException) as err:
            edge.require_edge_node(session, authorization=None)
        assert err.value.status_code == 401


# ---------------------------------------------------------------------------
# Enrollment / node lifecycle
# ---------------------------------------------------------------------------


class TestEnrollNode:
    def test_new_node_returns_a_token_and_stores_only_its_hash(self):
        edge = _edge()
        session = _fake_session(node_row=None)  # session.get -> None

        response = edge._enroll_node(
            session, node_id=NODE, segment_labels=["segment:dmz"]
        )

        assert response.node_id == NODE
        assert response.token  # the node's credential, returned once
        added = session.add.call_args[0][0]
        assert added.node_id == NODE
        assert added.token_hash == hashlib.sha256(response.token.encode()).hexdigest()
        assert added.token_hash != response.token
        assert added.status == "active"
        assert added.segment_labels == ["segment:dmz"]

    def test_existing_node_is_409_even_when_revoked(self):
        edge = _edge()
        session = _fake_session()
        session.get.return_value = _fake_node(status="revoked")

        with pytest.raises(edge.HTTPException) as err:
            edge._enroll_node(session, node_id=NODE, segment_labels=[])
        assert err.value.status_code == 409

    def test_invalid_node_id_is_400(self):
        edge = _edge()
        session = _fake_session()

        with pytest.raises(edge.HTTPException) as err:
            edge._enroll_node(session, node_id="../etc", segment_labels=[])
        assert err.value.status_code == 400


class TestRevokeNode:
    def test_unknown_node_is_404(self):
        edge = _edge()
        session = _fake_session()
        session.get.return_value = None

        with pytest.raises(edge.HTTPException) as err:
            edge._revoke_node(session, node_id="ghost", reason="", revoked_by="op")
        assert err.value.status_code == 404

    def test_revocation_writes_the_audit_fields(self):
        edge = _edge()
        node = _fake_node()
        session = _fake_session()
        session.get.return_value = node

        response = edge._revoke_node(
            session, node_id=NODE, reason="stolen laptop", revoked_by="jvl"
        )

        assert response.status == "revoked"
        assert node.status == "revoked"
        assert node.revoked_by == "jvl"
        assert node.revocation_reason == "stolen laptop"
        assert node.revoked_at is not None

    def test_revocation_is_idempotent(self):
        edge = _edge()
        node = _fake_node(
            status="revoked",
            revoked_at=NOW,
            revoked_by="first-op",
            revocation_reason="first reason",
        )
        session = _fake_session()
        session.get.return_value = node

        response = edge._revoke_node(
            session, node_id=NODE, reason="second reason", revoked_by="second-op"
        )

        # the first revocation's audit trail stands
        assert response.revoked_by == "first-op"
        assert response.revocation_reason == "first reason"


# ---------------------------------------------------------------------------
# Policy fetch
# ---------------------------------------------------------------------------


class TestAllowedActions:
    def test_unknown_version_is_none(self):
        edge = _edge()
        assert edge._allowed_actions(None) is None

    def test_non_active_row_is_none(self):
        edge = _edge()
        assert edge._allowed_actions(_policy_row(status="revoked")) is None

    def test_tampered_payload_is_an_integrity_error(self):
        edge = _edge()
        policy = _policy_row()
        policy.payload_hash = "0" * 64  # payload edited after activation

        with pytest.raises(edge.EdgePolicyIntegrityError):
            edge._allowed_actions(policy)

    def test_allowlist_is_read_from_the_signed_payload(self):
        edge = _edge()
        assert edge._allowed_actions(_policy_row(allowed=("block_ip",))) == (
            "block_ip",
        )


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_first_push_merges_rows_with_edge_provenance(self):
        edge = _edge()
        records, head = _chained_records(1, 2)
        session = _fake_session()
        session.get.return_value = _policy_row()  # cited policy version exists
        node = _fake_node()

        response = edge._reconcile(session, node=node, push=_push(records, head))

        assert response.accepted_through == 2
        assert response.merged_count == 2
        assert response.duplicate_ids == []
        assert response.rejected == []
        added = [call.args[0] for call in session.add.call_args_list]
        approval_rows = [a for a in added if type(a).__name__ == "ApprovalAction"]
        assert len(approval_rows) == 2
        for row in approval_rows:
            assert row.parameters["source"] == "edge"
            assert row.parameters["node_id"] == NODE
            assert row.parameters["policy_version"] == 42
            assert row.created_by == f"edge:{NODE}"
            assert row.status == "executed"
        receipt = [a for a in added if type(a).__name__ == "EdgeJournalReceipt"][0]
        assert (receipt.first_seq, receipt.last_seq) == (1, 2)
        assert receipt.chain_head == head

    def test_repushed_records_dedupe_by_idempotency_key(self):
        edge = _edge()
        records, head = _chained_records(1)
        session = _fake_session()
        session.get.return_value = _policy_row()
        session.query.return_value.filter.return_value.first.return_value = (
            SimpleNamespace(idempotency_key=records[0]["idempotency_key"])
        )
        node = _fake_node()

        response = edge._reconcile(session, node=node, push=_push(records, head))

        assert response.merged_count == 0
        assert response.duplicate_ids == [records[0]["idempotency_key"]]

    def test_chain_gap_refuses_with_resend_from_the_head(self):
        edge = _edge()
        _, held_head = _chained_records(1, 2)
        gapped, _ = _chained_records(4, prev=held_head)
        session = _fake_session()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(  # noqa: E501
            last_seq=2, chain_head=held_head, receipt_id="ejr-1"
        )
        node = _fake_node()

        response = edge._reconcile(session, node=node, push=_push(gapped, "f" * 64))

        assert isinstance(response, edge.ChainGapResponse)
        assert response.reason == "seq-gap"
        assert response.server_last_seq == 2
        assert response.server_head == held_head
        assert response.resend_from == 3

    def test_illegal_records_are_rejected_but_the_watermark_advances(self):
        # Chain holds, but the cited envelope never allowed the action: the
        # merge must not launder it, and the receipt still advances so the
        # node does not re-push the refused records forever.
        edge = _edge()
        records, head = _chained_records(1, 2, action_type="process_kill")
        session = _fake_session()
        session.get.return_value = _policy_row(allowed=("block_ip",))
        node = _fake_node()

        response = edge._reconcile(session, node=node, push=_push(records, head))

        assert isinstance(response, edge.JournalResponse)
        assert response.merged_count == 0
        assert [r.seq for r in response.rejected] == [1, 2]
        assert all(r.code == "action-not-in-envelope" for r in response.rejected)
        assert response.accepted_through == 2
        added = [call.args[0] for call in session.add.call_args_list]
        assert [type(a).__name__ for a in added] == ["EdgeJournalReceipt"]

    def test_unknown_cited_version_rejects_every_record(self):
        edge = _edge()
        records, head = _chained_records(1)
        session = _fake_session()
        session.get.return_value = None  # policy version never existed
        node = _fake_node()

        response = edge._reconcile(
            session, node=node, push=_push(records, head, policy_version=99)
        )

        assert isinstance(response, edge.JournalResponse)
        assert response.merged_count == 0
        assert [r.code for r in response.rejected] == ["policy-version-unavailable"]

    def test_journal_node_id_mismatch_is_403(self):
        # A node must not reconcile under another node's identity.
        edge = _edge()
        node = _fake_node(node_id="wn-other")
        records, head = _chained_records(1)

        with pytest.raises(edge.HTTPException) as err:
            edge.reconcile_journal(
                body=_push(records, head),
                session=_fake_session(),
                node=node,
            )
        assert err.value.status_code == 403


# ---------------------------------------------------------------------------
# Mounted-route behavior (TestClient against the real app)
# ---------------------------------------------------------------------------


class TestMountedRoutes:
    def test_enroll_refuses_when_unconfigured(self, client, no_enrollment_secret):
        resp = client.post("/api/v1/edge/enroll", json={"segment_labels": []})
        assert resp.status_code == 503

    def test_enroll_refuses_an_unauthenticated_call(
        self, client, with_enrollment_secret
    ):
        resp = client.post("/api/v1/edge/enroll", json={"segment_labels": []})
        assert resp.status_code == 401

    def test_enroll_succeeds_with_a_valid_token(
        self, client, with_enrollment_secret, monkeypatch
    ):
        edge = _edge()
        from core.edge.enrollment import mint_enrollment_token

        _freeze_edge_clock(monkeypatch)

        def fake_enroll(session, *, node_id, segment_labels):
            return edge.EnrollResponse(node_id=node_id, token="node-token-xyz")

        monkeypatch.setattr(edge, "_enroll_node", fake_enroll)
        token = mint_enrollment_token(
            NODE, secret=SECRET, expires_at=NOW + timedelta(hours=1)
        )

        resp = client.post(
            "/api/v1/edge/enroll",
            json={"segment_labels": ["segment:dmz"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"node_id": NODE, "token": "node-token-xyz"}

    def test_policy_refuses_an_unauthenticated_node(self, client):
        resp = client.get("/api/v1/edge/policy")
        assert resp.status_code == 401

    def test_journal_refuses_an_unauthenticated_node(self, client):
        resp = client.post(
            "/api/v1/edge/journal",
            json={
                "node_id": NODE,
                "policy_version": 1,
                "chain_head": "0" * 64,
                "records": [],
            },
        )
        assert resp.status_code == 401
