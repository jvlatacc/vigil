"""Speculative-containment lease ledger ORM model.

A lease is the applied-effect record the fast-path writes when it acts before
deliberation does: what was applied, to whom, how it gets undone, and when it
expires. It lives beside ApprovalAction (the decision record) in
core/storage/models/ — the two tables answer different questions and neither
can express the other's lifecycle.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
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


def default_lease_id() -> str:
    """``lease-{ts}``, the ``action-{ts}`` idiom ApprovalService uses.

    Generated in Python so the id exists before the executor call and a crash
    mid-apply still leaves an intent row that names its lease.
    """
    return f"lease-{utcnow().strftime('%Y%m%d-%H%M%S-%f')}"


class ContainmentAction(Base):
    """Applied-effect ledger for speculative containment leases.

    ``approval_actions`` tracks decisions; this table tracks effects. The
    deterministic fast-path issues a lease for one reversible mitigation —
    bounded by ``expires_at``, undone through ``undo_payload`` — while the
    slow path keeps deliberating. The system may demote itself (rollback,
    expiry) but never promote: escalation mints a row in ``approval_actions``
    under its own human gate, and ``escalated_approval_action_id`` only points
    back at it.

    Status walks ``pending_apply -> applied -> rolled_back | escalated |
    failed``. The partial unique index admits one ACTIVE lease (pending_apply
    or applied) per idempotency key, so webhook replays and duplicate triggers
    collapse into a single row; terminal states free the key, which is what
    makes a retry after a failure possible — the partial-index idiom of
    ``approval_actions``, narrowed to the two active states.
    """

    __tablename__ = "containment_actions"

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=default_lease_id
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending_apply",
        server_default="pending_apply",
    )
    # "{action_type}:{entity_type}:{entity_id}". Unique only while the lease is
    # live; failed/rolled_back/escalated are terminal and free the key.
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Loose reference, deliberately no FK: findings are deduplicated and
    # pruned independently, and a lease must outlive the row that triggered it.
    finding_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # The rendered rule that fired and the telemetry as the gate saw it, frozen
    # at fire time — LLM triage rewrites severity minutes later, and
    # adjudication must read what the gate saw, not the mutated record.
    decision_rule: Mapped[str] = mapped_column(Text, nullable=False)
    observed: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # Executor undo token (e.g. a Cloudflare rule_id). Undo touches ONLY this.
    undo_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Shadow rows are scored and recorded but nothing was applied.
    is_shadow: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ttl_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # downgraded | ttl_expired | false_positive | operator
    rollback_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    escalated_approval_action_id: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
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
        Index(
            "uq_containment_actions_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("status IN ('pending_apply', 'applied')"),
        ),
        # The TTL sweeper's scan: every lease that is still live and past expiry.
        Index("idx_containment_actions_status_expires", "status", "expires_at"),
    )
