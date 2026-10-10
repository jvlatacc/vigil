"""Signed policy bundles: publish, store, scope-match, and serve.

The control-plane half of the bundle lifecycle (design spec art_CRPCjz0X,
"Policy bundle — what the operator actually signs"): a bundle document is
linted (``core.edge.signing.validate_bundle_document``), signed with the
DSSE stack, verified once the way a daemon would verify it, and stored
immutable at ``(bundle_id, version)``. Serving hands the stored envelope
back untouched — the daemon re-verifies against its offline trust store, so
the control plane's job is to never serve anything that would fail that
check.

Scope matching is canonical-equality on ``segment_scope`` (the same rule
the heartbeat drift signal uses in ``core.edge.registry``): a bundle binds
to every node whose operator-declared scope document matches exactly. v1
keeps this deliberately simple; node_selector subset logic is not honored
here yet.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.edge import signing
from core.edge.registry import canonical_scope
from core.storage.models import EdgeBundle
from core.time import utcnow

logger = logging.getLogger(__name__)


class BundleServiceError(Exception):
    """Base for bundle-service failures the caller maps onto HTTP codes."""


class BundleDocumentInvalid(BundleServiceError):
    """The document failed the sign-time lint — 422, nothing stored."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class BundleConflict(BundleServiceError):
    """(bundle_id, version) already stored — a bundle never mutates."""


class StoredBundleTampered(BundleServiceError):
    """A stored envelope no longer verifies or no longer matches its
    payload column. Never served; the row is evidence now."""


def publish_bundle(
    document: dict,
    private_key: signing.Ed25519PrivateKey,
    *,
    signed_by: str = "operator",
) -> EdgeBundle:
    """Lint, sign, self-verify, and store one bundle version.

    Fails closed: an invalid document is refused before any bytes are
    signed, and the freshly-signed envelope is verified against a trust
    root built from the same public key — the exact check a daemon will
    run. Returns the stored row.
    """
    try:
        signing.validate_bundle_document(document)
    except signing.BundleValidationError as e:
        raise BundleDocumentInvalid(e.problems) from e

    envelope = signing.sign_payload(document, private_key)
    public_raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    kid = signing.keyid(public_raw)
    now = utcnow()
    self_check_root = signing.build_trust_root(
        base64.b64encode(public_raw).decode(),
        version=1,
        issued_at=now,
        expires_at=now + signing.MAX_BUNDLE_VALIDITY,
    )
    try:
        signing.verify_envelope(envelope, self_check_root)
    except signing.VerificationFailure as e:
        # Signing produced something our own verifier refuses — a bug, not
        # an operator error. Refuse loudly rather than store it.
        raise BundleServiceError(
            f"freshly signed bundle failed self-verification ({e.code})"
        ) from e

    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        row = EdgeBundle(
            bundle_id=document["bundle_id"],
            version=document["version"],
            segment_scope=document["segment_scope"],
            autonomy_tier=document["autonomy_tier"],
            envelope=envelope,
            payload=document,
            signed_by=signed_by,
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as e:
            raise BundleConflict(
                f"bundle {document['bundle_id']} v{document['version']} "
                "already exists; a bundle never mutates"
            ) from e
        session.expunge(row)
        logger.info(
            "Edge bundle %s v%d published (tier %s, signed by %s, keyid %s)",
            row.bundle_id,
            row.version,
            row.autonomy_tier,
            signed_by,
            kid,
        )
        return row


def get_bundle(bundle_id: str, version: int) -> Optional[EdgeBundle]:
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        row = session.get(EdgeBundle, (bundle_id, version))
        if row is not None:
            session.expunge(row)
        return row


def latest_bundle_for_node(node_segment_scope: dict) -> Optional[EdgeBundle]:
    """The newest stored bundle whose scope matches the node's, or None.

    Canonical scope equality, newest version wins — one document per pull,
    never a history replay.
    """
    from core.storage.connection import get_db_manager

    scope_text = canonical_scope(node_segment_scope or {})
    with get_db_manager().session_scope() as session:
        rows = session.execute(
            select(EdgeBundle).order_by(EdgeBundle.version.desc())
        ).scalars()
        for row in rows:
            if canonical_scope(dict(row.segment_scope)) == scope_text:
                session.expunge(row)
                return row
    return None


def verify_stored_bundle(row: EdgeBundle, trust_root: dict) -> signing.VerifiedPayload:
    """Re-verify a stored envelope before serving it.

    Catches storage-level tampering: the signature must verify and the
    decoded payload must equal the stored payload column.
    """
    try:
        verified = signing.verify_envelope(dict(row.envelope), trust_root)
    except signing.VerificationFailure as e:
        raise StoredBundleTampered(
            f"stored bundle {row.bundle_id} v{row.version} failed verification: {e}"
        ) from e
    if verified.payload != dict(row.payload):
        raise StoredBundleTampered(
            f"stored bundle {row.bundle_id} v{row.version}: envelope payload "
            "does not match the stored document"
        )
    return verified


def bundle_row_to_response(row: EdgeBundle) -> dict:
    """The policy-pull body: envelope plus the cursor fields the daemon
    compares against its own last-known-good version."""
    return {
        "bundle_id": row.bundle_id,
        "version": row.version,
        "autonomy_tier": row.autonomy_tier,
        "envelope": dict(row.envelope),
    }


def count_bundles() -> int:
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        return int(session.execute(select(func.count(EdgeBundle.version))).scalar_one())
