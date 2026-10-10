"""Deception lease-registry and probe-log ORM models. Schema and rationale:
``infra/database/init/40_deception_tables.sql``.

The lease row is the one place the daemon, the API and the console can all
see a redirect (the daemon and API are separate processes), and the probe
log is what corroboration counts over. Neither is ever deleted: released
leases are the audit trail, and probes age out only through the sweep's
prune.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
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

# A lease is born pending (approval row written, backend not yet steered),
# goes active on steer success, and leaves only to released or failed.
# pending/active are the non-terminal states the sweep and the executor
# reconcile; released/failed are terminal and keep their audit columns.
LEASE_STATUSES = ("pending", "active", "released", "failed")


class DeceptionLease(Base):
    """One attacker's redirect lease — the durable per-attacker state."""

    __tablename__ = "deception_leases"

    lease_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    attacker_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    # The approval row that authorized this lease; the audit join. The
    # approval_actions table is the record of record, so the FK only SETs
    # NULL on the theoretical day an approval is purged.
    action_id: Mapped[Optional[str]] = mapped_column(
        String(80),
        ForeignKey("approval_actions.action_id", ondelete="SET NULL"),
        nullable=True,
    )
    destination_ips: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    ports: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    backend: Mapped[str] = mapped_column(
        String(40), nullable=False, default="dry_run", server_default="dry_run"
    )
    backend_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ttl_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default="3600"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    renewal_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    release_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The unsteer outcome: {success, backend_ref, error?, message?} — the
    # executor_result pattern applied to rollback.
    rollback_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'released', 'failed')",
            name="ck_deception_leases_status",
        ),
        CheckConstraint(
            "(status IN ('released', 'failed')) = (released_at IS NOT NULL)",
            name="ck_deception_leases_released",
        ),
        Index(
            "idx_deception_leases_status_expires",
            "status",
            "expires_at",
        ),
        Index("idx_deception_leases_attacker_ip", "attacker_ip"),
    )


class DeceptionProbe(Base):
    """One recon observation from a source — the corroboration evidence."""

    __tablename__ = "deception_probes"

    probe_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    source_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    # Distinct per finding: a re-delivered finding is one observation.
    finding_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "idx_deception_probes_source_created",
            "source_ip",
            "created_at",
        ),
        Index("idx_deception_probes_created_at", text("created_at DESC")),
    )
