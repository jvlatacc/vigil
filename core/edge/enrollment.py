"""One-time enrollment tokens: how a Warden proves it may join the mesh.

An operator mints a token for one node identity (`mint_enrollment_token`,
or ``python -m core.edge.enrollment --node-id wn-7f3a``) and hands it to the
node out of band; the node presents it once at ``POST /api/v1/edge/enroll``
and receives its per-node bearer token. The token is HMAC over the node id
and an expiry, keyed by ``EDGE_ENROLLMENT_TOKEN`` from the secrets manager —
fail-closed 503 when unset, the ``/internal`` shared-secret posture.

"One-time" is enforced by the enrollment semantics, not by storage: the
token is bound to a single node id, and enrolling an id that already exists
is refused with 409 (a revoked node stays revoked — re-enrollment requires a
new node identity). A token therefore cannot outlive the one row it can
create, and rotating the secret kills every unspent token at once. There is
no spent-token ledger to replay against because a spent token has nothing
left to spend on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

from core.edge.wire import TS_FORMAT, strict_json_loads

# The secret's name in the secrets manager. Read per request, never at import.
ENROLLMENT_SECRET_NAME = "EDGE_ENROLLMENT_TOKEN"

# How long a minted token may sit unused before the node must ask for a
# fresh one. Short: an enrollment token is a standing invitation.
DEFAULT_TOKEN_TTL_HOURS = 24

_DOMAIN = b"vigil.edge-enroll.v1"
_PREFIX = "vigil.enroll.v1."

# The node-id charset the edge tables accept; also what the token binds.
NODE_ID_MAX_LENGTH = 50


class EnrollmentTokenError(Exception):
    """A presented enrollment token did not verify. ``code`` names why."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def validate_node_id(node_id: str) -> str:
    """Enforce the node-id charset: safe in a path, a hostname, and an id."""
    if not node_id or len(node_id) > NODE_ID_MAX_LENGTH:
        raise EnrollmentTokenError(
            "bad-node-id",
            f"node id must be 1..{NODE_ID_MAX_LENGTH} characters",
        )
    if not all(c.isalnum() or c in "-_" for c in node_id) or not node_id[0].isalnum():
        raise EnrollmentTokenError(
            "bad-node-id",
            "node id must be alphanumeric with - or _, starting alphanumeric",
        )
    return node_id


def _mac(secret: str, body: bytes) -> str:
    return hmac.new(_DOMAIN + b"\n" + secret.encode(), body, hashlib.sha256).hexdigest()


def mint_enrollment_token(
    node_id: str, *, secret: str, expires_at: datetime | None = None
) -> str:
    """Mint a one-time enrollment token bound to ``node_id``.

    ``expires_at`` defaults to now + ``DEFAULT_TOKEN_TTL_HOURS``. The caller
    supplies the secret so tests and the CLI can mint without touching the
    secrets manager.
    """
    validate_node_id(node_id)
    if not secret:
        raise EnrollmentTokenError("no-secret", "enrollment secret is empty")
    if expires_at is None:
        expires_at = _utcnow() + timedelta(hours=DEFAULT_TOKEN_TTL_HOURS)
    payload = deterministic_enroll_payload(node_id, expires_at)
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{_PREFIX}{body}.{_mac(secret, payload)}"


def deterministic_enroll_payload(node_id: str, not_after: datetime) -> bytes:
    """The exact bytes signed: node id and expiry in the edge wire format."""
    stamp = not_after.strftime(TS_FORMAT)
    return f'{{"node_id":"{node_id}","not_after":"{stamp}"}}'.encode()


def verify_enrollment_token(token: str, *, secret: str, now: datetime) -> str:
    """Verify a presented token; return the node id it binds.

    Raises ``EnrollmentTokenError`` with a recorded class for anything that
    is not exactly what ``mint_enrollment_token`` produced within the
    window: wrong key, wrong domain, edited payload, expired.
    """
    if not secret:
        raise EnrollmentTokenError("no-secret", "enrollment secret is empty")
    if not token.startswith(_PREFIX):
        raise EnrollmentTokenError("malformed", "not an edge enrollment token")
    rest = token[len(_PREFIX) :]
    body, _, presented_mac = rest.rpartition(".")
    if not body or not presented_mac:
        raise EnrollmentTokenError("malformed", "token is missing its signature")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except (ValueError, TypeError) as exc:
        raise EnrollmentTokenError(
            "malformed", f"token payload is not base64: {exc}"
        ) from exc
    if not hmac.compare_digest(_mac(secret, payload), presented_mac):
        raise EnrollmentTokenError("bad-signature", "token signature does not verify")
    try:
        doc: dict[str, Any] = strict_json_loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise EnrollmentTokenError(
            "malformed", f"token payload is not strict JSON: {exc}"
        ) from exc
    node_id = doc.get("node_id")
    not_after = doc.get("not_after")
    if not isinstance(node_id, str) or not isinstance(not_after, str):
        raise EnrollmentTokenError("malformed", "token payload is missing fields")
    validate_node_id(node_id)
    if _parse_stamp(not_after) <= now:
        raise EnrollmentTokenError("expired", f"token expired at {not_after}")
    return node_id


def _utcnow() -> datetime:
    """Aware UTC now — the enrollment clock (expiry is a signed instant)."""
    return datetime.now(UTC)


def _parse_stamp(value: str) -> datetime:
    return datetime.strptime(value, TS_FORMAT).replace(tzinfo=UTC)
