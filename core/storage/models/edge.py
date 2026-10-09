"""Local Autonomy Mesh ORM models: edge nodes, signed policies, journal
receipts. Schema and rationale: ``infra/database/init/40_edge_nodes.sql``,
``41_edge_policies.sql``, ``42_edge_journal_receipts.sql``."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

EDGE_NODE_STATUSES = ("active", "revoked")
EDGE_POLICY_STATUSES = ("draft", "active", "revoked")


class EdgeNode(Base):
    """One enrolled Warden runtime the control plane can issue, recognize,
    and revoke. ``token_hash`` is sha256 over the per-node bearer token — the
    token itself is never stored."""

    __tablename__ = "edge_nodes"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    segment_labels: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("ARRAY[]::text[]"),
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    enrolled_by: Mapped[str] = mapped_column(String(100), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_edge_nodes_status",
        ),
        CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_edge_nodes_revocation",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name="ck_edge_nodes_revoked_by",
        ),
        Index("uniq_edge_nodes_token_hash", "token_hash", unique=True),
        Index("idx_edge_nodes_status", "status"),
    )


class EdgePolicy(Base):
    """A signed containment-policy pack as distributed to one node. The
    primary key (node_id, policy_version) makes the version stream monotonic
    per node; at most one row per node is 'active'."""

    __tablename__ = "edge_policies"

    node_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("edge_nodes.node_id", ondelete="CASCADE"),
        primary_key=True,
    )
    policy_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signing_key_ids: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    not_before: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'revoked')",
            name="ck_edge_policies_status",
        ),
        CheckConstraint(
            "(status IN ('active', 'revoked')) = (activated_at IS NOT NULL)",
            name="ck_edge_policies_activation",
        ),
        CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_edge_policies_revocation",
        ),
        CheckConstraint(
            "not_before <= not_after",
            name="ck_edge_policies_window",
        ),
        Index(
            "uniq_edge_policies_active_per_node",
            "node_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_edge_policies_status", "status"),
    )


class EdgeJournalReceipt(Base):
    """One verified batch of a Warden journal: the accepted record range, the
    policy version the records cite, and the chain head the next push resumes
    from. The unique range makes a re-pushed batch resolve to this receipt."""

    __tablename__ = "edge_journal_receipts"

    receipt_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("edge_nodes.node_id", ondelete="CASCADE"), nullable=False
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_head: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "last_seq >= first_seq",
            name="ck_edge_journal_receipts_range",
        ),
        CheckConstraint(
            "record_count >= 1",
            name="ck_edge_journal_receipts_count",
        ),
        Index(
            "uniq_edge_journal_receipts_node_range",
            "node_id",
            "first_seq",
            "last_seq",
            unique=True,
        ),
        Index(
            "idx_edge_journal_receipts_node_last_seq",
            "node_id",
            text("last_seq DESC"),
        ),
    )
