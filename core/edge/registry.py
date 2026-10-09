"""The edge node registry: enrollment, per-node authentication, heartbeats,
revocation.

Machine auth for edge nodes follows the fail-closed shape of
``core.agents.internal_auth`` (shared internal token) but per node: an
operator mints a one-time enrollment token (HMAC keyed by
``VIGIL_EDGE_ENROLLMENT_SECRET``), the daemon exchanges it once for a bearer
credential the control plane stores only as a SHA-256 hash. Every node call
after that presents the credential; a revoked node reads exactly like an
unknown one — 401 — because revocation must beat whatever the daemon still
holds locally.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta
from typing import Any, Optional

from core.secrets import get_secret
from core.storage.models import EdgeNode
from core.time import utcnow

logger = logging.getLogger(__name__)

ENROLLMENT_SECRET_NAME = "VIGIL_EDGE_ENROLLMENT_SECRET"
#: "edge:<node_id>" must stay inside findings.data_source (VARCHAR(50)).
NODE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,43}$")
DEFAULT_ENROLLMENT_TOKEN_TTL = timedelta(days=7)
_TOKEN_PREFIX = "edge_enroll"
_ENROLLMENT_TOKEN_VERSION = "edge-enroll-v1"


class EdgeRegistryError(Exception):
    """Base for registry failures the router maps onto HTTP status codes."""


class EnrollmentSecretMissing(EdgeRegistryError):
    """VIGIL_EDGE_ENROLLMENT_SECRET unset — fail closed with 503, not 401."""


class NodeNotEnrolled(EdgeRegistryError):
    """Unknown node_id: same answer a revoked or wrong-credential node gets."""


class AuthenticationFailed(EdgeRegistryError):
    """Presented credential does not match the stored hash."""


class EnrollmentTokenInvalid(EdgeRegistryError):
    """Enrollment token forged, expired, or minted for a different node."""


def canonical_scope(scope: dict) -> str:
    """Scope documents compare by canonical form, not dict identity."""
    return json.dumps(scope, sort_keys=True, separators=(",", ":"))


def mint_enrollment_token(
    node_id: str, ttl: timedelta = DEFAULT_ENROLLMENT_TOKEN_TTL
) -> str:
    """Mint a one-time enrollment token bound to one node_id.

    Self-describing and stateless (the tool-principal pattern in
    ``core/auth/tool_principal.py``): the secret signs, nothing server-side
    stores the token, expiry rides inside it. An operator runs this, hands
    the token to the daemon's bootstrap, and the token is useless after the
    exchange or its deadline.
    """
    secret = _enrollment_secret()
    expires = int((utcnow() + ttl).timestamp())
    node = _validate_node_id(node_id)
    body = f"{node}:{expires}"
    sig = hmac.new(
        secret.encode(), f"{_ENROLLMENT_TOKEN_VERSION}:{body}".encode(), hashlib.sha256
    ).digest()
    return ".".join(
        (
            _TOKEN_PREFIX,
            urlsafe_b64encode(node.encode()).decode().rstrip("="),
            urlsafe_b64encode(str(expires).encode()).decode().rstrip("="),
            urlsafe_b64encode(sig).decode().rstrip("="),
        )
    )


def verify_enrollment_token(token: str, node_id: str) -> None:
    """Raise ``EnrollmentTokenInvalid`` unless the token is ours, unexpired,
    and minted for exactly this node."""
    secret = _enrollment_secret()
    parts = (token or "").split(".")
    if len(parts) != 4 or parts[0] != _TOKEN_PREFIX:
        raise EnrollmentTokenInvalid("malformed enrollment token")
    try:
        node = urlsafe_b64decode(parts[1] + "==").decode()
        expires = int(urlsafe_b64decode(parts[2] + "==").decode())
        sig = urlsafe_b64decode(parts[3] + "==")
    except Exception as e:  # base64 or int decode — a forged token, not a bug
        raise EnrollmentTokenInvalid("undecodable enrollment token") from e
    if node != _validate_node_id(node_id):
        raise EnrollmentTokenInvalid("token minted for a different node")
    expected = hmac.new(
        secret.encode(),
        f"{_ENROLLMENT_TOKEN_VERSION}:{node}:{expires}".encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, expected):
        raise EnrollmentTokenInvalid("bad enrollment token signature")
    if datetime.fromtimestamp(expires, tz=None) <= utcnow():
        raise EnrollmentTokenInvalid("enrollment token expired")


def enroll(node_id: str, segment_scope: dict, token: str) -> str:
    """Exchange a valid enrollment token for a node credential.

    Re-enrolling an existing node rotates its credential — the old bearer
    stops working the moment the new hash lands. Returns the plaintext
    credential, shown once; the registry keeps only its hash.
    """
    verify_enrollment_token(token, node_id)
    node = _validate_node_id(node_id)
    credential = secrets.token_urlsafe(32)
    _upsert_node(node, segment_scope, _hash_credential(credential))
    logger.info("Edge node %s enrolled (credential rotated)", node)
    return credential


def authenticate_node(node_id: str, presented_credential: Optional[str]) -> EdgeNode:
    """Return the node row, or raise the 401-flavoured errors.

    Unknown, revoked, and wrong-credential all fail here; the router maps
    each to 401 with no distinction an attacker could use.
    """
    from core.storage.connection import get_db_manager

    node = _validate_node_id(node_id)
    with get_db_manager().session_scope() as session:
        row = session.get(EdgeNode, node)
        if row is None:
            raise NodeNotEnrolled(f"edge node {node} is not enrolled")
        if row.status == "revoked":
            raise AuthenticationFailed(f"edge node {node} is revoked")
        if not presented_credential or not hmac.compare_digest(
            _hash_credential(presented_credential), row.credential_hash
        ):
            raise AuthenticationFailed(f"bad credential for edge node {node}")
        # Detach so the caller can read the row after the session closes.
        session.expunge(row)
        return row


def record_heartbeat(
    node_id: str,
    boot_id: Optional[str] = None,
    bundle_version: Optional[int] = None,
    autonomy_tier: Optional[str] = None,
    lease_state: Optional[str] = None,
) -> dict:
    """Refresh liveness and the sync cursor; report what the node should
    adopt next (drift signal: the current bundle version, when it differs)."""
    from core.storage.connection import get_db_manager

    node = _validate_node_id(node_id)
    with get_db_manager().session_scope() as session:
        row = session.get(EdgeNode, node)
        if row is None:
            raise NodeNotEnrolled(f"edge node {node} is not enrolled")
        if row.status == "revoked":
            raise AuthenticationFailed(f"edge node {node} is revoked")
        row.last_seen = utcnow()
        row.last_boot_id = boot_id or row.last_boot_id
        if bundle_version is not None:
            row.last_bundle_version = bundle_version
        current = _latest_version_for_scope(session, dict(row.segment_scope))
        return {
            "ok": True,
            "revoked": False,
            "autonomy_tier": autonomy_tier,
            "lease_state": lease_state,
            "current_bundle_version": current,
            "last_seen": row.last_seen.isoformat(),
        }


def revoke_node(node_id: str, revoked_by: str, reason: str) -> dict:
    """Kill a node's credential. Irreversible at the registry: re-enrollment
    (a fresh token) is the only way back."""
    from core.storage.connection import get_db_manager

    node = _validate_node_id(node_id)
    with get_db_manager().session_scope() as session:
        row = session.get(EdgeNode, node)
        if row is None:
            raise NodeNotEnrolled(f"edge node {node} is not enrolled")
        if row.status != "revoked":
            row.status = "revoked"
            row.revoked_at = utcnow()
            row.revoked_by = revoked_by
            row.revoke_reason = reason
        return {
            "node_id": node,
            "status": "revoked",
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }


def get_node(node_id: str) -> Optional[EdgeNode]:
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        row = session.get(EdgeNode, _validate_node_id(node_id))
        if row is not None:
            session.expunge(row)
        return row


def _enrollment_secret() -> str:
    secret = get_secret(ENROLLMENT_SECRET_NAME)
    if not secret:
        raise EnrollmentSecretMissing(f"{ENROLLMENT_SECRET_NAME} is not configured")
    return secret


def _validate_node_id(node_id: str) -> str:
    if not NODE_ID_PATTERN.match(node_id or ""):
        raise NodeNotEnrolled(
            "node_id must be 1-44 chars of [a-zA-Z0-9_-] with no leading dash"
        )
    return node_id


def _hash_credential(credential: str) -> str:
    return hashlib.sha256(credential.encode()).hexdigest()


def _upsert_node(node_id: str, segment_scope: dict, credential_hash: str) -> None:
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        row = session.get(EdgeNode, node_id)
        if row is None:
            row = EdgeNode(node_id=node_id)
            session.add(row)
        row.segment_scope = segment_scope if isinstance(segment_scope, dict) else {}
        row.credential_hash = credential_hash
        row.status = "active"
        row.revoked_at = None
        row.revoked_by = None
        row.revoke_reason = None
        row.last_seen = utcnow()


def _latest_version_for_scope(session: Any, scope: dict) -> Optional[int]:
    """Newest stored bundle version whose scope matches the node's, inside an
    open session (used by the heartbeat drift signal)."""
    from sqlalchemy import select

    from core.storage.models import EdgeBundle

    scope_text = canonical_scope(scope)
    rows = session.execute(
        select(EdgeBundle).order_by(EdgeBundle.version.desc())
    ).scalars()
    for row in rows:
        if canonical_scope(dict(row.segment_scope)) == scope_text:
            return row.version
    return None
