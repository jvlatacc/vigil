"""DSSE envelope verification against an offline trust store.

The wire form follows DSSE (IETF draft): base64 payload, payloadType, and
Ed25519 signatures over the PAE encoding — signature binds the exact signed
bytes, so payload tampering fails verification before parsing even runs.
Verification is table-driven refuse-early: trust root validity, envelope
shape, signer, signature, schema, validity window, minimum edge version,
scope, revocation precedence, then monotonic version (rollback resistance).
A refused bundle never activates — the cache keeps the last-known-good one
and the node drops to whatever tier remains valid (expired => Tier 0).
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from services.edge.policy.model import (
    BUNDLE_PAYLOAD_TYPE,
    Bundle,
    BundleError,
    parse_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_TRUST_ROOT_FIELDS = frozenset({"keys", "expires_at"})
_ENVELOPE_FIELDS = frozenset({"payloadType", "payload", "signatures"})
_SIGNATURE_FIELDS = frozenset({"keyid", "sig"})


class TrustError(ValueError):
    """The trust store itself is unusable — DEGRADED, refuse activation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class TrustRoot:
    """The offline trust store: named Ed25519 public keys (raw 32-byte hex)
    the node will accept bundle signatures from, with an optional overall
    expiry — an expired trust root refuses everything (design spec failure
    matrix: 'Trust store corrupted on disk' -> refuse + DEGRADED)."""

    keys: dict[str, str]
    expires_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)

    def expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


def parse_trust_root(payload: Mapping[str, Any]) -> TrustRoot:
    if not isinstance(payload, dict):
        raise TrustError("E-TRUST", "trust root must be a JSON object")
    extra = sorted(set(payload) - _TRUST_ROOT_FIELDS)
    if extra:
        raise TrustError("E-TRUST", f"unknown trust root field(s): {', '.join(extra)}")
    keys = payload.get("keys")
    if not isinstance(keys, dict) or not keys:
        raise TrustError("E-TRUST", "trust root keys must be a non-empty object")
    parsed_keys: dict[str, str] = {}
    for keyid, key_hex in keys.items():
        if not isinstance(keyid, str) or not isinstance(key_hex, str):
            raise TrustError("E-TRUST", "trust root keys must map ids to hex strings")
        try:
            raw_key = bytes.fromhex(key_hex)
        except ValueError as exc:
            raise TrustError("E-TRUST", f"key {keyid!r} is not hex") from exc
        if len(raw_key) != 32:
            raise TrustError(
                "E-TRUST", f"key {keyid!r} is not a raw 32-byte Ed25519 key"
            )
        parsed_keys[keyid] = key_hex
    expires_raw = payload.get("expires_at")
    expires_at = None
    if expires_raw is not None:
        if not isinstance(expires_raw, str):
            raise TrustError("E-TRUST", "expires_at must be an ISO-8601 string")
        try:
            parsed_expiry = datetime.fromisoformat(expires_raw)
        except ValueError as exc:
            raise TrustError(
                "E-TRUST", f"expires_at not ISO-8601: {expires_raw!r}"
            ) from exc
        if parsed_expiry.tzinfo is None:
            raise TrustError("E-TRUST", "expires_at must carry a timezone")
        expires_at = parsed_expiry.astimezone(UTC)
    return TrustRoot(keys=parsed_keys, expires_at=expires_at, raw=dict(payload))


def load_trust_root(path: Path) -> TrustRoot:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TrustError("E-TRUST", f"cannot read trust root {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise TrustError("E-TRUST", f"trust root {path} is not valid JSON") from exc
    return parse_trust_root(payload)


@dataclass(frozen=True)
class Verification:
    bundle: Bundle | None
    accepted: bool
    code: str  # "OK" or a stable refusal code (E-*)
    detail: str = ""


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding: type length + type + payload length
    + payload, so signatures cannot be transplanted between payload types."""
    return (
        b"DSSE"
        + str(len(payload_type)).encode()
        + b" "
        + payload_type.encode()
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def verify_signature(
    payload: bytes, payload_type: str, sig_b64: str, key_hex: str
) -> bool:
    try:
        sig = base64.b64decode(sig_b64, validate=True)
    except (binascii.Error, ValueError):
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        key.verify(sig, pae(payload_type, payload))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_bundle(
    envelope: Mapping[str, Any],
    trust_root: TrustRoot,
    *,
    now: datetime,
    edge_version: str,
    node_labels: Mapping[str, str],
    current: Bundle | None,
) -> Verification:
    """Refuse-early verification. Order is precedence: signature and schema
    before policy windows, revocation before version monotonicity."""
    if trust_root.expired(now):
        return _refuse("E-TRUST-EXPIRED", "trust root expired; refusing every bundle")
    if not isinstance(envelope, dict):
        return _refuse("E-ENVELOPE", "envelope must be a JSON object")
    extra = sorted(set(envelope) - _ENVELOPE_FIELDS)
    if extra:
        return _refuse("E-ENVELOPE", f"unknown envelope field(s): {', '.join(extra)}")
    payload_type = envelope.get("payloadType")
    if payload_type != BUNDLE_PAYLOAD_TYPE:
        return _refuse("E-PAYLOAD-TYPE", f"payloadType {payload_type!r} unsupported")

    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str):
        return _refuse("E-ENVELOPE", "payload must be a base64 string")
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (binascii.Error, ValueError):
        return _refuse("E-ENVELOPE", "payload is not valid base64")

    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        return _refuse("E-ENVELOPE", "signatures must be a non-empty list")
    matched = False
    for entry in signatures:
        if not isinstance(entry, dict):
            return _refuse("E-ENVELOPE", "signature entries must be objects")
        extra = sorted(set(entry) - _SIGNATURE_FIELDS)
        if extra:
            return _refuse(
                "E-ENVELOPE", f"unknown signature field(s): {', '.join(extra)}"
            )
        keyid = entry.get("keyid")
        sig = entry.get("sig")
        if not isinstance(keyid, str) or not isinstance(sig, str):
            return _refuse("E-ENVELOPE", "signature entries need keyid and sig strings")
        key_hex = trust_root.keys.get(keyid)
        if key_hex is None:
            continue  # unknown signer: try remaining signatures before refusing
        matched = True
        if verify_signature(payload, str(payload_type), sig, key_hex):
            break
    else:
        if matched:
            return _refuse(
                "E-BAD-SIGNATURE", "signature does not verify against the trust root"
            )
        return _refuse("E-UNKNOWN-SIGNER", "no signature keyid is in the trust store")

    try:
        parsed_payload = json.loads(payload)
    except ValueError:
        return _refuse("E-PAYLOAD", "payload is not valid JSON")
    try:
        bundle = parse_bundle(parsed_payload)
    except BundleError as exc:
        return Verification(
            bundle=None, accepted=False, code=exc.code, detail=exc.detail
        )

    if now < bundle.not_before:
        return _refuse(
            "E-NOT-YET", f"not_before {bundle.not_before.isoformat()} is in the future"
        )
    if now >= bundle.expires_at:
        return _refuse(
            "E-EXPIRED",
            f"expired at {bundle.expires_at.isoformat()}; never extended locally",
        )

    if _semver_tuple(edge_version) < _semver_tuple(bundle.min_edge_version):
        return _refuse(
            "E-MIN-VERSION",
            f"daemon {edge_version} older than bundle minimum {bundle.min_edge_version}",
        )

    if not bundle.segment_scope.matches_labels(node_labels):
        return _refuse(
            "E-SCOPE", "bundle segment_scope does not match this node's labels"
        )

    if current is not None:
        # Central revocation beats local allowance: the active bundle's
        # revocations refuse this candidate outright.
        if current.revokes(bundle):
            return _refuse(
                "E-REVOKED",
                f"{bundle.bundle_id} v{bundle.version} is revoked by {current.bundle_id} v{current.version}",
            )
        if bundle.version <= current.version:
            return _refuse(
                "E-VERSION",
                f"non-monotonic: {bundle.version} <= active {current.version} (rollback resistance)",
            )

    return Verification(bundle=bundle, accepted=True, code="OK")


def _refuse(code: str, detail: str) -> Verification:
    return Verification(bundle=None, accepted=False, code=code, detail=detail)


def _semver_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return (0, 0, 0)  # unparseable local version sorts oldest: refuse-by-default
    return (int(parts[0]), int(parts[1]), int(parts[2]))


__all__ = [
    "TrustError",
    "TrustRoot",
    "Verification",
    "load_trust_root",
    "pae",
    "parse_trust_root",
    "verify_bundle",
    "verify_signature",
]
