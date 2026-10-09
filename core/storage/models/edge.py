"""Edge node registry and signed-bundle store ORM models. Schema and
rationale: ``infra/database/init/40_edge_nodes.sql`` and
``41_edge_bundles.sql``."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

EDGE_NODE_STATUSES = ("active", "revoked")


class EdgeNode(Base):
    """One enrolled edge daemon, holding only what sync and revocation need.

    The bearer credential itself is never stored — ``credential_hash`` is the
    SHA-256 hex of it, compared constant-time on every node call. The row is
    the enrollment record, the sync cursor carrier (``last_bundle_version``),
    and the revocation target: status ``revoked`` answers every further
    authenticated call with 401, which is what makes revocation beat any
    local allowance.
    """

    __tablename__ = "edge_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The segment this daemon defends, as the operator declared it at enroll
    # (vpc, cidrs, node_selector). Policy bundles bind to the same document.
    segment_scope: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_boot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_bundle_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_edge_nodes_status"),
        CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_edge_nodes_revocation_pair",
        ),
        Index("idx_edge_nodes_status", "status"),
    )


class EdgeBundle(Base):
    """One signed policy bundle version, stored exactly as signed.

    ``envelope`` is the DSSE envelope the daemon pulls and verifies against
    its offline trust store; ``payload`` is the decoded bundle document, kept
    so the control plane can serve cursor comparisons and scope matches
    without re-verifying its own signature on every pull. A bundle never
    mutates after signing: a change is a new row at a higher version.
    """

    __tablename__ = "edge_bundles"

    bundle_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    autonomy_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    signed_by: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (Index("idx_edge_bundles_scope_version", "bundle_id", "version"),)
