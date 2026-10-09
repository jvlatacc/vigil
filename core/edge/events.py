"""Import of edge journal batches into the control plane.

Two destinations, one idempotency rule each:

- Observation, revert, and offline-window records become findings with
  ``data_source="edge:<node_id>"`` and ``external_id=<event_id>``, so the
  existing ``(data_source, external_id)`` uniqueness is the replay dedup.
  The derived ``finding_id`` is a pure function of that pair, which makes a
  replayed event land on the same row even if the pre-check misses it.
- Action records become approval-pipeline rows marked executed, with the
  edge actor as the named approver. The house rule holds: a confidence
  score never decides alone — the row records *who* acted (the bundle-
  named edge principal), not just how confident the daemon was.

Both paths are idempotent per ``event_id``: replaying a batch the daemon
already uploaded reports duplicates, never duplicate rows. That is the
"durably acked" fact the daemon needs before it clears its journal
ranges, so acks are only returned for events that committed (or were
already committed) here.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.response.approval_service import (
    ActionType,
    ApprovalService,
    Reversibility,
)
from core.storage.connection import get_db_manager
from core.storage.models import EdgeNode, Finding

logger = logging.getLogger(__name__)

#: Batch shape — the route enforces the count; the importer re-checks so the
#: service is safe for non-route callers too.
MAX_EVENTS_PER_BATCH = 500
MAX_EVENT_PAYLOAD_BYTES = 65_536
MAX_EVENT_ID_LENGTH = 128

#: Journal record kinds the control plane understands. Anything else is a
#: rejected event, not a crash — the daemon's journal may outgrow this
#: vocabulary while it was partitioned.
OBSERVATION = "observation"
ACTION = "action"
REVERT = "revert"
OFFLINE_WINDOW = "offline_window"
EVENT_KINDS = frozenset({OBSERVATION, ACTION, REVERT, OFFLINE_WINDOW})

#: Edge-executable action types, mirroring the bundle's allowed_actions.
#: Everything else is refused with a per-event reason, not a batch failure.
_ACTION_TYPES = {
    "block_ip": ActionType.BLOCK_IP,
    "block_domain": ActionType.BLOCK_DOMAIN,
}

_FINDING_ID_PREFIX = "edge-"


@dataclass(frozen=True)
class EventImportResult:
    """Per-event outcome of one batch import.

    ``accepted`` and ``duplicates`` are both durably-acked: the daemon may
    clear those journal ranges on receipt. ``rejected`` events are told
    apart so the daemon can quarantine them locally instead of retrying.
    """

    accepted: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def import_events(node: EdgeNode, events: list[dict]) -> EventImportResult:
    """Import one bounded journal batch for an authenticated node."""
    result = EventImportResult()
    if len(events) > MAX_EVENTS_PER_BATCH:
        raise ValueError(
            f"batch of {len(events)} events exceeds {MAX_EVENTS_PER_BATCH}"
        )

    source = finding_source_for(node.node_id)
    approvals = ApprovalService()
    committed_sequences: list[int] = []
    for event in events:
        event_id, reason = _validate_event(event)
        if reason is not None:
            result.rejected.append({"event_id": event_id or "", "reason": reason})
            continue
        try:
            if event["kind"] == ACTION:
                _import_action(node, source, event_id, event, approvals, result)
            else:
                _import_finding(source, event_id, event, result)
        except SQLAlchemyError as e:
            # One bad event never poisons the batch: the rest still land,
            # and the failure is reported per event rather than swallowed.
            logger.warning("Edge event %s failed import: %s", event_id, e)
            result.rejected.append({"event_id": event_id, "reason": "import_failed"})
            continue
        sequence = event.get("local_sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            committed_sequences.append(sequence)
    # The watermark advances only here — after every per-event session has
    # committed and before the response is built, so an acked event is a
    # committed event. A max, never a subtraction: gaps (evicted or
    # rejected records) resolve on replay, they do not hold the watermark.
    _advance_commit_watermark(node, committed_sequences)
    return result


def _advance_commit_watermark(node: EdgeNode, sequences: list[int]) -> None:
    """Move the node's commit_watermark to the highest sequence in this
    batch, durably. Monotonic max: never ahead of what actually committed,
    never behind what the node already uploaded."""
    if not sequences:
        return
    candidate = max(sequences)
    try:
        with get_db_manager().session_scope() as session:
            row = session.get(EdgeNode, node.node_id)
            if row is None or (
                row.commit_watermark is not None and row.commit_watermark >= candidate
            ):
                return
            row.commit_watermark = candidate
    except SQLAlchemyError as exc:
        # A lagging watermark never blocks the ack: the events committed and
        # the next batch re-advances the max.
        logger.warning("commit watermark update failed for %s: %s", node.node_id, exc)


def finding_source_for(node_id: str) -> str:
    """The finding ``data_source`` for a node — bounded for the column.

    ``node_id`` is registry-validated to at most 44 characters, so the
    prefix keeps us inside ``findings.data_source``'s 50.
    """
    source = f"edge:{node_id}"
    if len(source) > 50:  # pragma: no cover - registry validation should bind this
        raise ValueError(f"edge node id too long for findings.data_source: {node_id}")
    return source


def _finding_id(source: str, event_id: str) -> str:
    """Deterministic row id for an (source, external_id) pair.

    Replay lands on the same row even when the pre-select misses (two
    concurrent deliveries of one event race the uniqueness index, and the
    loser counts the row as a duplicate rather than crashing the batch).
    """
    digest = hashlib.sha256(f"{source}:{event_id}".encode()).hexdigest()
    return f"{_FINDING_ID_PREFIX}{digest[:40]}"


def _validate_event(event: Any) -> tuple[str, Optional[str]]:
    """Shape-check one journal record; (event_id, reason-or-None)."""
    if not isinstance(event, dict):
        return "", "event must be a JSON object"
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not 0 < len(event_id) <= MAX_EVENT_ID_LENGTH:
        return "", f"event_id must be a string of at most {MAX_EVENT_ID_LENGTH}"
    if event_id.strip() != event_id or not event_id.isprintable():
        return event_id, "event_id must be printable with no surrounding whitespace"
    if event.get("kind") not in EVENT_KINDS:
        return event_id, f"kind must be one of {sorted(EVENT_KINDS)}"
    if _parse_timestamp(event.get("occurred_at")) is None:
        return event_id, "occurred_at must be an ISO-8601 timestamp"
    payload = event.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return event_id, "payload must be a JSON object"
    if len(json.dumps(payload, default=str).encode()) > MAX_EVENT_PAYLOAD_BYTES:
        return event_id, f"payload exceeds {MAX_EVENT_PAYLOAD_BYTES} bytes"
    sequence = event.get("local_sequence")
    if sequence is not None and (
        isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0
    ):
        return event_id, "local_sequence must be a non-negative integer"
    if event["kind"] == ACTION:
        action = event.get("action")
        if not isinstance(action, dict):
            return event_id, "action events require an action object"
        if action.get("action_type") not in _ACTION_TYPES:
            return event_id, f"action_type must be one of {sorted(_ACTION_TYPES)}"
        target = action.get("target")
        if not isinstance(target, str) or not 0 < len(target) <= 255:
            return event_id, "action.target must be a string of at most 255"
    return event_id, None


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed


def _import_finding(
    source: str, event_id: str, event: dict, result: EventImportResult
) -> None:
    """Import one observation/revert/offline-window record as a finding."""
    kind = event["kind"]
    payload = event.get("payload") or {}
    occurred_at = _parse_timestamp(event["occurred_at"])
    with get_db_manager().session_scope() as session:
        existing = session.execute(
            select(Finding).where(
                Finding.data_source == source,
                Finding.external_id == event_id,
            )
        ).first()
        if existing is not None:
            result.duplicates.append(event_id)
            return
        severity = payload.get("severity")
        finding = Finding(
            finding_id=_finding_id(source, event_id),
            data_source=source,
            external_id=event_id,
            title=str(payload.get("title") or f"edge {kind}"),
            description=payload.get("description") or json.dumps(payload, default=str),
            severity=(
                severity
                if severity in ("info", "low", "medium", "high", "critical")
                else "info"
            ),
            status="new",
            timestamp=occurred_at,
            entity_context={"event_kind": kind, "node": source},
            evidence_links=[],
        )
        try:
            session.add(finding)
            session.flush()
        except IntegrityError:
            # The (data_source, external_id) uniqueness backstop: a racing
            # double delivery. The row exists; that is a duplicate, not an
            # error — and never a second row.
            session.rollback()
            result.duplicates.append(event_id)
            return
    result.accepted.append(event_id)


def _import_action(
    node: EdgeNode,
    source: str,
    event_id: str,
    event: dict,
    approvals: ApprovalService,
    result: EventImportResult,
) -> None:
    """Import one executed edge action as an approval row with provenance.

    The daemon already acted under its signed bundle; the import records
    reality. The edge actor is the named approver (never a bare score),
    the idempotency key makes replays return the same row, and the
    executed row lands in the same surface the analyst already watches.
    """
    action = event["action"]
    payload = event["payload"]
    actor = str(payload.get("actor") or f"edge:{node.node_id}")
    idempotency_key = f"edge:{node.node_id}:{event_id}"
    # _put_action (not create_action) because the inserted flag is the
    # replay-dedup signal — same precedent as autonomous_response_service.
    # human_only=True pins the row at PENDING so approve_action below is the
    # step that names the edge actor: an already-approved insert would skip
    # it, leaving an executed row with approved_by NULL — a score deciding
    # alone, the exact thing the pipeline refuses.
    pending, inserted = approvals._put_action(
        action_type=_ACTION_TYPES[str(action["action_type"])],
        title=str(action.get("title") or f"edge {action['action_type']}"),
        description=str(action.get("description") or payload.get("rule") or ""),
        target=str(action["target"]),
        confidence=_bounded_confidence(action.get("confidence")),
        reason=str(payload.get("rule") or "edge bundle action"),
        evidence=[str(payload.get("journal_digest") or source)],
        created_by=source,
        parameters={
            "executor": action.get("executor"),
            "ttl_seconds": action.get("ttl_seconds"),
            "node_id": node.node_id,
            "event_id": event_id,
            "occurred_at": event["occurred_at"],
        },
        reversibility=Reversibility.REVERSIBLE,
        idempotency_key=idempotency_key,
        human_only=True,
        annotate_rule=False,
    )
    if not inserted:
        result.duplicates.append(event_id)
        return
    executed = approvals.approve_action(pending.action_id, approved_by=actor)
    if executed is None:
        result.rejected.append({"event_id": event_id, "reason": "action_not_imported"})
        return
    if (
        approvals.mark_executed(
            pending.action_id,
            {
                "source": "edge-import",
                "node_id": node.node_id,
                "event_id": event_id,
                "executor": action.get("executor"),
                "reverted": bool(payload.get("reverted")),
            },
        )
        is None
    ):
        result.rejected.append(
            {"event_id": event_id, "reason": "execution_not_recorded"}
        )
        return
    result.accepted.append(event_id)


def _bounded_confidence(value: Any) -> float:
    """Daemon-reported confidence, clamped into the pipeline's domain.

    Out-of-range garbage becomes the band floor rather than a crash or a
    forged 1.0 — the edge is untrusted input to this pipeline too.
    """
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))
