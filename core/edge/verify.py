"""Offline verification for edge policy packs: trust nothing until it verifies.

Ported from the Medic trust pattern (services/medic/contracts/trust_check.py —
same DSSE v1 envelopes, same keyid derivation, same strictness) with the edge
content types. The trust root is baked into the Warden image at build time and
updated only by a newer root signed by the current root role; there is no
network, no transparency log, no OCSP, so verification behaves identically on
a partitioned node.

The ordering is the load-bearing property: verify_envelope() parses only the
small, fixed-shape envelope, and the payload NEVER — signature verification
runs on raw bytes, so a tampered or forged pack is refused without its
contents being parsed at all. Only after a signature verifies does the caller
hand the payload to policy.parse_policy().
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator

from core.edge import EDGE_TRUST_ROOT
from core.edge.wire import parse_ts, strict_json_loads

HERE = Path(__file__).parent
_TRUST_SCHEMA = json.loads((HERE / "trust.schema.json").read_text())
ENVELOPE = Draft202012Validator(_TRUST_SCHEMA)
ROOT = Draft202012Validator(
    {
        "$schema": _TRUST_SCHEMA["$schema"],
        "$defs": _TRUST_SCHEMA["$defs"],
        "$ref": "#/$defs/trust_root",
    }
)

# An edge policy is small structured JSON — the manifest names a model by hash,
# it does not carry one — so 1 MiB of envelope is already misuse.
MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_ROOT_LIFETIME_DAYS = 400

# Role lookup order; payload types are disjoint so at most one matches.
_ROLES = ("policies", "root")


@dataclass
class Verified:
    """The outcome of envelope verification.

    Either the raw payload bytes (unparsed, untrusted) with who signed them,
    or the rejection classes that refused them. ``errors`` is a list of
    (class, detail): the class is what callers record and alert on, the
    detail is for the operator reading the log.
    """

    errors: list[tuple[str, str]] = field(default_factory=list)
    payload: bytes | None = None
    payload_type: str | None = None
    role: str | None = None
    signed_by: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def codes(self) -> set[str]:
        return {code for code, _ in self.errors}


def keyid(public_raw: bytes) -> str:
    """First 32 hex of sha256(raw 32-byte public key) — the Medic derivation."""
    return hashlib.sha256(public_raw).hexdigest()[:32]


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding: binds the type to the bytes."""
    ptype = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(ptype), ptype, len(payload), payload)


def _role_for(root: dict, payload_type: str) -> tuple[str, dict] | None:
    for name in _ROLES:
        role = root["roles"][name]
        if payload_type in role["payload_types"]:
            return name, role
    return None


def _check_sigs(
    env: dict, payload: bytes, root: dict, role: dict, now: datetime
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (distinct valid keyids, per-signature failure reasons)."""
    message = pae(env["payloadType"], payload)
    good: list[str] = []
    reasons: list[tuple[str, str]] = []
    for sig in env["signatures"]:
        kid = sig["keyid"]
        if kid in root["revoked_keyids"]:
            reasons.append(("S-REVOKED", f"key {kid} is revoked"))
            continue
        if kid not in role["keyids"] or kid not in root["keys"]:
            reasons.append(("S-SCOPE", f"key {kid} may not sign {env['payloadType']}"))
            continue
        key = root["keys"][kid]
        if parse_ts(key["not_after"]) <= now:
            reasons.append(
                ("S-KEY-EXPIRED", f"key {kid} expired at {key['not_after']}")
            )
            continue
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key["public"])).verify(
                base64.b64decode(sig["sig"]), message
            )
        except (InvalidSignature, ValueError):
            reasons.append(("S-SIG", f"signature by {kid} doesn't verify"))
            continue
        if kid not in good:
            good.append(kid)
    return good, reasons


def verify_envelope(
    data: bytes, root: dict, *, expected: set[str], now: datetime
) -> Verified:
    """Verify an import before anything parses its payload.

    ``expected``: payload types the caller accepts here (a policy fetch passes
    ``{EDGE_POLICY}``; the root-updater passes ``{EDGE_TRUST_ROOT}``). Every
    refusal carries a class; a refused payload is never parsed — the caller
    sees errors, not content.
    """
    res = Verified()
    err = res.errors.append
    if parse_ts(root["expires_at"]) <= now:
        err(
            (
                "S-ROOT-EXPIRED",
                f"trust root v{root['version']} expired; bake a newer one or upgrade Vigil",
            )
        )
        return res
    if len(data) > MAX_ENVELOPE_BYTES:
        err(("S-SIZE", f"{len(data)} bytes"))
        return res
    try:
        env = strict_json_loads(data)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        err(("S-JSON", str(exc)[:120]))
        return res
    if isinstance(env, dict) and "format" in env and "payloadType" not in env:
        # A bare, unsigned pack — the payload of an envelope, handed over raw.
        err(("S-UNSIGNED", "unsigned content is refused"))
        return res
    errors = list(ENVELOPE.iter_errors(env))
    if errors:
        err(("S-ENVELOPE", errors[0].message[:150]))
        return res
    ptype = env["payloadType"]
    if ptype not in expected:
        err(("S-TYPE", f"{ptype} is not accepted here"))
        return res
    found = _role_for(root, ptype)
    if found is None or not found[1]["keyids"]:
        err(
            (
                "S-SCOPE",
                f"no key may sign {ptype} under trust root v{root['version']}",
            )
        )
        return res
    name, role = found
    try:
        payload = base64.b64decode(env["payload"])
    except ValueError as exc:
        err(("S-ENVELOPE", f"payload is not valid base64: {str(exc)[:100]}"))
        return res
    good, reasons = _check_sigs(env, payload, root, role, now)
    if len(good) < role["threshold"]:
        res.errors.extend(reasons)
        if good or not reasons:
            err(
                (
                    "S-THRESHOLD",
                    f"{len(good)} of {role['threshold']} required signatures",
                )
            )
        return res
    res.payload, res.payload_type, res.role, res.signed_by = payload, ptype, name, good
    return res


def update_trust_root(current: dict, data: bytes, *, now: datetime) -> Verified:
    """Accept a newer trust root only if the current root role AND (when it
    changed) the new root role each sign it with their threshold, the version
    goes up, and no revoked key is un-revoked."""
    res = verify_envelope(data, current, expected={EDGE_TRUST_ROOT}, now=now)
    if not res.ok:
        if res.codes & {
            "S-SIG",
            "S-THRESHOLD",
            "S-SCOPE",
            "S-REVOKED",
            "S-KEY-EXPIRED",
        }:
            res.errors.append(
                (
                    "S-ROOT-THRESHOLD",
                    "not signed by the current root role's threshold",
                )
            )
        return res
    payload = res.payload
    if payload is None:  # pragma: no cover - ok implies a payload is set
        return Verified(errors=[("S-INTERNAL", "verified payload missing")])
    try:
        new = strict_json_loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        return Verified(errors=[("S-JSON", str(exc)[:120])])
    errors = list(ROOT.iter_errors(new))
    if errors:
        return Verified(errors=[("S-ROOT-SCHEMA", errors[0].message[:150])])
    out = Verified(
        payload=payload,
        payload_type=EDGE_TRUST_ROOT,
        role="root",
        signed_by=res.signed_by,
    )
    if new["version"] <= current["version"]:
        out.errors.append(
            (
                "S-ROOT-VERSION",
                f"v{new['version']} is not newer than v{current['version']}",
            )
        )
    if not set(current["revoked_keyids"]) <= set(new["revoked_keyids"]):
        out.errors.append(("S-ROOT-UNREVOKE", "a revoked key can never be un-revoked"))
    issued, expires = parse_ts(new["issued_at"]), parse_ts(new["expires_at"])
    if (
        not issued < expires
        or (expires - issued).days > MAX_ROOT_LIFETIME_DAYS
        or expires <= now
    ):
        out.errors.append(
            (
                "S-ROOT-EXPIRED",
                "trust root lifetime invalid, over 400 days, or already expired",
            )
        )
    if set(new["roles"]["root"]["keyids"]) != set(current["roles"]["root"]["keyids"]):
        good, _ = _check_sigs(json.loads(data), payload, new, new["roles"]["root"], now)
        if len(good) < new["roles"]["root"]["threshold"]:
            out.errors.append(
                (
                    "S-ROOT-THRESHOLD",
                    "a root rotation must also be signed by the new root role's threshold",
                )
            )
    return out


def load_root(data: bytes, *, now: datetime) -> dict:
    """Load the trust root baked into the image. Like a TUF root, it must carry
    its own root role's threshold of signatures (checked here, not just at
    build time — a corrupted bake refuses to boot rather than trust silently)."""
    env = strict_json_loads(data)
    if list(ENVELOPE.iter_errors(env)) or env["payloadType"] != EDGE_TRUST_ROOT:
        raise ValueError("not a trust-root envelope")
    payload = base64.b64decode(env["payload"])
    root = strict_json_loads(payload)
    errors = list(ROOT.iter_errors(root))
    if errors:
        raise ValueError(errors[0].message)
    good, _ = _check_sigs(env, payload, root, root["roles"]["root"], now)
    if len(good) < root["roles"]["root"]["threshold"]:
        raise ValueError("trust root is not signed by its own root role's threshold")
    return root
