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

TRUST_ROOT_FORMAT = "vigil.edge.trust-root/v1"
# The trust-root wire contract is pinned by the contract schemas; this
# module deliberately re-implements it (services.edge imports nothing
# from core), so both sides must agree on the field set and semantics.
_TRUST_ROOT_FIELDS = frozenset(
    {"format", "version", "issued_at", "expires_at", "keys", "roles", "revoked_keyids"}
)
_KEY_FIELDS = frozenset({"public", "not_after"})
_ROLE_FIELDS = frozenset({"keyids", "threshold", "payload_types"})
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
    """The offline trust store, TUF-shaped v1 — the exact document
    core/edge/signing.build_trust_root emits. ``keys`` maps keyids to raw
    32-byte hex for signature checks; ``roles``/``revoked_keyids``/
    ``not_after`` carry the root's authorization and rotation metadata and
    are enforced here exactly as the control plane's own verifier does."""

    keys: dict[str, str]
    key_not_after: dict[str, datetime] = field(default_factory=dict)
    revoked: frozenset[str] = frozenset()
    role_keyids: frozenset[str] = frozenset()
    threshold: int = 1
    payload_types: frozenset[str] = frozenset()
    expires_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def key_expired(self, keyid: str, now: datetime) -> bool:
        not_after = self.key_not_after.get(keyid)
        return not_after is not None and now >= not_after


def _parse_tz(name: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise TrustError("E-TRUST", f"{name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TrustError("E-TRUST", f"{name} not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise TrustError("E-TRUST", f"{name} must carry a timezone")
    return parsed.astimezone(UTC)


def parse_trust_root(payload: Mapping[str, Any]) -> TrustRoot:
    if not isinstance(payload, dict):
        raise TrustError("E-TRUST", "trust root must be a JSON object")
    extra = sorted(set(payload) - _TRUST_ROOT_FIELDS)
    if extra:
        raise TrustError("E-TRUST", f"unknown trust root field(s): {', '.join(extra)}")
    if payload.get("format") != TRUST_ROOT_FORMAT:
        raise TrustError("E-TRUST", "trust root format mismatch")
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise TrustError("E-TRUST", "trust root version must be a positive integer")
    if "issued_at" not in payload:
        raise TrustError("E-TRUST", "trust root issued_at is required")
    _parse_tz("issued_at", payload["issued_at"])
    expires_at = _parse_tz("expires_at", payload.get("expires_at"))

    keys_raw = payload.get("keys")
    if not isinstance(keys_raw, dict) or not keys_raw:
        raise TrustError("E-TRUST", "trust root keys must be a non-empty object")
    parsed_keys: dict[str, str] = {}
    not_after: dict[str, datetime] = {}
    for keyid, key_doc in keys_raw.items():
        if not isinstance(keyid, str) or not isinstance(key_doc, dict):
            raise TrustError("E-TRUST", "trust root keys must map ids to key documents")
        key_extra = sorted(set(key_doc) - _KEY_FIELDS)
        if key_extra:
            raise TrustError(
                "E-TRUST", f"key {keyid!r} has unknown field(s): {', '.join(key_extra)}"
            )
        public_b64 = key_doc.get("public")
        if not isinstance(public_b64, str):
            raise TrustError("E-TRUST", f"key {keyid!r} needs a base64 'public' value")
        try:
            raw_key = base64.b64decode(public_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise TrustError(
                "E-TRUST", f"key {keyid!r} public is not valid base64"
            ) from exc
        if len(raw_key) != 32:
            raise TrustError(
                "E-TRUST", f"key {keyid!r} is not a raw 32-byte Ed25519 key"
            )
        if key_doc.get("not_after") is None:
            raise TrustError("E-TRUST", f"key {keyid!r} needs not_after")
        not_after[keyid] = _parse_tz(f"key {keyid!r} not_after", key_doc["not_after"])
        parsed_keys[keyid] = raw_key.hex()

    roles = payload.get("roles")
    if not isinstance(roles, dict) or not isinstance(roles.get("bundles"), dict):
        raise TrustError("E-TRUST", "trust root roles.bundles is required")
    role = roles["bundles"]
    role_extra = sorted(set(role) - _ROLE_FIELDS)
    if role_extra:
        raise TrustError(
            "E-TRUST", f"roles.bundles has unknown field(s): {', '.join(role_extra)}"
        )
    keyids = role.get("keyids")
    if (
        not isinstance(keyids, list)
        or not keyids
        or not all(isinstance(k, str) for k in keyids)
    ):
        raise TrustError(
            "E-TRUST", "roles.bundles.keyids must be a non-empty string list"
        )
    missing = sorted(set(keyids) - set(parsed_keys))
    if missing:
        raise TrustError(
            "E-TRUST", f"roles.bundles names unknown key(s): {', '.join(missing)}"
        )
    threshold = role.get("threshold", 1)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise TrustError(
            "E-TRUST", "roles.bundles.threshold must be a positive integer"
        )
    payload_types = role.get("payload_types")
    if (
        not isinstance(payload_types, list)
        or not payload_types
        or not all(isinstance(p, str) for p in payload_types)
    ):
        raise TrustError(
            "E-TRUST", "roles.bundles.payload_types must be a non-empty string list"
        )
    revoked_raw = payload.get("revoked_keyids", [])
    if not isinstance(revoked_raw, list) or not all(
        isinstance(k, str) for k in revoked_raw
    ):
        raise TrustError("E-TRUST", "revoked_keyids must be a string list")

    return TrustRoot(
        keys=parsed_keys,
        key_not_after=not_after,
        revoked=frozenset(revoked_raw),
        role_keyids=frozenset(keyids),
        threshold=threshold,
        payload_types=frozenset(payload_types),
        expires_at=expires_at,
        raw=dict(payload),
    )


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
    """DSSE v1 pre-authentication encoding: type length + type + payload
    length + payload, so signatures cannot be transplanted between payload
    types. Byte-for-byte the medic/core construction — a divergence here
    would make every control-plane signature unverifiable."""
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type),
        payload_type.encode(),
        len(payload),
        payload,
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
    if payload_type not in trust_root.payload_types:
        return _refuse(
            "E-PAYLOAD-TYPE",
            f"payloadType {payload_type!r} not authorized by the trust root",
        )

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
    good: set[str] = set()
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
        if keyid in trust_root.revoked:
            continue  # a revoked key can never count; keep scanning
        key_hex = trust_root.keys.get(keyid)
        if key_hex is None or keyid not in trust_root.role_keyids:
            continue  # unknown or unauthorized signer: try remaining signatures
        matched = True
        if trust_root.key_expired(keyid, now):
            return _refuse("E-KEY-EXPIRED", f"signing key {keyid} expired")
        if verify_signature(payload, str(payload_type), sig, key_hex):
            good.add(keyid)
            if len(good) >= trust_root.threshold:
                break
    if len(good) < trust_root.threshold:
        if matched or good:
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

    if bundle.min_edge_version is not None and _semver_tuple(
        edge_version
    ) < _semver_tuple(bundle.min_edge_version):
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
    "TRUST_ROOT_FORMAT",
    "TrustError",
    "TrustRoot",
    "Verification",
    "load_trust_root",
    "pae",
    "parse_trust_root",
    "verify_bundle",
    "verify_signature",
]
