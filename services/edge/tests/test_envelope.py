"""DSSE verification suite — the design spec's bundle-verification list:
bad signature, unknown signer, tampered payload, schema refusals, validity
windows, minimum edge version, scope mismatch, revocation precedence,
rollback resistance, and trust-store failure."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from services.edge.policy.envelope import (
    TrustError,
    load_trust_root,
    parse_trust_root,
    verify_bundle,
)
from services.edge.policy.model import BUNDLE_PAYLOAD_TYPE
from services.edge.tests._fixtures import (
    EdgeSigner,
    bundle_payload,
    make_bundle,
    sign_envelope,
    trust_root_for,
)

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
GATEWAY_LABELS = {"vigil.ai/edge-role": "gateway", "vigil.ai/vpc": "vpc-0a1b2c3d"}


@pytest.fixture()
def signer() -> EdgeSigner:
    return EdgeSigner()


@pytest.fixture()
def trust(signer: EdgeSigner):
    return parse_trust_root(trust_root_for(signer))


def _verify(
    envelope, trust, *, current=None, now=NOW, edge_version="1.0.0", labels=None
):
    return verify_bundle(
        envelope,
        trust,
        now=now,
        edge_version=edge_version,
        node_labels=labels if labels is not None else GATEWAY_LABELS,
        current=current,
    )


def test_valid_envelope_verifies(signer: EdgeSigner, trust) -> None:
    result = _verify(sign_envelope(bundle_payload(), signer), trust)
    assert result.accepted
    assert result.code == "OK"
    assert result.bundle is not None
    assert result.bundle.bundle_id == "edge-pol-vpc-west-gw"


def test_tampered_payload_fails_signature(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(), signer)
    raw = base64.b64decode(envelope["payload"])
    tampered = dict(envelope)
    tampered["payload"] = base64.b64encode(bytes([raw[0] ^ 0x01]) + raw[1:]).decode()
    result = _verify(tampered, trust)
    assert not result.accepted
    assert result.code == "E-BAD-SIGNATURE"


def test_signature_transplant_between_payload_types_refused(
    signer: EdgeSigner, trust
) -> None:
    """A signature made over a different PAE (payload type) must not verify:
    the envelope claims the vigil payload type but the signature was computed
    over a foreign type's PAE — a transplant, not a type refusal."""
    envelope = sign_envelope(bundle_payload(), signer, payload_type="application/other")
    envelope["payloadType"] = BUNDLE_PAYLOAD_TYPE
    result = _verify(envelope, trust)
    assert not result.accepted
    assert result.code == "E-BAD-SIGNATURE"


def test_unknown_signer_refused(trust) -> None:
    stranger = EdgeSigner(keyid="stranger-key")
    result = _verify(sign_envelope(bundle_payload(), stranger), trust)
    assert not result.accepted
    assert result.code == "E-UNKNOWN-SIGNER"


def test_wrong_payload_type_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(), signer)
    result = _verify({**envelope, "payloadType": "application/json"}, trust)
    assert not result.accepted
    assert result.code == "E-PAYLOAD-TYPE"


def test_unknown_envelope_field_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(), signer)
    result = _verify({**envelope, "surprise": 1}, trust)
    assert not result.accepted
    assert result.code == "E-ENVELOPE"


def test_empty_signatures_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(), signer)
    result = _verify({**envelope, "signatures": []}, trust)
    assert not result.accepted
    assert result.code == "E-ENVELOPE"


def test_non_json_payload_refused(signer: EdgeSigner, trust) -> None:
    payload_type = BUNDLE_PAYLOAD_TYPE
    envelope = {
        "payloadType": payload_type,
        "payload": base64.b64encode(b"not json at all").decode(),
        "signatures": [
            {
                "keyid": signer.keyid,
                "sig": signer.sign_payload(b"not json at all", payload_type),
            }
        ],
    }
    result = _verify(envelope, trust)
    assert not result.accepted
    assert result.code == "E-PAYLOAD"


def test_schema_refusal_surfaces_bundle_code(signer: EdgeSigner, trust) -> None:
    bad = bundle_payload()
    bad["unexpected_field"] = True
    result = _verify(sign_envelope(bad, signer), trust)
    assert not result.accepted
    assert result.code == "B-SCHEMA"


def test_future_not_before_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(not_before="2026-10-09T18:00:00Z"), signer)
    result = _verify(envelope, trust)
    assert not result.accepted
    assert result.code == "E-NOT-YET"


def test_expired_bundle_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(expires_at="2026-10-10T00:00:00Z"), signer)
    result = _verify(envelope, trust, now=datetime(2026, 10, 11, 0, 0, tzinfo=UTC))
    assert not result.accepted
    assert result.code == "E-EXPIRED"


def test_minimum_edge_version_refused(signer: EdgeSigner, trust) -> None:
    envelope = sign_envelope(bundle_payload(min_edge_version="2.0.0"), signer)
    result = _verify(envelope, trust, edge_version="1.5.0")
    assert not result.accepted
    assert result.code == "E-MIN-VERSION"


def test_scope_mismatch_refused(signer: EdgeSigner, trust) -> None:
    result = _verify(
        sign_envelope(bundle_payload(), signer),
        trust,
        labels={"vigil.ai/edge-role": "worker"},
    )
    assert not result.accepted
    assert result.code == "E-SCOPE"


def test_non_monotonic_version_refused(signer: EdgeSigner, trust) -> None:
    current = make_bundle(version=9)
    envelope = sign_envelope(bundle_payload(version=7), signer)
    result = _verify(envelope, trust, current=current)
    assert not result.accepted
    assert result.code == "E-VERSION"


def test_equal_version_refused(signer: EdgeSigner, trust) -> None:
    current = make_bundle(version=7)
    envelope = sign_envelope(bundle_payload(version=7), signer)
    result = _verify(envelope, trust, current=current)
    assert not result.accepted
    assert result.code == "E-VERSION"


def test_revocation_precedence_over_version(signer: EdgeSigner, trust) -> None:
    """Central revocation beats local allowance — checked before monotonicity
    so a revoked re-sign cannot ride a version bump past the gate."""
    current = make_bundle(
        version=8, revocations=[{"bundle_id": "edge-pol-vpc-west-gw", "version": 9}]
    )
    envelope = sign_envelope(bundle_payload(version=9), signer)
    result = _verify(envelope, trust, current=current)
    assert not result.accepted
    assert result.code == "E-REVOKED"


def test_expired_trust_root_refuses_everything(signer: EdgeSigner) -> None:
    stale = parse_trust_root(trust_root_for(signer, expires_at="2026-10-01T00:00:00Z"))
    result = _verify(sign_envelope(bundle_payload(), signer), stale)
    assert not result.accepted
    assert result.code == "E-TRUST-EXPIRED"


def test_corrupt_trust_root_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "trust-root.dsse.json"
    bad.write_text("{not json")
    with pytest.raises(TrustError) as excinfo:
        load_trust_root(bad)
    assert excinfo.value.code == "E-TRUST"


def test_missing_trust_root_file_raises(tmp_path: Path) -> None:
    with pytest.raises(TrustError) as excinfo:
        load_trust_root(tmp_path / "absent.json")
    assert excinfo.value.code == "E-TRUST"


def test_trust_root_expiry_roundtrip(signer: EdgeSigner) -> None:
    raw = json.dumps(trust_root_for(signer, expires_at="2026-12-01T00:00:00Z"))
    parsed = parse_trust_root(json.loads(raw))
    assert parsed.expires_at == datetime(2026, 12, 1, tzinfo=UTC)
    assert not parsed.expired(NOW)


def test_revoked_root_key_cannot_sign(signer: EdgeSigner) -> None:
    root = trust_root_for(signer)
    root["revoked_keyids"] = [signer.keyid]
    result = _verify(sign_envelope(bundle_payload(), signer), parse_trust_root(root))
    assert not result.accepted
    assert result.code == "E-UNKNOWN-SIGNER"


def test_expired_signing_key_refused(signer: EdgeSigner) -> None:
    root = trust_root_for(signer)
    root["keys"][signer.keyid]["not_after"] = "2026-10-01T00:00:00Z"
    result = _verify(sign_envelope(bundle_payload(), signer), parse_trust_root(root))
    assert not result.accepted
    assert result.code == "E-KEY-EXPIRED"


def test_key_outside_bundle_role_cannot_sign(signer: EdgeSigner) -> None:
    other = EdgeSigner(keyid="other-key")
    root = trust_root_for(signer, other)
    root["roles"]["bundles"]["keyids"] = [other.keyid]
    result = _verify(sign_envelope(bundle_payload(), signer), parse_trust_root(root))
    assert not result.accepted
    assert result.code == "E-UNKNOWN-SIGNER"


def test_payload_type_not_in_root_role_refused(signer: EdgeSigner) -> None:
    root = trust_root_for(signer)
    root["roles"]["bundles"]["payload_types"] = ["application/json"]
    result = _verify(sign_envelope(bundle_payload(), signer), parse_trust_root(root))
    assert not result.accepted
    assert result.code == "E-PAYLOAD-TYPE"


def test_wrong_trust_root_format_raises(signer: EdgeSigner) -> None:
    root = trust_root_for(signer)
    root["format"] = "vigil.edge.trust-root/v2"
    with pytest.raises(TrustError) as excinfo:
        parse_trust_root(root)
    assert excinfo.value.code == "E-TRUST"


def test_threshold_unmet_refused(signer: EdgeSigner) -> None:
    root = trust_root_for(signer)
    root["roles"]["bundles"]["threshold"] = 2
    result = _verify(sign_envelope(bundle_payload(), signer), parse_trust_root(root))
    assert not result.accepted
    assert result.code == "E-BAD-SIGNATURE"
