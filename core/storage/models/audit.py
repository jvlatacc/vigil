"""The tool-call audit model: one append-only, hash-chained row per call.

The DDL it mirrors is ``infra/database/init/41_tool_call_audit.sql``; the
hash-chain trigger and the ``vigil_app`` grants live there. The Python writer
and verifier are ``core.audit.tool_calls`` — this file is only the shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from core.storage.models.base import Base
from core.time import utcnow


class ToolCallAudit(Base):
    """One tool call, allowed or denied, and who was behind it.

    Deny is a first-class decision, not an error path: a call Vigil refused
    earns the same row as one it ran, which is what makes "who tried tool X on
    system Y at time Z" answerable even when the answer is "nobody was
    allowed to".
    """

    __tablename__ = "tool_call_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )

    # Who ran it: the verified local user, or "agent" when no person was bound
    # (the convention tools.mcp.vigil.CALLER_UNAUTHENTICATED records). The IdP
    # subject rides along once federation populates it; until then it is NULL
    # and the username is the whole identity a row asserts.
    actor_username: Mapped[str] = mapped_column(Text, nullable=False)
    idp_subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Where the call entered and what it named. Enforcement rows (agent,
    # mcp-inbound) record a permission decision; dispatch rows (mcp-client,
    # in-process, vstrike) record what the far side received and answered.
    # The vocabulary lives in core.audit.tool_calls.
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    server_name: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)

    # The arguments by digest, never in the clear: an audit trail records that
    # a call happened, not a second copy of whatever was fed to it.
    args_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    args_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    decision: Mapped[str] = mapped_column(Text, nullable=False)
    deny_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Correlation: the OTEL trace the call sits inside, and the agent run that
    # drove it when the dispatcher sent one.
    trace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # The chain. Written by the writer and recomputed by the BEFORE-INSERT
    # trigger; the caller's values are never trusted on a database that has
    # the trigger.
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_tool_call_audit_ts", "ts"),
        Index("idx_tool_call_audit_actor", "actor_username"),
        Index("idx_tool_call_audit_server_tool", "server_name", "tool_name"),
    )
