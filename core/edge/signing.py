"""DSSE v1 / Ed25519 signing for edge policy packs and trust roots.

The control-plane side of ``core/edge/verify.py``: envelopes built here are
exactly what the offline verifier accepts, because both go through the same
``pae()`` and ``keyid()``. Signing keys stay with the control plane (KMS in
production, per the Medic pattern); a Warden node never holds one — it only
verifies against the trust root baked into its image.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.edge.verify import keyid, pae

__all__ = [
    "deterministic_json",
    "keyid_for",
    "public_raw",
    "sign_envelope",
]


def public_raw(private_key: Ed25519PrivateKey) -> bytes:
    """The raw 32-byte public key of a private signing key."""
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def keyid_for(private_key: Ed25519PrivateKey) -> str:
    """The keyid the verifier will expect for this key — same derivation."""
    return keyid(public_raw(private_key))


def deterministic_json(doc: dict[str, Any]) -> bytes:
    """Serialize a policy document to the exact bytes that get signed and hashed.

    Sorted keys, no whitespace: the same document always yields the same
    payload bytes, which is what the version gate's payload-hash comparison —
    and a reviewer's rebuild-and-compare — depends on.
    """
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def sign_envelope(
    payload: bytes, payload_type: str, signers: Sequence[Ed25519PrivateKey]
) -> bytes:
    """Build a DSSE v1 envelope: one Ed25519 signature per key, over the PAE.

    Signatures cover ``pae(payload_type, payload)`` — the type is bound by the
    signature, so swapping payloadType on a stolen envelope fails verification.
    """
    signatures = []
    for signer in signers:
        raw = public_raw(signer)
        signatures.append(
            {
                "keyid": keyid(raw),
                "sig": base64.b64encode(
                    signer.sign(pae(payload_type, payload))
                ).decode(),
            }
        )
    envelope = {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload).decode(),
        "signatures": signatures,
    }
    return (json.dumps(envelope, indent=2) + "\n").encode()
