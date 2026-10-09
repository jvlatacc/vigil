"""DSSE signing and verification for edge policy bundles.

The signing stack mirrors ``services/medic/contracts/trust_check.py`` — the
repo's existing DSSE precedent (Ed25519, DSSE v1 pre-authentication
encoding, TUF-shaped trust root, keyid = first 32 hex of sha256 of the raw
public key) — without importing it: medic is deliberately import-isolated,
and core may not import services. The wire format is the shared contract,
enforced by the JSON Schemas in ``core/edge/contracts/`` and by tests that
run this module's verification against medic-shaped envelopes.

Signing a bundle is the human promotion of edge autonomy (README: "only
humans can promote it"): the operator's key, not a confidence score, grants
what a daemon may do unattended. The signer therefore also lints every
bundle document against the v1 wire contract before signing — tier3+ is
unsignable, actions are network-scoped, windows are bounded.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from jsonschema import Draft202012Validator

from core.time import utcnow

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).parent / "contracts"

BUNDLE_PAYLOAD_TYPE = "application/vnd.deeptempo.vigil.edge-bundle.v1+json"
TRUST_ROOT_PAYLOAD_TYPE = "application/vnd.deeptempo.vigil.edge-trust-root.v1+json"
TRUST_ROOT_FORMAT = "vigil.edge.trust-root/v1"

#: Bundle validity ceiling. Bundles are re-signed on schedule, not held
#: forever: a stolen signing key must age out like any other credential.
MAX_BUNDLE_VALIDITY = timedelta(days=90)
MAX_ENVELOPE_BYTES = 1 << 20  # 1 MiB, the medic precedent

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SigningError(Exception):
    """Key material or envelope shape is unusable."""


class BundleValidationError(Exception):
    """A bundle document failed the sign-time lint; carries every problem."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def ts_format(moment: datetime) -> str:
    """Naive-UTC datetime to the medic timestamp convention."""
    return moment.strftime(_TS_FORMAT)


def ts_parse(value: str) -> datetime:
    return datetime.strptime(value, _TS_FORMAT)


def canonical_json(document: dict) -> bytes:
    """Deterministic bytes for hashing and signing: sorted keys, no space,
    UTF-8. Must match what the daemon side hashes when it re-verifies."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def keyid(public_raw: bytes) -> str:
    """Medic convention: first 32 hex of sha256 over the raw 32-byte key."""
    return hashlib.sha256(public_raw).hexdigest()[:32]


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding: binds the type to the bytes."""
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def generate_signing_keypair() -> tuple[str, str, str]:
    """Bootstrap helper: (private PEM, public b64, keyid) for a fresh
    Ed25519 key. Operator-run — the private key never round-trips through
    the API."""
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return private_pem, base64.b64encode(public_raw).decode(), keyid(public_raw)


def load_signing_key(path: str) -> Ed25519PrivateKey:
    """Load the Ed25519 private key from a PEM file (PKCS8)."""
    try:
        key_bytes = Path(path).read_bytes()
        key = serialization.load_pem_private_key(key_bytes, password=None)
    except OSError as e:
        raise SigningError(f"signing key file unreadable: {path}") from e
    except (ValueError, TypeError) as e:
        raise SigningError(f"signing key is not valid PEM: {path}") from e
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError(
            "signing key must be an Ed25519 private key "
            "(generate with core.edge.signing.generate_signing_keypair)"
        )
    return key


def build_trust_root(
    public_b64: str,
    *,
    version: int,
    issued_at: datetime,
    expires_at: datetime,
    key_not_after: Optional[datetime] = None,
) -> dict:
    """Build (unsigned) trust root v1 for one signing key, mirroring
    medic's TUF shape. Serve this to edge nodes as their offline store."""
    public_raw = base64.b64decode(public_b64)
    kid = keyid(public_raw)
    return {
        "format": TRUST_ROOT_FORMAT,
        "version": version,
        "issued_at": ts_format(issued_at),
        "expires_at": ts_format(expires_at),
        "keys": {
            kid: {
                "public": public_b64,
                "not_after": ts_format(key_not_after or expires_at),
            }
        },
        "roles": {
            "bundles": {
                "keyids": [kid],
                "threshold": 1,
                "payload_types": [BUNDLE_PAYLOAD_TYPE],
            }
        },
        "revoked_keyids": [],
    }


def sign_payload(payload: dict, private_key: Ed25519PrivateKey) -> dict:
    """Sign a payload document into a DSSE v1 envelope.

    The signature covers PAE(payloadType, canonical payload bytes); the
    envelope carries the payload base64, exactly what the daemon verifies.
    """
    payload_bytes = canonical_json(payload)
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    signature = private_key.sign(pae(BUNDLE_PAYLOAD_TYPE, payload_bytes))
    return {
        "payloadType": BUNDLE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [
            {"keyid": keyid(public_raw), "sig": base64.b64encode(signature).decode()}
        ],
    }


class VerifiedPayload:
    """Outcome of envelope verification: payload plus who signed it."""

    def __init__(self, payload: dict, payload_type: str, signed_by: list[str]) -> None:
        self.payload = payload
        self.payload_type = payload_type
        self.signed_by = signed_by


class VerificationFailure(Exception):
    """Envelope refused; the message names the reason class, in the spirit
    of medic's error codes (S-SIG, S-SCOPE, S-THRESHOLD, ...)."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def verify_envelope(
    envelope: dict,
    trust_root: dict,
    *,
    expected_payload_type: str = BUNDLE_PAYLOAD_TYPE,
    now: Optional[datetime] = None,
) -> VerifiedPayload:
    """Verify a DSSE envelope against an offline trust root.

    Mirrors medic's ``verify_envelope``: root expiry, envelope size, strict
    JSON payload with no duplicate keys, payload-type scoping to the role,
    key revocation and expiry, and the signature-threshold check. The
    control plane uses this to verify what it is about to store and serve;
    the daemon re-implements it offline (the contract schemas pin the
    format for both sides).
    """
    now = now or utcnow()
    if (
        not isinstance(trust_root, dict)
        or trust_root.get("format") != TRUST_ROOT_FORMAT
    ):
        raise VerificationFailure("S-ROOT", "trust root format mismatch")
    if ts_parse(trust_root["expires_at"]) <= now:
        raise VerificationFailure(
            "S-ROOT-EXPIRED",
            f"trust root v{trust_root.get('version')} expired",
        )
    role = (trust_root.get("roles") or {}).get("bundles")
    if not role or not role.get("keyids"):
        raise VerificationFailure(
            "S-SCOPE", "no key may sign this payload under the trust root"
        )
    if not isinstance(envelope, dict):
        raise VerificationFailure("S-ENVELOPE", "envelope is not an object")
    if envelope.get("payloadType") != expected_payload_type:
        raise VerificationFailure(
            "S-TYPE", f"payloadType {envelope.get('payloadType')!r} not accepted"
        )
    payload_b64 = envelope.get("payload", "")
    if not isinstance(payload_b64, str):
        raise VerificationFailure("S-ENVELOPE", "payload is not base64 text")
    payload_bytes = base64.b64decode(payload_b64)
    if len(payload_bytes) > MAX_ENVELOPE_BYTES:
        raise VerificationFailure("S-SIZE", f"payload {len(payload_bytes)} bytes")

    signatures = envelope.get("signatures") or []
    good: list[str] = []
    for sig_entry in signatures:
        kid = (sig_entry or {}).get("keyid", "")
        if kid in trust_root.get("revoked_keyids", []):
            continue  # revoked: cannot count, keep scanning for a valid one
        key_doc = (trust_root.get("keys") or {}).get(kid)
        if key_doc is None or kid not in role["keyids"]:
            raise VerificationFailure(
                "S-SCOPE", f"key {kid} may not sign {expected_payload_type}"
            )
        if ts_parse(key_doc["not_after"]) <= now:
            raise VerificationFailure("S-KEY-EXPIRED", f"key {kid} expired")
        try:
            Ed25519PublicKey.from_public_bytes(
                base64.b64decode(key_doc["public"])
            ).verify(
                base64.b64decode(sig_entry["sig"]),
                # DSSE signatures cover the PAE encoding, not the bare
                # payload — reconstruct it exactly as the signer did.
                pae(expected_payload_type, payload_bytes),
            )
        except (InvalidSignature, ValueError, TypeError) as e:
            raise VerificationFailure(
                "S-SIG", f"signature by {kid} does not verify"
            ) from e
        if kid not in good:
            good.append(kid)

    threshold = role.get("threshold", 1)
    if len(good) < threshold:
        raise VerificationFailure(
            "S-THRESHOLD", f"{len(good)} of {threshold} required signatures"
        )

    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=_no_dupes,
            parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        raise VerificationFailure("S-JSON", f"payload is not strict JSON: {e}") from e
    if not isinstance(payload, dict):
        raise VerificationFailure("S-JSON", "payload is not a JSON object")
    return VerifiedPayload(payload, expected_payload_type, good)


def _no_dupes(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON keys")
    return dict(pairs)


def _bad_constant(name: str) -> None:
    raise ValueError(f"non-standard constant {name}")


# --- Sign-time bundle lint -------------------------------------------------
#
# Schema first (wire contract), then the semantic checks a JSON Schema
# cannot express. Both halves run before anything is signed; a bundle that
# fails never leaves the control plane.


def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "edge-bundle.schema.json").read_text())
    return Draft202012Validator(schema)


def validate_bundle_document(document: dict, *, now: Optional[datetime] = None) -> None:
    """Raise ``BundleValidationError`` if the bundle may not be signed.

    Pure function: no DB, no clock beyond the caller's ``now`` (tests pin
    it). This is the operator's seatbelt at signing time — the human gate
    must be hard to do carelessly (spec: bundle lint + scope preview).
    """
    now = now or utcnow()
    problems: list[str] = []

    errors = sorted(_validator().iter_errors(document), key=lambda e: list(e.path))
    problems.extend(
        f"schema: {'/'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in errors
    )
    if not isinstance(document, dict):
        raise BundleValidationError(problems or ["bundle document is not an object"])

    not_before = _ts_or_none(document.get("not_before"))
    expires_at = _ts_or_none(document.get("expires_at"))
    if not_before and expires_at:
        if expires_at <= not_before:
            problems.append("validity: expires_at must be after not_before")
        elif expires_at - not_before > MAX_BUNDLE_VALIDITY:
            problems.append(
                f"validity: window exceeds {MAX_BUNDLE_VALIDITY.days} days; "
                "bundles are re-signed, not issued forever"
            )
        elif not_before > now:
            # Legal for the daemon (it honors not_before), but a signing-time
            # surprise worth naming: the operator signed a future document.
            problems.append(
                f"validity: not_before {document['not_before']} is in the future"
            )

    version = document.get("version")
    parent = document.get("parent_version")
    if isinstance(version, int) and isinstance(parent, int) and parent >= version:
        problems.append(
            f"version: parent_version {parent} must be below version {version}"
        )

    raw_decision = document.get("decision")
    decision = raw_decision if isinstance(raw_decision, dict) else {}
    escalate = decision.get("escalate_confidence")
    auto_act = decision.get("auto_act_confidence")
    if (
        isinstance(escalate, (int, float))
        and isinstance(auto_act, (int, float))
        and escalate > auto_act
    ):
        problems.append(
            "decision: escalate_confidence must not exceed auto_act_confidence "
            "(the escalate band sits below the auto-act band)"
        )

    if problems:
        raise BundleValidationError(problems)


def _ts_or_none(value: object) -> Optional[datetime]:
    if isinstance(value, str):
        try:
            return ts_parse(value)
        except ValueError:
            return None
    return None
