"""Edge node registry lifecycle tests.

Covers the spec's control-plane acceptance criteria that live in the
registry layer: enrollment fails closed when the signing secret is missing
(503 territory), tokens minted for one node are worthless for another,
wrong credentials read the same as unknown nodes (401 territory),
heartbeats record liveness and cursor, and revocation kills every further
authenticated call.
"""

import pytest

from core.edge import registry
from core.storage.connection import get_db_manager
from core.storage.models import EdgeNode

pytestmark = pytest.mark.external_service

NODE = "gw-vpc-west-01"
SCOPE = {"vpc": "vpc-0a1b2c3d", "cidrs": ["10.42.0.0/16"]}


def _enrolled_node(secret: str, node_id: str = NODE) -> str:
    token = registry.mint_enrollment_token(node_id)
    return registry.enroll(node_id, SCOPE, token)


@pytest.fixture
def clean_node(edge_enrollment_secret: str):
    """Drop any registry state for the test node, then yield."""
    with get_db_manager().session_scope() as session:
        session.query(EdgeNode).filter(EdgeNode.node_id == NODE).delete()
    yield edge_enrollment_secret
    with get_db_manager().session_scope() as session:
        session.query(EdgeNode).filter(EdgeNode.node_id == NODE).delete()


class TestEnrollment:
    def test_enroll_stores_hash_never_plaintext(self, clean_node: str):
        credential = _enrolled_node(clean_node)
        assert credential  # shown once
        with get_db_manager().session_scope() as session:
            row = session.get(EdgeNode, NODE)
            assert row is not None
            assert row.credential_hash != credential
            assert len(row.credential_hash) == 64
            assert row.status == "active"
            assert dict(row.segment_scope)["vpc"] == "vpc-0a1b2c3d"

    def test_re_enroll_rotates_the_credential(self, clean_node: str):
        first = _enrolled_node(clean_node)
        second = _enrolled_node(clean_node)
        assert first != second
        # The first credential no longer authenticates.
        with pytest.raises(registry.AuthenticationFailed):
            registry.authenticate_node(NODE, first)
        row = registry.authenticate_node(NODE, second)
        assert row.node_id == NODE


class TestFailClosed:
    def test_missing_secret_blocks_minting(self, monkeypatch):
        monkeypatch.setattr(registry, "get_secret", lambda key, default=None: None)
        with pytest.raises(registry.EnrollmentSecretMissing):
            registry.mint_enrollment_token(NODE)

    def test_missing_secret_blocks_verification(self, monkeypatch, clean_node: str):
        token = registry.mint_enrollment_token(NODE)
        monkeypatch.setattr(registry, "get_secret", lambda key, default=None: None)
        with pytest.raises(registry.EnrollmentSecretMissing):
            registry.enroll(NODE, SCOPE, token)

    def test_token_for_another_node_is_rejected(self, clean_node: str):
        token = registry.mint_enrollment_token("gw-other")
        with pytest.raises(registry.EnrollmentTokenInvalid):
            registry.enroll(NODE, SCOPE, token)

    def test_forged_token_signature_is_rejected(self, clean_node: str):
        token = registry.mint_enrollment_token(NODE)
        forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        with pytest.raises(registry.EnrollmentTokenInvalid):
            registry.enroll(NODE, SCOPE, forged)

    def test_expired_token_is_rejected(self, clean_node: str):
        from datetime import timedelta

        token = registry.mint_enrollment_token(NODE, ttl=timedelta(seconds=-1))
        with pytest.raises(registry.EnrollmentTokenInvalid, match="expired"):
            registry.enroll(NODE, SCOPE, token)


class TestAuthentication:
    def test_good_credential_authenticates(self, clean_node: str):
        credential = _enrolled_node(clean_node)
        row = registry.authenticate_node(NODE, credential)
        assert row.node_id == NODE

    def test_unknown_node_is_not_enrolled(self, clean_node: str):
        with pytest.raises(registry.NodeNotEnrolled):
            registry.authenticate_node("gw-ghost", "whatever")

    def test_wrong_credential_fails(self, clean_node: str):
        _enrolled_node(clean_node)
        with pytest.raises(registry.AuthenticationFailed):
            registry.authenticate_node(NODE, "wrong-credential")

    def test_missing_credential_fails(self, clean_node: str):
        _enrolled_node(clean_node)
        with pytest.raises(registry.AuthenticationFailed):
            registry.authenticate_node(NODE, None)

    def test_invalid_node_id_never_reaches_the_db(self, clean_node: str):
        with pytest.raises(registry.NodeNotEnrolled):
            registry.authenticate_node("../etc/passwd", "x")


class TestHeartbeat:
    def test_heartbeat_updates_liveness_and_cursor(self, clean_node: str):
        _enrolled_node(clean_node)
        report = registry.record_heartbeat(
            NODE, boot_id="boot-1", bundle_version=3, autonomy_tier="tier2"
        )
        assert report["ok"] is True
        with get_db_manager().session_scope() as session:
            row = session.get(EdgeNode, NODE)
            assert row.last_seen is not None
            assert row.last_boot_id == "boot-1"
            assert row.last_bundle_version == 3

    def test_heartbeat_reports_newer_bundle_version(self, clean_node: str):
        from core.storage.models import EdgeBundle

        _enrolled_node(clean_node)
        with get_db_manager().session_scope() as session:
            session.add(
                EdgeBundle(
                    bundle_id="edge-pol-x",
                    version=5,
                    segment_scope=SCOPE,
                    autonomy_tier="tier2",
                    envelope={},
                    payload={},
                    signed_by="test",
                )
            )
        report = registry.record_heartbeat(NODE, bundle_version=4)
        assert report["current_bundle_version"] == 5  # drift signal


class TestRevocation:
    def test_revoked_node_cannot_authenticate_or_heartbeat(self, clean_node: str):
        credential = _enrolled_node(clean_node)
        result = registry.revoke_node(NODE, "analyst", "compromised gateway")
        assert result["status"] == "revoked"
        with pytest.raises(registry.AuthenticationFailed):
            registry.authenticate_node(NODE, credential)
        with pytest.raises(registry.AuthenticationFailed):
            registry.record_heartbeat(NODE)

    def test_revocation_is_idempotent(self, clean_node: str):
        _enrolled_node(clean_node)
        first = registry.revoke_node(NODE, "analyst", "reason")
        second = registry.revoke_node(NODE, "analyst", "reason")
        assert first["revoked_at"] == second["revoked_at"]

    def test_revocation_records_who_and_why(self, clean_node: str):
        _enrolled_node(clean_node)
        registry.revoke_node(NODE, "analyst@ops", "stale node")
        with get_db_manager().session_scope() as session:
            row = session.get(EdgeNode, NODE)
            assert row.status == "revoked"
            assert row.revoked_by == "analyst@ops"
            assert row.revoke_reason == "stale node"
            assert row.revoked_at is not None
