"""The edge wire contract, pinned where both sides can see it.

The control plane (core/edge) signs and serves; the daemon
(services/edge) verifies offline. The two packages share no imports by
design — the contract schemas are the interface — so the literals that
cross the boundary can drift silently: T1 shipped one payload-type
string while T2 accepted another, and only the end-to-end compose run
caught it. These tests re-prove the seam on every CI run: the daemon
must accept, byte for byte, what the control plane emits.
"""

import base64
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.edge.signing import BUNDLE_PAYLOAD_TYPE as CONTROL_PLANE_BUNDLE_TYPE
from core.edge.signing import build_trust_root
from services.edge.policy.envelope import parse_trust_root
from services.edge.policy.model import BUNDLE_PAYLOAD_TYPE as DAEMON_BUNDLE_TYPE


def test_bundle_payload_type_is_one_wire_literal() -> None:
    assert CONTROL_PLANE_BUNDLE_TYPE == DAEMON_BUNDLE_TYPE


def test_daemon_parses_the_trust_root_the_control_plane_builds() -> None:
    """build_trust_root's output must satisfy the daemon's strict offline
    parser — the operator hands that exact document to edge nodes."""
    public_raw = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    now = datetime.now(UTC)
    root = build_trust_root(
        base64.b64encode(public_raw).decode(),
        version=1,
        issued_at=now,
        expires_at=now + timedelta(days=1),
    )
    parsed = parse_trust_root(root)
    assert parsed.keys
    assert not parsed.expired(now)
