"""DSSE signing, verification, and sign-time bundle lint tests.

Table-driven cases for the failure modes the spec names: bad signature,
unknown signer, revoked key, expired key, schema-version refusal,
non-monotonic version, plus the happy path (sign → verify round-trip with
prior-envelope determinism).
"""

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from core.edge import signing
from core.time import utcnow


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str, str]:
    return signing.generate_signing_keypair()


@pytest.fixture
def private_key(keypair) -> Ed25519PrivateKey:
    pem, _, _ = keypair
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


@pytest.fixture
def trust_root(keypair) -> dict:
    _, public_b64, _ = keypair
    now = utcnow()
    return signing.build_trust_root(
        public_b64,
        version=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )


@pytest.fixture
def bundle_document() -> dict:
    """The spec's example bundle, trimmed to its load-bearing fields."""
    now = utcnow()
    return {
        "bundle_id": "edge-pol-vpc-west-gw",
        "edge_schema_version": 1,
        "segment_scope": {
            "vpc": "vpc-0a1b2c3d",
            "cidrs": ["10.42.0.0/16"],
            "node_selector": {"vigil.ai/edge-role": "gateway"},
        },
        "version": 7,
        "parent_version": 6,
        "not_before": signing.ts_format(now),
        "expires_at": signing.ts_format(now + timedelta(days=7)),
        "min_edge_version": "1.0.0",
        "autonomy_tier": "tier2",
        "decision": {
            "auto_act_confidence": 0.92,
            "escalate_confidence": 0.85,
            "max_actions_per_hour": 6,
            "max_active_blocks": 24,
            "default_block_ttl_seconds": 900,
        },
        "allowed_actions": [
            {
                "action_type": "block_ip",
                "executor": "nftables",
                "params": {"max_ttl_seconds": 3600},
            },
            {
                "action_type": "block_ip",
                "executor": "k8s_networkpolicy",
                "params": {"namespaces": ["prod", "staging"]},
            },
        ],
        "rules": [
            {
                "rule_id": "c2-egress-active",
                "match": {
                    "direction": "egress",
                    "ioc_set": "c2-active",
                    "dest_kind": "ip",
                },
                "severity_floor": "high",
            }
        ],
        "ioc_sets": {
            "c2-active": {
                "kind": "cidr",
                "entries": ["203.0.113.0/24"],
                "source": "threat-intel-sync@2026-10-08",
            }
        },
        "revocations": [],
        "rollback_reference": {"bundle_id": "edge-pol-vpc-west-gw", "version": 6},
    }


def _forge_envelope(private_key: Ed25519PrivateKey, payload_bytes: bytes) -> dict:
    """Build a correctly-signed envelope over arbitrary payload bytes."""
    signature = private_key.sign(
        signing.pae(signing.BUNDLE_PAYLOAD_TYPE, payload_bytes)
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "payloadType": signing.BUNDLE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [
            {
                "keyid": signing.keyid(public_raw),
                "sig": base64.b64encode(signature).decode(),
            }
        ],
    }


class TestSignVerify:
    def test_round_trip(self, private_key, trust_root, bundle_document):
        envelope = signing.sign_payload(bundle_document, private_key)
        verified = signing.verify_envelope(envelope, trust_root)
        assert verified.payload == bundle_document
        assert verified.payload_type == signing.BUNDLE_PAYLOAD_TYPE
        assert len(verified.signed_by) == 1

    def test_signature_is_deterministic_over_canonical_bytes(
        self, private_key, bundle_document
    ):
        first = signing.sign_payload(bundle_document, private_key)
        shuffled = dict(reversed(list(bundle_document.items())))
        second = signing.sign_payload(shuffled, private_key)
        assert first["payload"] == second["payload"]
        assert first["signatures"][0]["sig"] == second["signatures"][0]["sig"]

    def test_keyid_matches_medic_convention(self, keypair):
        _, public_b64, kid = keypair
        assert kid == signing.keyid(base64.b64decode(public_b64))
        assert len(kid) == 32
        int(kid, 16)  # hex

    def test_pae_is_dsse_v1(self):
        message = signing.pae("application/x", b"{}")
        assert message == b"DSSEv1 13 application/x 2 {}"


class TestTamperDetection:
    def test_flipped_payload_byte_fails(self, private_key, trust_root, bundle_document):
        envelope = signing.sign_payload(bundle_document, private_key)
        raw = bytearray(base64.b64decode(envelope["payload"]))
        raw[0] ^= 0x01
        envelope["payload"] = base64.b64encode(bytes(raw)).decode()
        with pytest.raises(signing.VerificationFailure, match="S-SIG"):
            signing.verify_envelope(envelope, trust_root)

    def test_wrong_key_fails(self, private_key, bundle_document):
        _, other_public, _ = signing.generate_signing_keypair()
        other_root = signing.build_trust_root(
            other_public,
            version=1,
            issued_at=utcnow(),
            expires_at=utcnow() + timedelta(days=1),
        )
        envelope = signing.sign_payload(bundle_document, private_key)
        with pytest.raises(signing.VerificationFailure, match="S-SCOPE"):
            signing.verify_envelope(envelope, other_root)

    def test_unknown_signer_fails(self, private_key, trust_root, bundle_document):
        envelope = signing.sign_payload(bundle_document, private_key)
        other_pem, _, _ = signing.generate_signing_keypair()
        other_key = serialization.load_pem_private_key(
            other_pem.encode(), password=None
        )
        envelope["signatures"][0]["sig"] = base64.b64encode(
            other_key.sign(b"anything")
        ).decode()
        with pytest.raises(signing.VerificationFailure, match="S-SIG"):
            signing.verify_envelope(envelope, trust_root)

    def test_revoked_keyid_cannot_meet_threshold(
        self, private_key, keypair, trust_root, bundle_document
    ):
        _, _, kid = keypair
        trust_root["revoked_keyids"] = [kid]
        envelope = signing.sign_payload(bundle_document, private_key)
        with pytest.raises(signing.VerificationFailure, match="S-THRESHOLD"):
            signing.verify_envelope(envelope, trust_root)

    def test_expired_key_fails(self, keypair, bundle_document):
        _, public_b64, _ = keypair
        now = utcnow()
        root = signing.build_trust_root(
            public_b64,
            version=1,
            issued_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=1),
            key_not_after=now - timedelta(days=1),
        )
        pem, _, _ = keypair
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        envelope = signing.sign_payload(bundle_document, key)
        with pytest.raises(signing.VerificationFailure, match="S-KEY-EXPIRED"):
            signing.verify_envelope(envelope, root)

    def test_expired_trust_root_fails(self, keypair, private_key, bundle_document):
        _, public_b64, _ = keypair
        now = utcnow()
        root = signing.build_trust_root(
            public_b64,
            version=1,
            issued_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
        envelope = signing.sign_payload(bundle_document, private_key)
        with pytest.raises(signing.VerificationFailure, match="S-ROOT-EXPIRED"):
            signing.verify_envelope(envelope, root)

    def test_wrong_payload_type_fails(self, private_key, trust_root, bundle_document):
        envelope = signing.sign_payload(bundle_document, private_key)
        envelope["payloadType"] = "application/evil"
        with pytest.raises(signing.VerificationFailure, match="S-TYPE"):
            signing.verify_envelope(envelope, trust_root)

    def test_duplicate_json_keys_in_payload_fail(self, private_key, trust_root):
        envelope = _forge_envelope(private_key, b'{"bundle_id": "x", "bundle_id": "y"}')
        with pytest.raises(signing.VerificationFailure, match="S-JSON"):
            signing.verify_envelope(envelope, trust_root)

    def test_non_object_payload_fails(self, private_key, trust_root):
        envelope = _forge_envelope(private_key, b"[1, 2, 3]")
        with pytest.raises(signing.VerificationFailure, match="S-JSON"):
            signing.verify_envelope(envelope, trust_root)


class TestTrustRootContract:
    def test_built_root_validates_against_the_contract(self, trust_root):
        schema = json.loads(
            (Path(signing.CONTRACTS_DIR) / "edge-trust-root.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(trust_root)

    def test_built_root_names_the_bundle_payload_type(self, trust_root):
        assert trust_root["format"] == "vigil.edge.trust-root/v1"
        assert trust_root["roles"]["bundles"]["payload_types"] == [
            signing.BUNDLE_PAYLOAD_TYPE
        ]


class TestBundleLint:
    def test_spec_example_passes(self, bundle_document):
        signing.validate_bundle_document(bundle_document)

    def test_tier3_is_unsignable(self, bundle_document):
        bundle_document["autonomy_tier"] = "tier3"
        with pytest.raises(signing.BundleValidationError, match="schema"):
            signing.validate_bundle_document(bundle_document)

    def test_tier0_observe_only_is_signable(self, bundle_document):
        bundle_document["autonomy_tier"] = "tier0"
        bundle_document["allowed_actions"] = []
        signing.validate_bundle_document(bundle_document)

    def test_isolate_host_is_not_in_the_v1_vocabulary(self, bundle_document):
        bundle_document["allowed_actions"].append(
            {"action_type": "isolate_host", "executor": "nftables"}
        )
        with pytest.raises(signing.BundleValidationError, match="schema"):
            signing.validate_bundle_document(bundle_document)

    def test_inverted_validity_window_rejected(self, bundle_document):
        bundle_document["expires_at"] = bundle_document["not_before"]
        with pytest.raises(signing.BundleValidationError, match="expires_at"):
            signing.validate_bundle_document(bundle_document)

    def test_window_over_ninety_days_rejected(self, bundle_document):
        not_before = datetime.strptime("2026-01-01T00:00:00Z", signing._TS_FORMAT)
        bundle_document["not_before"] = signing.ts_format(not_before)
        bundle_document["expires_at"] = signing.ts_format(
            not_before + timedelta(days=91)
        )
        with pytest.raises(signing.BundleValidationError, match="90 days"):
            signing.validate_bundle_document(bundle_document)

    def test_future_not_before_is_flagged(self, bundle_document):
        now = utcnow()
        bundle_document["not_before"] = signing.ts_format(now + timedelta(days=30))
        bundle_document["expires_at"] = signing.ts_format(now + timedelta(days=37))
        with pytest.raises(signing.BundleValidationError, match="future"):
            signing.validate_bundle_document(bundle_document)

    def test_non_monotonic_parent_version_rejected(self, bundle_document):
        bundle_document["parent_version"] = bundle_document["version"]
        with pytest.raises(signing.BundleValidationError, match="parent_version"):
            signing.validate_bundle_document(bundle_document)

    def test_escalate_above_auto_act_rejected(self, bundle_document):
        bundle_document["decision"]["escalate_confidence"] = 0.99
        bundle_document["decision"]["auto_act_confidence"] = 0.90
        with pytest.raises(signing.BundleValidationError, match="escalate_confidence"):
            signing.validate_bundle_document(bundle_document)

    def test_missing_required_field_rejected(self, bundle_document):
        del bundle_document["decision"]
        with pytest.raises(signing.BundleValidationError, match="schema"):
            signing.validate_bundle_document(bundle_document)

    def test_unknown_field_rejected(self, bundle_document):
        bundle_document["sneaky_extra"] = "bypass"
        with pytest.raises(signing.BundleValidationError, match="schema"):
            signing.validate_bundle_document(bundle_document)

    def test_problems_listed_not_just_first(self, bundle_document):
        bundle_document["autonomy_tier"] = "tier9"
        bundle_document["parent_version"] = 999
        with pytest.raises(signing.BundleValidationError) as exc:
            signing.validate_bundle_document(bundle_document)
        assert len(exc.value.problems) >= 2

    def test_signing_refuses_invalid_bundle(self, private_key, bundle_document):
        bundle_document["autonomy_tier"] = "tier3"
        with pytest.raises(signing.BundleValidationError):
            signing.validate_bundle_document(bundle_document)
