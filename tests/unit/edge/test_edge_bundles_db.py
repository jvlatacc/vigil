"""Bundle publish/store/serve tests (DB-backed).

Covers: publish stores a verifiable immutable row; the sign-time lint
refuses invalid documents before anything is signed; (bundle_id, version)
conflicts are refused; scope matching picks the newest matching bundle for
a node; and a stored envelope that stops verifying (or disagrees with its
payload column) is never served.
"""

import base64
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.edge import bundles, signing
from core.storage.connection import get_db_manager
from core.storage.models import EdgeBundle
from core.time import utcnow

pytestmark = pytest.mark.external_service

SCOPE = {"vpc": "vpc-0a1b2c3d", "cidrs": ["10.42.0.0/16"]}
OTHER_SCOPE = {"vpc": "vpc-9999zzzz", "cidrs": ["10.99.0.0/16"]}


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


def _key() -> Ed25519PrivateKey:
    pem, _, _ = signing.generate_signing_keypair()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


def _trust_root_for(key: Ed25519PrivateKey) -> dict:
    public_b64 = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    now = utcnow()
    return signing.build_trust_root(
        public_b64, version=1, issued_at=now, expires_at=now + timedelta(days=365)
    )


@pytest.fixture
def signing_key():
    return _key()


@pytest.fixture
def clean_bundles():
    """Clear every edge bundle row before and after."""
    with get_db_manager().session_scope() as session:
        session.query(EdgeBundle).delete()
    yield
    with get_db_manager().session_scope() as session:
        session.query(EdgeBundle).delete()


class TestPublish:
    def test_publish_stores_a_verifiable_row(self, signing_key, clean_bundles):
        document = _document(version=3)
        row = bundles.publish_bundle(document, signing_key, signed_by="test")
        assert row.bundle_id == "edge-pol-test"
        assert row.version == 3
        assert row.autonomy_tier == "tier0"
        verified = bundles.verify_stored_bundle(row, _trust_root_for(signing_key))
        assert verified.payload["version"] == 3

    def test_publish_refuses_invalid_document(self, signing_key, clean_bundles):
        bad = _document()
        bad["autonomy_tier"] = "tier3"
        with pytest.raises(bundles.BundleDocumentInvalid):
            bundles.publish_bundle(bad, signing_key)
        assert bundles.count_bundles() == 0

    def test_publish_refuses_duplicate_version(self, signing_key, clean_bundles):
        bundles.publish_bundle(_document(version=1), signing_key)
        with pytest.raises(bundles.BundleConflict):
            bundles.publish_bundle(_document(version=1), signing_key)

    def test_published_envelope_verifies_like_a_daemon_would(
        self, signing_key, clean_bundles
    ):
        document = _document()
        row = bundles.publish_bundle(document, signing_key)
        verified = signing.verify_envelope(
            dict(row.envelope), _trust_root_for(signing_key)
        )
        assert verified.payload == document


class TestScopeMatching:
    def test_newest_matching_bundle_wins(self, signing_key, clean_bundles):
        bundles.publish_bundle(_document(version=1, scope=SCOPE), signing_key)
        bundles.publish_bundle(_document(version=2, scope=OTHER_SCOPE), signing_key)
        row = bundles.latest_bundle_for_node(SCOPE)
        assert row is not None
        assert row.version == 1
        other = bundles.latest_bundle_for_node(OTHER_SCOPE)
        assert other is not None
        assert other.version == 2

    def test_no_match_returns_none(self, signing_key, clean_bundles):
        bundles.publish_bundle(_document(version=1, scope=SCOPE), signing_key)
        assert bundles.latest_bundle_for_node(OTHER_SCOPE) is None

    def test_scope_comparison_is_canonical_not_dict_order(
        self, signing_key, clean_bundles
    ):
        bundles.publish_bundle(
            _document(
                version=1, scope={"cidrs": ["10.42.0.0/16"], "vpc": "vpc-0a1b2c3d"}
            ),
            signing_key,
        )
        row = bundles.latest_bundle_for_node(SCOPE)
        assert row is not None  # same document, different key order


class TestStoredTamperDetection:
    def test_corrupted_envelope_is_refused(self, signing_key, clean_bundles):
        row = bundles.publish_bundle(_document(), signing_key)
        root = _trust_root_for(signing_key)
        with get_db_manager().session_scope() as session:
            stored = session.get(EdgeBundle, (row.bundle_id, row.version))
            assert stored is not None
            envelope = dict(stored.envelope)
            raw = bytearray(base64.b64decode(envelope["payload"]))
            raw[0] ^= 0x01
            envelope["payload"] = base64.b64encode(bytes(raw)).decode()
            stored.envelope = envelope
        with get_db_manager().session_scope() as session:
            tampered = session.get(EdgeBundle, (row.bundle_id, row.version))
            assert tampered is not None
            session.expunge(tampered)
        with pytest.raises(bundles.StoredBundleTampered):
            bundles.verify_stored_bundle(tampered, root)

    def test_payload_envelope_mismatch_is_refused(self, signing_key, clean_bundles):
        row = bundles.publish_bundle(_document(), signing_key)
        root = _trust_root_for(signing_key)
        with get_db_manager().session_scope() as session:
            stored = session.get(EdgeBundle, (row.bundle_id, row.version))
            assert stored is not None
            payload = dict(stored.payload)
            payload["version"] = 99  # envelope no longer matches the document
            stored.payload = payload
        with get_db_manager().session_scope() as session:
            tampered = session.get(EdgeBundle, (row.bundle_id, row.version))
            assert tampered is not None
            session.expunge(tampered)
        with pytest.raises(bundles.StoredBundleTampered):
            bundles.verify_stored_bundle(tampered, root)

    def test_untampered_row_verifies(self, signing_key, clean_bundles):
        row = bundles.publish_bundle(_document(), signing_key)
        verified = bundles.verify_stored_bundle(row, _trust_root_for(signing_key))
        assert verified.signed_by  # one key signed it
