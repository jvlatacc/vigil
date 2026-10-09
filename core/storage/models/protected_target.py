"""Never-quarantine invariant ORM model. Schema and rationale:
``infra/database/init/40_protected_targets.sql``."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

PROTECTED_KINDS = ("ip", "cidr", "hostname_glob", "role")
PROTECTED_ORIGINS = ("env", "operator")


class ProtectedTarget(Base):
    """One containment target unattended response may never touch."""

    __tablename__ = "protected_targets"

    target_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="operator", server_default="operator"
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    removed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    removal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('ip', 'cidr', 'hostname_glob', 'role')",
            name="ck_protected_targets_kind",
        ),
        CheckConstraint(
            "origin IN ('env', 'operator')",
            name="ck_protected_targets_origin",
        ),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)",
            name="ck_protected_targets_removal",
        ),
        Index(
            "uniq_protected_targets_active",
            "kind",
            "value",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("idx_protected_targets_created_at", text("created_at DESC")),
    )
