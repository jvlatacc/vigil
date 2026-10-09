"""Fixture builders for the core/edge tests.

Every test builds its own keypairs and trust root in-process — the same way
the Medic fixtures do — so no secret material ever ships in the repo. The
builders are module-level functions, not pytest fixtures, because each test
parameterizes over different key layouts (thresholds, revocations, forks).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.edge import EDGE_POLICY, EDGE_TRUST_ROOT
from core.edge.policy import MAX_POLICY_LIFETIME_DAYS
from core.edge.signing import (
    deterministic_json,
    keyid_for,
    public_raw,
    sign_envelope,
)
from core.edge.verify import load_root

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
ROOT_EXPIRES = "2027-11-04T00:00:00Z"
KEY_EXPIRES = "2027-11-04T00:00:00Z"


def generate_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def root_entry(key: Ed25519PrivateKey) -> dict:
    return {
        "alg": "ed25519",
        "public": base64.b64encode(public_raw(key)).decode(),
        "not_after": KEY_EXPIRES,
        "holder": "aws-kms:edge-2026",
    }


def build_root_doc(
    root_keys: Sequence[Ed25519PrivateKey],
    policy_keys: Sequence[Ed25519PrivateKey],
    *,
    version: int = 1,
    root_threshold: int | None = None,
    policies_threshold: int | None = None,
    revoked: Sequence[Ed25519PrivateKey] = (),
    extra_roles: dict | None = None,
    expires_at: str = ROOT_EXPIRES,
    issued_at: str = "2026-10-01T00:00:00Z",
) -> dict:
    """A trust root document: root role signs roots, policies role signs packs."""
    all_keys = list(root_keys) + list(policy_keys) + list(revoked)
    roles = {
        "root": {
            "keyids": [keyid_for(k) for k in root_keys],
            "threshold": (
                root_threshold if root_threshold is not None else len(root_keys)
            ),
            "payload_types": [EDGE_TRUST_ROOT],
        },
        "policies": {
            "keyids": [keyid_for(k) for k in policy_keys],
            "threshold": (
                policies_threshold
                if policies_threshold is not None
                else len(policy_keys)
            ),
            "payload_types": [EDGE_POLICY],
        },
    }
    if extra_roles:
        roles.update(extra_roles)
    return {
        "format": "vigil.edge-trust-root/v1",
        "version": version,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "keys": {keyid_for(k): root_entry(k) for k in all_keys},
        "roles": roles,
        "revoked_keyids": [keyid_for(k) for k in revoked],
    }


def bake_root(doc: dict, signers: Sequence[Ed25519PrivateKey]) -> dict:
    """Self-sign and load a trust root — the image-bake step."""
    return load_root(
        sign_envelope(deterministic_json(doc), EDGE_TRUST_ROOT, list(signers)), now=NOW
    )


def default_root(
    *,
    root_keys: Sequence[Ed25519PrivateKey] | None = None,
    policy_keys: Sequence[Ed25519PrivateKey] | None = None,
    **kwargs,
) -> dict:
    """One root key, one policy key, both live. The common case."""
    rk = list(root_keys or [generate_key()])
    pk = list(policy_keys or [generate_key()])
    return bake_root(build_root_doc(rk, pk, **kwargs), rk)


def policy_doc(
    *,
    version: int = 42,
    issued: datetime | None = None,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    envelope: dict | None = None,
    protected: Sequence[str] | None = None,
    rules: Sequence[dict] | None = None,
    model: dict | None = None,
    selectors: Sequence[str] = ("segment:dmz",),
) -> dict:
    """A spec-shaped policy pack document; every field overridable."""
    issued = issued or NOW
    not_before = not_before or issued  # the spec shape: validity starts at issue
    not_after = not_after or (NOW + timedelta(days=6))
    return {
        "format": "vigil.edge-policy/v1",
        "policy_version": version,
        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_before": not_before.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_after": not_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "node_selectors": list(selectors),
        "autonomy_envelope": envelope
        or {
            "allowed_actions": ["block_ip"],
            "max_actions_per_hour": 5,
            "max_action_ttl_minutes": 30,
            "require_reversible": True,
            "confidence_floor": 0.9,
            "allow_slm_decisions": False,
        },
        "protected_targets": (
            list(protected)
            if protected is not None
            else ["self", "gateway", "control_plane", "dns_resolvers"]
        ),
        "rules": (
            list(rules)
            if rules is not None
            else [
                {
                    "rule_id": "edge-001",
                    "match": {
                        "indicator": "ip",
                        "mitre": ["T1071"],
                        "min_local_confidence": 0.85,
                    },
                    "action": {"type": "block_ip", "ttl_minutes": 30},
                }
            ]
        ),
        "model_manifest": model
        or {
            "name": "security-slm-1b-q4",
            "sha256": "9f" * 32,
            "format": "gguf",
        },
    }


def sign_policy(
    doc: dict, keys: Sequence[Ed25519PrivateKey], payload: bytes | None = None
) -> bytes:
    """Sign a policy document with the given keys (payload may be overridden
    to build re-signed-with-wrong-key fixtures)."""
    return sign_envelope(
        payload if payload is not None else deterministic_json(doc),
        EDGE_POLICY,
        list(keys),
    )


def valid_pack_bytes(
    keys: Sequence[Ed25519PrivateKey] | None = None, **kwargs
) -> bytes:
    """A pack that verifies and parses: the control case."""
    return sign_policy(policy_doc(**kwargs), keys or [generate_key()])


def days(n: int) -> timedelta:
    return timedelta(days=n)


def max_lifetime_not_after(now: datetime) -> datetime:
    return now + timedelta(days=MAX_POLICY_LIFETIME_DAYS)


__all__ = [
    "NOW",
    "bake_root",
    "build_root_doc",
    "days",
    "default_root",
    "generate_key",
    "max_lifetime_not_after",
    "policy_doc",
    "root_entry",
    "sign_policy",
    "valid_pack_bytes",
]
