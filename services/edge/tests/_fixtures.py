"""Shared fixtures for the edge unit tests: the spec's example bundle and
small fakes. Kept as a plain module (no conftest magic) so each test imports
exactly what it uses."""

from __future__ import annotations

import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from services.edge.observations.base import Observation
from services.edge.policy.envelope import TRUST_ROOT_FORMAT, pae
from services.edge.policy.model import BUNDLE_PAYLOAD_TYPE, Bundle, parse_bundle

NODE_ID = "gw-vpc-west-01"

# The design spec's example bundle, verbatim in shape: tier 2, high-severity
# C2 egress rule, both executors allowed.
BUNDLE_V7: dict[str, Any] = {
    "bundle_id": "edge-pol-vpc-west-gw",
    "edge_schema_version": 1,
    "segment_scope": {
        "vpc": "vpc-0a1b2c3d",
        "cidrs": ["10.42.0.0/16"],
        "node_selector": {"vigil.ai/edge-role": "gateway"},
    },
    "version": 7,
    "parent_version": 6,
    "not_before": "2026-10-09T00:00:00Z",
    "expires_at": "2026-10-16T00:00:00Z",
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
        {
            "action_type": "block_domain",
            "executor": "nftables",
            "params": {"max_ttl_seconds": 3600},
        },
    ],
    "rules": [
        {
            "rule_id": "c2-egress-active",
            "match": {"direction": "egress", "ioc_set": "c2-active", "dest_kind": "ip"},
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


def bundle_payload(**overrides: Any) -> dict[str, Any]:
    payload = copy.deepcopy(BUNDLE_V7)
    for key, value in overrides.items():
        payload[key] = value
    return payload


def make_bundle(**overrides: Any) -> Bundle:
    return parse_bundle(bundle_payload(**overrides))


class FakeCaps:
    """Counts since the last hour boundary — the journal supplies the real
    view; this one just replays preset numbers."""

    def __init__(self, per_hour: int = 0, active: int = 0) -> None:
        self.per_hour = per_hour
        self.active = active

    def executed_in_last_hour(self, action_type: str, now: object) -> int:
        return self.per_hour

    def active_blocks(self, now: object) -> int:
        return self.active


def make_observation(**overrides: Any) -> Observation:
    from datetime import UTC, datetime

    defaults: dict[str, Any] = {
        "timestamp": datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC),
        "direction": "egress",
        "src_ip": "10.42.7.7",
        "dest_ip": "203.0.113.55",
        "dest_domain": None,
        "proto": "tcp",
        "event_type": "flow",
        "raw_digest": "a" * 64,
        "raw_ref": "eve.json:42",
    }
    defaults.update(overrides)
    return Observation(**defaults)


class EdgeSigner:
    """Test stand-in for the control-plane bundle signer: generates an
    Ed25519 keypair and produces DSSE signatures over the PAE encoding."""

    def __init__(self, keyid: str = "edge-test-key") -> None:
        self.keyid = keyid
        self._private = Ed25519PrivateKey.generate()
        self.public_hex = (
            self._private.public_key()
            .public_bytes(Encoding.Raw, PublicFormat.Raw)
            .hex()
        )

    def sign_payload(self, payload: bytes, payload_type: str) -> str:
        return base64.b64encode(self._private.sign(pae(payload_type, payload))).decode()


def trust_root_for(
    *signers: EdgeSigner, expires_at: str | None = None
) -> dict[str, Any]:
    """TUF-shaped v1 trust root — hand-built to match
    core/edge/signing.build_trust_root's output exactly (edge tests never
    import core)."""
    now = datetime.now(UTC)
    far = (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "format": TRUST_ROOT_FORMAT,
        "version": 1,
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires_at or far,
        "keys": {
            s.keyid: {
                "public": base64.b64encode(bytes.fromhex(s.public_hex)).decode(),
                "not_after": far,
            }
            for s in signers
        },
        "roles": {
            "bundles": {
                "keyids": [s.keyid for s in signers],
                "threshold": 1,
                "payload_types": [BUNDLE_PAYLOAD_TYPE],
            }
        },
        "revoked_keyids": [],
    }


def sign_envelope(
    payload: dict[str, Any],
    signer: EdgeSigner,
    *,
    payload_type: str = BUNDLE_PAYLOAD_TYPE,
) -> dict[str, Any]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(raw).decode(),
        "signatures": [
            {"keyid": signer.keyid, "sig": signer.sign_payload(raw, payload_type)}
        ],
    }
