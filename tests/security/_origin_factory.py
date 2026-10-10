"""The sender side of the origin attestation, for tests (#944).

Shared by the verifier tests (tests/unit/response/test_origin.py) and the
adversarial suite (tests/security/test_origin_spoofing.py). This is exactly
what a Vigil sensor does — sign the canonical finding bytes and put the
envelope in the header — so the verifier under test never sees these helpers.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.response.origin import FINDING_PAYLOAD_TYPE, pae

FINDING = {
    "finding_id": "webhook-attest-1",
    "data_source": "webhook",
    "severity": "critical",
    "title": "attested finding",
    "description": "signed by the factory",
}

# A fixed "now" so iat/age boundaries are exact in every test.
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    public = private_key.public_key()
    raw = public.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return b64(raw)


def medic_keyid(public_b64: str) -> str:
    """Medic's keyid convention: first 32 hex of sha256(raw public key)."""
    import hashlib

    return hashlib.sha256(base64.b64decode(public_b64)).hexdigest()[:32]


class Signer:
    """One sensor: an origin id and the Ed25519 key it signs with."""

    def __init__(
        self, origin_id: str = "sensor-edge-01", key: Optional[Ed25519PrivateKey] = None
    ):
        self.origin_id = origin_id
        self.key = key or Ed25519PrivateKey.generate()

    def trust_entry(
        self,
        *,
        scope: str = "*",
        enabled: bool = True,
        not_after: Optional[str] = None,
    ) -> dict:
        entry: dict[str, Any] = {
            "origin_id": self.origin_id,
            "public_key": public_key_b64(self.key),
            "scope": scope,
            "enabled": enabled,
        }
        if not_after is not None:
            entry["not_after"] = not_after
        return entry

    def sign_payload(
        self,
        payload: bytes,
        *,
        payload_type: str = FINDING_PAYLOAD_TYPE,
        iat: Optional[int] = None,
        jti: str = "01J-TEST-NONCE-0001",
        keyid: Optional[str] = None,
        sig: Optional[str] = None,
    ) -> str:
        """One-signature envelope over PAE(payload_type, payload)."""
        signature = (
            b64(self.key.sign(pae(payload_type, payload))) if sig is None else sig
        )
        envelope = {
            "payload_type": payload_type,
            "payload": b64(payload),
            "signatures": [
                {
                    "keyid": keyid or self.origin_id,
                    "sig": signature,
                    "iat": int(datetime.now(UTC).timestamp()) if iat is None else iat,
                    "jti": jti,
                }
            ],
        }
        return json.dumps(envelope)

    def sign_finding(self, finding: Optional[dict] = None, **kwargs: Any) -> str:
        payload = json.dumps(FINDING if finding is None else finding).encode()
        return self.sign_payload(payload, **kwargs)


def medic_trust_check() -> ModuleType:
    """Load the Medic verifier by path.

    ``services`` is a namespace package and the contracts directory has no
    ``__init__.py`` on purpose (grimp skips it); loading by file path keeps
    this a test-only read across the import fence rather than a new module
    dependency. Registering in ``sys.modules`` first is required before
    ``exec_module`` — dataclass processing looks the module up there.
    """
    name = "medic_trust_check_parity"
    if name in sys.modules:
        return sys.modules[name]
    path = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "medic"
        / "contracts"
        / "trust_check.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def medic_root(
    public_b64: str,
    kid: str,
    *,
    payload_types: tuple[str, ...],
    revoked: tuple[str, ...] = (),
    key_not_after: str = "2099-01-01T00:00:00Z",
    expires_at: str = "2099-01-01T00:00:00Z",
) -> dict:
    """A minimal trust root trust_check.verify_envelope will accept.

    verify_envelope reads roles/four names unconditionally, so all four must
    exist; only the role carrying ``payload_types`` needs real key material.
    """
    roles = {
        name: {"keyids": [kid], "threshold": 1, "payload_types": list(payload_types)}
        for name in ("packs", "packs-dev", "fixplans", "root")
    }
    return {
        "version": 1,
        "expires_at": expires_at,
        "revoked_keyids": list(revoked),
        "keys": {
            kid: {
                "alg": "ed25519",
                "public": public_b64,
                "not_after": key_not_after,
                "holder": "test:yubikey-1",
            }
        },
        "roles": roles,
    }


def medic_envelope(
    signer: Signer,
    payload: bytes,
    *,
    payload_type: str,
    keyid: Optional[str] = None,
    sig: Optional[str] = None,
) -> bytes:
    trust_check = medic_trust_check()
    signature = (
        b64(signer.key.sign(trust_check.pae(payload_type, payload)))
        if sig is None
        else sig
    )
    envelope = {
        "payloadType": payload_type,
        "payload": b64(payload),
        "signatures": [
            {
                "keyid": keyid or medic_keyid(public_key_b64(signer.key)),
                "sig": signature,
            }
        ],
    }
    return json.dumps(envelope).encode()
