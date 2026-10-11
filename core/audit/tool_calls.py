"""The audit writer for tool calls, and the hash-chain verifier.

One module for both halves of the accountability record: writing the row a
call earns (``record_tool_call``) and proving the stored chain still holds
(``verify_chain``). The hash formula exists here in Python and again in the
BEFORE-INSERT trigger (``41_tool_call_audit.sql``); on a database with the
trigger the trigger's answer is the one that lands, and the integration suite
asserts the two agree, so a formula that drifts is caught, not absorbed.

Failure handling is the point: the writer raises. A deny whose row cannot be
written does not become a quieter denial, and an allowed call whose row cannot
be written does not return a success nobody can account for — the call fails,
closed, and the error is in the log.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.storage.models import ToolCallAudit
from core.storage.unit_of_work import unit_of_work

logger = logging.getLogger(__name__)

# Where a call entered. The writer is shared by all of them, which is why the
# vocabulary is defined here rather than at any one door. The first two are
# enforcement points — a permission decision is made there, so deny rows are
# possible. The rest are execution points — the call is dispatched there, so
# the row carries what the far side actually received and answered.
SURFACE_AGENT = "agent"
SURFACE_MCP_INBOUND = "mcp-inbound"

# Outbound vendor dispatch (core/integrations/mcp/client.py): the funnel every
# vendor MCP tool call passes through on its way down the stdio pipe.
SURFACE_MCP_CLIENT = "mcp-client"

# Vigil's own tools, called in this process (core/integrations/mcp/in_process.py).
SURFACE_IN_PROCESS = "in-process"

# Outbound VStrike REST and MCP calls (core/integrations/vstrike/client.py).
# VStrike sees the service account; the acting Vigil user is the row's actor.
SURFACE_VSTRIKE = "vstrike"

# What the two decisions are called. Deny is a recorded outcome, not an error
# path — the reason it happened rides in deny_reason.
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"

# The actor recorded when no person is bound behind the call — a hunt, a
# daemon. Same convention as tools.mcp.vigil.CALLER_UNAUTHENTICATED, restated
# rather than imported: core cannot import tools/ (import-linter contract).
ACTOR_AGENT = "agent"

# The fields the hash binds, in the one order the trigger and this module must
# agree on. Deliberately not ts: a timezone-aware timestamp has no one spelling
# across engines, and the chain links rows by id regardless — the ledger's
# hash binds the payload alone for the same reason.
_HASH_FIELDS = (
    "actor_username",
    "idp_subject",
    "surface",
    "server_name",
    "tool_name",
    "args_sha256",
    "args_bytes",
    "decision",
    "deny_reason",
    "outcome",
    "duration_ms",
    "trace_id",
    "run_id",
)

# ASCII unit separator: a byte that cannot appear in any field (usernames,
# server and tool names, digests, reasons are all printable text), so two
# different rows cannot render as the same text and the canonical form is
# unambiguous without length-prefixing.
_FIELD_SEPARATOR = "\x1f"


def hash_args(
    args: Optional[Mapping[str, Any]],
) -> tuple[Optional[str], Optional[int]]:
    """The arguments, as a sha256 digest and a byte length.

    The row says a call with these arguments happened; it never says what the
    arguments were — an audit trail is not a second copy of the data a tool
    was fed, which can hold credentials and case content.
    """
    if args is None:
        return None, None
    canonical = json.dumps(
        args, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), len(canonical)


def current_trace_id() -> Optional[str]:
    """The OTEL trace the call sits inside, or None when telemetry is off.

    Telemetry failing to import is the same as it being disabled: the audit
    row still lands, with the trace id left empty. Correlation is a strength
    the row carries, never a condition the write imposes.
    """
    try:
        from opentelemetry import trace
    except Exception:  # noqa: BLE001 — no telemetry package, no trace id
        return None
    context = trace.get_current_span().get_span_context()
    # An int trace id is the API's contract (0 when there is no trace).
    # Anything else — an instrumented stand-in, a non-standard tracer — is
    # telemetry Vigil cannot read, which is the same as it being off.
    trace_id = getattr(context, "trace_id", None)
    if not isinstance(trace_id, int) or trace_id == 0:
        return None
    return f"{trace_id:032x}"


def _field(value: Any) -> str:
    """The canonical spelling of one field: empty for NULL, decimal for ints."""
    return "" if value is None else str(value)


def canonical_row(row: Any) -> str:
    """The row's content, as the one text the hash is taken over.

    Public so the integration suite can compare this against the database
    trigger's own canonical function on a real row.
    """
    return _FIELD_SEPARATOR.join(_field(getattr(row, name)) for name in _HASH_FIELDS)


def row_event_hash(prev_hash: str, canonical: str) -> str:
    """The chain step: sha256 over the previous row's hash and this row."""
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def record_tool_call(
    *,
    actor_username: str,
    surface: str,
    server_name: str,
    tool_name: str,
    args: Optional[Mapping[str, Any]] = None,
    decision: str = DECISION_ALLOW,
    deny_reason: Optional[str] = None,
    outcome: Optional[str] = None,
    duration_ms: Optional[int] = None,
    idp_subject: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> ToolCallAudit:
    """Write the one row this call earns, and commit it before returning.

    Raises on failure — never swallows. Callers write the row where the
    verified caller, the tool id and the arguments coexist: the deny row
    before the 403 is raised, the allow row after the call answers. A write
    that fails fails the call: the error is logged by the propagating
    exception, and the caller does not read an unaudited success.

    ``actor_username`` is the verified local user, or ``ACTOR_AGENT`` when no
    person is bound. ``idp_subject`` rides along when the session carries one.
    """
    args_sha256, args_bytes = hash_args(args)
    with unit_of_work(session) as s:
        tail = s.execute(
            select(ToolCallAudit.event_hash).order_by(ToolCallAudit.id.desc()).limit(1)
        ).scalar()
        row = ToolCallAudit(
            actor_username=actor_username,
            idp_subject=idp_subject,
            surface=surface,
            server_name=server_name,
            tool_name=tool_name,
            args_sha256=args_sha256,
            args_bytes=args_bytes,
            decision=decision,
            deny_reason=deny_reason,
            outcome=outcome,
            duration_ms=duration_ms,
            trace_id=trace_id,
            run_id=run_id,
            prev_hash=tail or "",
        )
        # Recomputed by the trigger on a database that has one; computed here
        # so the row is verifiable the moment it exists anywhere else. Under
        # concurrency the trigger is the authority — the writer's prev_hash
        # can be stale by the time the insert lands, and the trigger's is not.
        row.event_hash = row_event_hash(row.prev_hash, canonical_row(row))
        s.add(row)
        s.flush()
        return row


@dataclass(frozen=True)
class ChainVerification:
    """The chain's answer: whether every row links, and where it first breaks."""

    ok: bool
    checked: int
    # The id of the first row whose hash does not hold, when not ok.
    broken_at: Optional[int]


def verify_chain(session: Optional[Session] = None) -> ChainVerification:
    """Recompute every row's hash and check each link to the one before it.

    A row whose content was edited in place stops matching its own hash, and
    every hash after it stops matching its prev_hash — one verification
    catches either. Reads every row, ordered by id; this is an audit action,
    not a hot path.
    """
    with unit_of_work(session) as s:
        rows = (
            s.execute(select(ToolCallAudit).order_by(ToolCallAudit.id)).scalars().all()
        )
        prev_hash = ""
        for row in rows:
            if row.prev_hash != prev_hash:
                return ChainVerification(ok=False, checked=len(rows), broken_at=row.id)
            if row.event_hash != row_event_hash(prev_hash, canonical_row(row)):
                return ChainVerification(ok=False, checked=len(rows), broken_at=row.id)
            prev_hash = row.event_hash
    return ChainVerification(ok=True, checked=len(rows), broken_at=None)
