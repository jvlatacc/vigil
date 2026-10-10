"""Cryptographic origin validation for findings (#944).

A finding's confidence can drive automated containment, so an adversary who
cannot breach a host can still aim the Responder: spoofed traffic makes a DNS
server look like the attacker, and the webhook's bearer token authenticates
the transport, not the content's origin. Findings therefore carry a DSSE
envelope with an Ed25519 signature; the webhook verifies it at ingest and
stamps the finding ``origin_verified``/``origin_id``. The guard chain reads
those stamps at decision time and holds unverified evidence for a person.

This mirrors ``services/medic/contracts/trust_check.py`` — strict JSON (no
duplicate keys, no non-standard constants), the DSSE v1 pre-authentication
encoding, scoped trust roots, key expiry, revocation, an envelope size cap,
and the error-tuple shape. The duplication is deliberate: the import fence
forbids ``core`` importing ``services``, so the verifier cannot be shared,
and parity with the Medic verifier is tested in
``tests/unit/response/test_origin.py``.

Wire format (an HTTP header value, JSON):

    {"payload_type": "https://vigil.example/schemas/finding/v1",
     "payload": "<base64 canonical finding JSON>",
     "signatures": [{"keyid": "sensor-edge-01", "sig": "<base64 Ed25519>",
                     "iat": 1760000000, "jti": "<nonce>"}]}

The signature covers the PAE of the full payload, so it cannot be transplanted
onto different content; the caller additionally binds the verified payload to
the body it stores via :func:`attestation_covers`. ``iat`` may be at most 300 s
old and 60 s in the future; ``jti`` nonces are remembered in an
:class:`OriginReplayCache`. Trust roots come from ``DAEMON_TRUSTED_ORIGINS``
(origin id, base64 Ed25519 public key, scope, enabled) — config-only for v1.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Iterable, Mapping, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.ingestion.dedup import RedisDedupSet
from core.response.guards_config import GuardConfig
from core.time import utcnow

logger = logging.getLogger(__name__)
# Failures land on their own logger so a deployment can route, alert or retain
# them independently of the daemon's chatter: a flood of these lines is the
# spoofing flood itself.
security_logger = logging.getLogger("vigil.security.origin")

FINDING_PAYLOAD_TYPE = "https://vigil.example/schemas/finding/v1"
EXPECTED_PAYLOAD_TYPES = frozenset({FINDING_PAYLOAD_TYPE})

# The HTTP header carrying the envelope on the daemon webhook path.
ATTESTATION_HEADER = "X-Vigil-Origin-Attestation"

# aiohttp's server caps one header field at 8190 bytes, so an attestation past
# ~8 KiB cannot arrive on the wire anyway — refuse it here with a code instead
# of a protocol-level 431 the sender cannot parse. Findings too large to
# attest ingest unverified and wait for a person; that is the safe side.
MAX_ATTESTATION_BYTES = 8 * 1024
# The spec's staleness bound: an ``iat`` older than this cannot vouch for a
# decision being made now, because the replay window it protects is over.
MAX_IAT_AGE_SECONDS = 300
# A future ``iat`` is a pre-signed attestation — reject beyond a small skew
# allowance for sender clocks.
MAX_IAT_FUTURE_SKEW_SECONDS = 60
# The replay cache must outlive the staleness bound with margin, so a replay
# is caught by the nonce before age could ever excuse it.
REPLAY_TTL_SECONDS = 3600

# Error codes, mirroring trust_check's ``S-`` family with an origin ``O-``.
O_SIZE = "O-SIZE"
O_JSON = "O-JSON"
O_ENVELOPE = "O-ENVELOPE"
O_TYPE = "O-TYPE"
O_UNKNOWN = "O-UNKNOWN"
O_REVOKED = "O-REVOKED"
O_KEY_EXPIRED = "O-KEY-EXPIRED"
O_SCOPE = "O-SCOPE"
O_STALE = "O-STALE"
O_CLOCK = "O-CLOCK"
O_SIG = "O-SIG"
O_REPLAY = "O-REPLAY"
O_COVERAGE = "O-COVERAGE"


class OriginConfigError(ValueError):
    """A trusted-origin entry cannot be honored as configured (#944).

    A ``ValueError`` so callers that treat one as "configuration error, stop
    verifying" need no second except clause, matching ``GuardConfigError``.
    """


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding: binds the type to the bytes.

    Byte-for-byte the same encoding as Medic's ``trust_check.pae``; the
    parity test proves it rather than trusting the comment.
    """
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def _no_dupes(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON keys")
    return dict(pairs)


def _bad_constant(name: str) -> None:
    raise ValueError(f"non-standard constant {name}")


def _strict_json(data: bytes):
    """Parse like trust_check: duplicate keys and NaN/Infinity refuse to parse."""
    return json.loads(
        data.decode("utf-8"), object_pairs_hook=_no_dupes, parse_constant=_bad_constant
    )


@lru_cache(maxsize=64)
def _public_key(public_b64: str) -> Ed25519PublicKey:
    raw = base64.b64decode(public_b64, validate=True)
    if len(raw) != 32:
        raise OriginConfigError(
            f"public_key decodes to {len(raw)} bytes, expected a raw 32-byte"
            " Ed25519 key"
        )
    return Ed25519PublicKey.from_public_bytes(raw)


@dataclass(frozen=True)
class OriginTrustRoot:
    """One trusted origin from ``DAEMON_TRUSTED_ORIGINS``.

    ``scope`` names what the origin may attest for (``*`` is any); the guard
    chain reads it via :meth:`OriginTrustIndex.scope_of` to decide whether an
    origin is scoped for auto-response. ``enabled=False`` is revocation.
    """

    origin_id: str
    public_key: str
    scope: str = "*"
    enabled: bool = True
    not_after: Optional[datetime] = None

    @classmethod
    def from_entry(cls, entry: Any, *, index: int) -> "OriginTrustRoot":
        if not isinstance(entry, dict):
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}]: expected a JSON object"
            )
        origin_id = entry.get("origin_id")
        if not isinstance(origin_id, str) or not origin_id.strip():
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}]: expected a non-empty"
                " origin_id string"
            )
        public_key = entry.get("public_key")
        if not isinstance(public_key, str) or not public_key.strip():
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}] ({origin_id}): expected a"
                " base64 public_key string"
            )
        try:
            _public_key(public_key)
        except OriginConfigError as exc:
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}] ({origin_id}): {exc}"
            ) from exc
        except (ValueError, TypeError) as exc:
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}] ({origin_id}): public_key is"
                f" not decodable base64 ({exc})"
            ) from exc

        scope = entry.get("scope", "*")
        if not isinstance(scope, str) or not scope.strip():
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}] ({origin_id}): expected a"
                " non-empty scope string"
            )
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise OriginConfigError(
                f"daemon_trusted_origins[{index}] ({origin_id}): expected"
                " enabled to be a boolean"
            )
        raw_not_after = entry.get("not_after")
        not_after: Optional[datetime] = None
        if raw_not_after is not None:
            try:
                not_after = datetime.fromisoformat(str(raw_not_after))
            except ValueError as exc:
                raise OriginConfigError(
                    f"daemon_trusted_origins[{index}] ({origin_id}): not_after"
                    f" is not an ISO-8601 timestamp ({exc})"
                ) from exc
        return cls(
            origin_id=origin_id,
            public_key=public_key,
            scope=scope,
            enabled=enabled,
            not_after=not_after,
        )


@dataclass
class OriginVerification:
    """Mirror of trust_check's ``Verified``: error tuples plus what verified.

    ``ok`` is exactly "no errors" — a result with a payload but also an error
    is never treated as verified.
    """

    errors: list[tuple[str, str]] = field(default_factory=list)
    payload: Optional[bytes] = None
    payload_type: Optional[str] = None
    origin_id: Optional[str] = None
    nonces: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def codes(self) -> set[str]:
        return {code for code, _ in self.errors}


def _envelope_shape_error(env: Any) -> Optional[str]:
    """The first structural problem with an attestation envelope, or None."""
    if not isinstance(env, dict):
        return "expected a JSON object"
    payload_type = env.get("payload_type")
    if not isinstance(payload_type, str) or not payload_type:
        return "expected a non-empty payload_type string"
    payload = env.get("payload")
    if not isinstance(payload, str) or not payload:
        return "expected a base64 payload string"
    signatures = env.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        return "expected a non-empty signatures list"
    for position, sig in enumerate(signatures):
        if not isinstance(sig, dict):
            return f"signatures[{position}]: expected a JSON object"
        if not isinstance(sig.get("keyid"), str) or not sig.get("keyid"):
            return f"signatures[{position}]: expected a non-empty keyid string"
        if not isinstance(sig.get("sig"), str) or not sig.get("sig"):
            return f"signatures[{position}]: expected a base64 sig string"
        # A bool is an int subclass in Python; a True timestamp is not one.
        if isinstance(sig.get("iat"), bool) or not isinstance(sig.get("iat"), int):
            return f"signatures[{position}]: expected an integer epoch iat"
        if not isinstance(sig.get("jti"), str) or not sig.get("jti"):
            return f"signatures[{position}]: expected a non-empty jti string"
    return None


def verify_attestation(
    data: bytes,
    roots: Mapping[str, OriginTrustRoot],
    *,
    now: datetime,
    expected: frozenset[str] = EXPECTED_PAYLOAD_TYPES,
    required_scope: Optional[str] = None,
) -> OriginVerification:
    """Verify an attestation envelope against the trusted origins.

    Ordering mirrors ``trust_check.verify_envelope``: size, strict JSON,
    shape, payload type, then per-signature registration, revocation, scope,
    key expiry, freshness and crypto — cheapest and most specific first.
    Replay rejection is the caller's, because it needs a stateful cache; the
    caller marks only nonces from signatures that verified here.
    """
    res = OriginVerification()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    def err(code: str, detail: str) -> None:
        res.errors.append((code, detail))

    if len(data) > MAX_ATTESTATION_BYTES:
        err(O_SIZE, f"{len(data)} bytes")
        return res
    try:
        env = _strict_json(data)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        err(O_JSON, str(exc)[:120])
        return res
    shape_error = _envelope_shape_error(env)
    if shape_error is not None:
        err(O_ENVELOPE, shape_error)
        return res
    payload_type = env["payload_type"]
    if payload_type not in expected:
        err(O_TYPE, f"{payload_type} is not accepted here")
        return res
    try:
        payload = base64.b64decode(env["payload"])
    except (ValueError, TypeError) as exc:
        err(O_ENVELOPE, f"payload is not decodable base64 ({exc})")
        return res

    good: list[str] = []
    for sig in env["signatures"]:
        kid = sig["keyid"]
        root = roots.get(kid)
        if root is None:
            err(O_UNKNOWN, f"key {kid} is not a registered origin")
            continue
        if not root.enabled:
            err(O_REVOKED, f"origin {kid} is disabled")
            continue
        if required_scope is not None and root.scope not in ("*", required_scope):
            err(O_SCOPE, f"origin {kid} may not attest {required_scope}")
            continue
        if root.not_after is not None and root.not_after <= now:
            err(O_KEY_EXPIRED, f"origin {kid} expired at {root.not_after.isoformat()}")
            continue
        age = now.timestamp() - sig["iat"]
        if age > MAX_IAT_AGE_SECONDS:
            err(O_STALE, f"signed {int(age)}s ago (limit {MAX_IAT_AGE_SECONDS}s)")
            continue
        if age < -MAX_IAT_FUTURE_SKEW_SECONDS:
            err(
                O_CLOCK,
                f"signed {int(-age)}s in the future (limit"
                f" {MAX_IAT_FUTURE_SKEW_SECONDS}s)",
            )
            continue
        try:
            _public_key(root.public_key).verify(
                base64.b64decode(sig["sig"]), pae(payload_type, payload)
            )
        except (InvalidSignature, ValueError, TypeError):
            err(O_SIG, f"signature by {kid} doesn't verify")
            continue
        if kid not in good:
            good.append(kid)
        if sig["jti"] not in res.nonces:
            res.nonces.append(sig["jti"])

    if not good:
        return res
    res.payload, res.payload_type, res.origin_id = payload, payload_type, good[0]
    return res


def attestation_covers(verdict: OriginVerification, body: Any) -> bool:
    """True when the verified payload is the content being ingested.

    The signature binds the exact payload bytes; this binds those bytes to
    the request body, so a valid attestation cannot be transplanted onto
    different findings. JSON equality, not byte equality: a sender may
    serialize the signed copy differently from the transport copy.
    """
    if verdict.payload is None:
        return False
    try:
        attested = _strict_json(verdict.payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return False
    return attested == body


class OriginTrustIndex:
    """Memory-resident view of the operator's trusted origins.

    Built once from ``DAEMON_TRUSTED_ORIGINS`` at daemon boot; config-only
    for v1, so there is nothing to invalidate at runtime — a change is a
    daemon restart, the way ``ResponseConfig`` treats thresholds.
    """

    def __init__(self, roots: Mapping[str, OriginTrustRoot]):
        self._roots = dict(roots)

    @classmethod
    def from_entries(cls, entries: Iterable[Any]) -> "OriginTrustIndex":
        roots: dict[str, OriginTrustRoot] = {}
        for index, entry in enumerate(entries):
            root = OriginTrustRoot.from_entry(entry, index=index)
            if root.origin_id in roots:
                raise OriginConfigError(
                    f"daemon_trusted_origins[{index}]: duplicate origin_id"
                    f" {root.origin_id}"
                )
            roots[root.origin_id] = root
        return cls(roots)

    @classmethod
    def from_settings(cls, settings: Any = None) -> "OriginTrustIndex":
        """Bridge the seed list the way ``ResponseConfig`` bridges the band."""
        config = GuardConfig.from_settings(settings)
        return cls.from_entries(config.trusted_origins)

    @classmethod
    def empty(cls) -> "OriginTrustIndex":
        return cls({})

    def __len__(self) -> int:
        return len(self._roots)

    @property
    def roots(self) -> Mapping[str, OriginTrustRoot]:
        return dict(self._roots)

    def scope_of(self, origin_id: str) -> Optional[str]:
        """The origin's scope, for the guard chain's auto-response scoping."""
        root = self._roots.get(origin_id)
        return root.scope if root is not None else None

    def verify(
        self,
        data: bytes,
        *,
        now: Optional[datetime] = None,
        expected: frozenset[str] = EXPECTED_PAYLOAD_TYPES,
        required_scope: Optional[str] = None,
    ) -> OriginVerification:
        return verify_attestation(
            data,
            self._roots,
            now=now or utcnow(),
            expected=expected,
            required_scope=required_scope,
        )


class OriginReplayCache:
    """Replay rejection for attestation nonces, on the ``RedisDedupSet`` shape.

    Namespaced key, TTL-bounded, in-memory fallback with logged degradation.
    Nonces live one hour — long past the 300 s staleness bound — so a replay
    is caught by the nonce before age could excuse it. In fallback mode a
    daemon restart forgets recent nonces; the staleness bound still rejects
    everything older than five minutes, which bounds what a restart re-opens.
    """

    def __init__(
        self,
        *,
        namespace: str = "origin-attestation:jti",
        redis_url: Optional[str] = None,
        ttl_seconds: int = REPLAY_TTL_SECONDS,
    ):
        self._dedup = RedisDedupSet(
            namespace, redis_url=redis_url, ttl_seconds=ttl_seconds
        )

    async def seen_or_record(self, jti: str) -> bool:
        """True when this nonce was already used (a replay)."""
        if not jti:
            return False
        if await self._dedup.is_processed(jti):
            return True
        await self._dedup.mark_processed(jti)
        return False
