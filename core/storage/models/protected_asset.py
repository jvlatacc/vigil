"""Protected asset ORM model. Schema and rationale:
``infra/database/init/40_protected_assets.sql``."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

MATCH_KINDS = ("ip", "cidr", "hostname")
ASSET_CLASSES = (
    "dns",
    "domain_controller",
    "gateway",
    "dhcp",
    "database",
    "other",
)


class ProtectedAsset(Base):
    """One asset the Responder must never auto-contain against (#944)."""

    __tablename__ = "protected_assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    match_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    match_value: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    removed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    removal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "match_kind IN ('ip', 'cidr', 'hostname')",
            name="ck_protected_assets_match_kind",
        ),
        CheckConstraint(
            "asset_class IN ('dns', 'domain_controller', 'gateway', 'dhcp',"
            " 'database', 'other')",
            name="ck_protected_assets_asset_class",
        ),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)",
            name="ck_protected_assets_removal",
        ),
        Index(
            "uniq_protected_assets_active",
            "match_kind",
            text("lower(match_value)"),
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("idx_protected_assets_created_at", text("created_at DESC")),
    )
