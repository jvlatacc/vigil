"""Moving-target-defense decoy registry ORM models. Schema and rationale:
``infra/database/init/40_mtd_decoy_registry.sql``."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

DECOY_KINDS = ("ssh", "http")
DECOY_STATUSES = ("active", "retired")
MTD_EXCLUSION_STATUSES = ("active", "removed")


class MtdDecoyRegistry(Base):
    """One decoy service honey-routing may sinkhole attacker flows into.

    A registry row is a routing target, not a running thing: the decoy
    workloads themselves live in the deployment (compose profile, Helm
    Deployment), this table is what the decision plane may pick from.
    Retirement is recorded, not deleted, so "what did we route into last
    month" stays answerable; the partial unique index lets a new decoy
    reuse a retired name.
    """

    __tablename__ = "mtd_decoy_registry"

    decoy_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # The name the deployment knows the decoy by (compose service, Helm
    # Deployment) — what an operator cross-references against the stack.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # What the decoy pretends to be; the decision plane picks by kind.
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    # Where the decoy is reached: host/port of the service behind it.
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    # A pointer into the credential store (core.secrets / integration
    # config), never the credential: a decoy holds canary values only, and
    # the registry must not become the leak path for them.
    canary_credential_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    # Last canary rotation. NULL until the first rotation runs.
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("kind IN ('ssh', 'http')", name="ck_mtd_decoy_registry_kind"),
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_mtd_decoy_registry_status",
        ),
        Index(
            "uniq_mtd_decoy_registry_active_name",
            "name",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # Decoy selection reads "an active decoy of this kind".
        Index("idx_mtd_decoy_registry_kind_status", "kind", "status"),
    )


class MtdIpExclusion(Base):
    """One address the MTD decision plane must never honey-route.

    The mirror image of ``IpExclusion`` (which hides an address from the
    findings queue): this hides an address from the decoys. Production
    hosts an analyst names here fall back to the normal response path.

    Removal is recorded, not deleted — a status transition, active to
    removed, with who and when — so "was this address ever protected from
    routing" survives the removal. At most one active row per address;
    listing it again after removal is a new row with its own reason.
    """

    __tablename__ = "mtd_ip_exclusions"

    exclusion_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # Canonical text form (Python's ipaddress: lower-case, compressed
    # IPv6), one address per row, no ranges — same discipline as
    # ip_exclusions.
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    # Why it must not be routed. Required: a never-route entry nobody can
    # explain is one nobody dares remove.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    added_by: Mapped[str] = mapped_column(String(100), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    # Set together with the status transition to 'removed'; the check
    # constraint below keeps the two from disagreeing.
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    removed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'removed')",
            name="ck_mtd_ip_exclusions_status",
        ),
        CheckConstraint(
            "(status = 'active') = (removed_at IS NULL)",
            name="ck_mtd_ip_exclusions_status_removal",
        ),
        Index(
            "uniq_mtd_ip_exclusions_active_ip",
            "ip",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_mtd_ip_exclusions_added_at", text("added_at DESC")),
    )
