"""Compiled triage policy ORM models. Schema and rationale:
``infra/database/init/40_compiled_policies.sql``, governance in
``docs/adr/0001-jit-policy-fast-path.md``."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow

POLICY_STATES = ("candidate", "shadow", "active", "suspended", "retired")
POLICY_MODES = ("shadow", "active")
DECISION_OUTCOMES = ("applied", "shadow_logged", "no_match")
AGREEMENT_SOURCES = ("llm", "analyst")


class CompiledPolicy(Base):
    """One version of one compiled triage policy.

    Rows are never deleted: ``retired`` is terminal and kept for audit. The
    composite primary key is (policy_id, version) — a new compile of the same
    archetype issues a new version, and every decision names the version and
    content hash it ran under.
    """

    __tablename__ = "compiled_policies"

    policy_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", server_default="candidate"
    )
    # The versioned condition tree: what the evaluator runs and every export
    # renderer projects.
    policy_ir: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    maturity_evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)

    compiled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    compiled_by: Mapped[str] = mapped_column(
        String(100), nullable=False, default="system", server_default="system"
    )

    promoted_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspended_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rearmed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rearmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('candidate', 'shadow', 'active', 'suspended', 'retired')",
            name="ck_compiled_policies_state",
        ),
        CheckConstraint("version >= 1", name="ck_compiled_policies_version_positive"),
        CheckConstraint(
            "(promoted_at IS NULL) = (promoted_by IS NULL)",
            name="ck_compiled_policies_promoted",
        ),
        CheckConstraint(
            "(suspended_at IS NULL) = (suspended_by IS NULL)",
            name="ck_compiled_policies_suspended",
        ),
        CheckConstraint(
            "(rearmed_at IS NULL) = (rearmed_by IS NULL)",
            name="ck_compiled_policies_rearmed",
        ),
        CheckConstraint(
            "(retired_at IS NULL) = (retired_by IS NULL)",
            name="ck_compiled_policies_retired",
        ),
        CheckConstraint(
            "state <> 'active' OR promoted_at IS NOT NULL",
            name="ck_compiled_policies_active_has_promotion",
        ),
        CheckConstraint(
            "state <> 'suspended' OR suspended_at IS NOT NULL",
            name="ck_compiled_policies_suspended_has_record",
        ),
        CheckConstraint(
            "state <> 'retired' OR retired_at IS NOT NULL",
            name="ck_compiled_policies_retired_has_record",
        ),
        Index("idx_compiled_policies_state", "state"),
    )


class CompiledPolicyDecision(Base):
    """One fast-path evaluation of one finding: hit or miss, shadow or active.

    Written for every evaluation so the shadow window and the drift counters
    see the same rows the audit sees. ``policy_id``/``policy_version``/
    ``content_hash``/``mode``/``decision`` are NULL on a no-match row, whose
    ``outcome`` is ``no_match``. The agreement columns are backfilled when the
    eventual LLM or analyst result exists.
    """

    __tablename__ = "compiled_policy_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(String(50), nullable=False)

    policy_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)

    decision: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    actual_decision: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    agreement_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    agrees: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    evaluation_us: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id"],
            ["findings.finding_id"],
            ondelete="CASCADE",
            name="fk_compiled_policy_decisions_finding",
        ),
        ForeignKeyConstraint(
            ["policy_id", "policy_version"],
            ["compiled_policies.policy_id", "compiled_policies.version"],
            ondelete="RESTRICT",
            name="fk_compiled_policy_decisions_policy",
        ),
        CheckConstraint(
            "mode IN ('shadow', 'active')",
            name="ck_compiled_policy_decisions_mode",
        ),
        CheckConstraint(
            "outcome IN ('applied', 'shadow_logged', 'no_match')",
            name="ck_compiled_policy_decisions_outcome",
        ),
        CheckConstraint(
            "(outcome = 'no_match') = (policy_id IS NULL)",
            name="ck_compiled_policy_decisions_no_match",
        ),
        CheckConstraint(
            "(mode IS NULL) = (outcome = 'no_match')",
            name="ck_compiled_policy_decisions_mode_outcome",
        ),
        CheckConstraint(
            "agreement_source IN ('llm', 'analyst')",
            name="ck_compiled_policy_decisions_agreement_source",
        ),
        CheckConstraint(
            "(agrees IS NULL) = (actual_decision IS NULL) "
            "AND (agreement_source IS NULL) = (actual_decision IS NULL)",
            name="ck_compiled_policy_decisions_agreement_pairing",
        ),
        CheckConstraint(
            "evaluation_us >= 0",
            name="ck_compiled_policy_decisions_evaluation_us_nonnegative",
        ),
        Index(
            "idx_compiled_policy_decisions_policy",
            "policy_id",
            text("evaluated_at DESC"),
        ),
        Index(
            "idx_compiled_policy_decisions_finding",
            "finding_id",
            text("evaluated_at DESC"),
        ),
    )
