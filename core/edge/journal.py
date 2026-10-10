"""The Warden decision journal: hash chain, batch verification, legality.

Both sides of the mesh import this module — Warden writes its journal with
``record_hash`` and the control plane re-computes the same hashes at
reconcile time — so the serialization is pinned here, not agreed in prose.
The formula is the agent_events pattern: ``sha256(prev_hash ‖ record)`` over
the record's canonical bytes (sorted keys, no whitespace, the chaining
``prev_hash`` field itself excluded).

Verification is fail-closed and ordered: a batch either chains exactly onto
the server-held head, or it is refused with the position to resend from.
Legality is a separate judgment, applied per record after the chain holds:
a record is merged only if the policy version it cites allowed what it did —
judged by the pack's content, never by wall time (a partitioned node's clock
is not authority; its signed policy is).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.edge.signing import deterministic_json
from core.edge.wire import parse_ts

# prev_hash of the first record ever pushed by a node — the chain's zero.
GENESIS_PREV_HASH = "0" * 64

# The canonical journal record fields, excluding prev_hash: exactly what
# record_hash covers. The wire model (services/api/routers/edge.py) forbids
# extras, so both sides hash the same content.
RECORD_FIELDS = (
    "seq",
    "ts",
    "mode",
    "idempotency_key",
    "action_type",
    "target",
    "decision_rule",
    "execution",
)


def record_hash(prev_hash: str, record: Mapping[str, Any]) -> str:
    """sha256(prev_hash ‖ canonical record bytes) — the chain link.

    ``record`` is the mapping without its ``prev_hash`` field (the hash of
    record N-1 is record N's ``prev_hash``; it cannot also cover itself).
    """
    content = {key: record[key] for key in RECORD_FIELDS if key in record}
    return hashlib.sha256(prev_hash.encode() + deterministic_json(content)).hexdigest()


def approval_row_for(
    record: Mapping[str, Any], *, node_id: str, policy_version: int
) -> dict:
    """Map a verified journal record onto the approval_actions vocabulary.

    The reconciliation contract: a merged row is the existing approval record
    with edge provenance, deduped by the idempotency_key the node already
    chose. ``source: edge`` lives in ``parameters`` (with node, policy
    version and seq) because these rows *are* machine-decided — by signed
    policy, re-checked here at merge time — and must read as such in audit.

    Execution mapping is honest about what happened: an executed record is
    ``executed``; a failed one is ``failed``; a dry run is ``pending`` with
    ``requires_approval`` — the containment did not happen, and a dry-ran
    block is exactly a decision a person should look at (the
    ``_execute_isolation`` lesson: never record a success for containment
    that never happened).
    """
    execution = record["execution"]
    status = {"executed": "executed", "failed": "failed", "dry_run": "pending"}[
        execution["status"]
    ]
    seq: int = record["seq"]
    decision_rule: str = record["decision_rule"]
    return {
        "action_id": f"edge-{node_id}-{seq:012d}"[:80],
        "action_type": record["action_type"],
        "title": f"[edge:{node_id}] {record['action_type']} {record['target']}",
        "description": decision_rule,
        "target": record["target"],
        "confidence": 0.0,
        "reason": decision_rule,
        "evidence": [],
        "requires_approval": status == "pending",
        "status": status,
        "executed_at": execution.get("at") if status == "executed" else None,
        "execution_result": execution,
        "parameters": {
            "source": "edge",
            "node_id": node_id,
            "policy_version": policy_version,
            "seq": seq,
            "mode": record["mode"],
        },
        "reversibility": "reversible",
        "idempotency_key": record["idempotency_key"],
    }


@dataclass(frozen=True)
class ChainVerdict:
    """The outcome of verifying a pushed batch against the server-held head.

    ``new_records`` are the records past the server's watermark, in order,
    each verified to chain onto the head. ``duplicate_records`` are records
    at or below the watermark — already held, never re-merged, and never
    re-verified: their content is pinned by the next record's ``prev_hash``.
    A refused batch carries a ``code`` naming what broke.
    """

    ok: bool
    code: str = ""
    detail: str = ""
    new_records: tuple[dict, ...] = ()
    duplicate_records: tuple[dict, ...] = ()
    accepted_through: int = 0
    final_head: str = ""
    # The seq the server will accept next: held head + 1 after a refusal
    # (nothing merged), accepted watermark + 1 after a successful merge.
    resend_from: int = 1


def verify_batch(
    records: list[dict],
    *,
    server_last_seq: int,
    server_head: str | None,
    claimed_head: str,
) -> ChainVerdict:
    """Verify a pushed batch chains onto the server-held head.

    ``server_head`` is ``None`` for a node with no receipts yet, in which
    case the first record must chain from ``GENESIS_PREV_HASH``. Any gap,
    break, or head disagreement refuses the whole batch — the caller answers
    409 with ``resend_from`` so the node resumes from the held position.
    Nothing here trusts the push: every link is recomputed.
    """
    if not records:
        return ChainVerdict(
            ok=False,
            code="empty-batch",
            detail="no records pushed",
            resend_from=server_last_seq + 1,
        )

    expected_prev = server_head if server_head is not None else GENESIS_PREV_HASH
    expected_seq = server_last_seq + 1
    new: list[dict] = []
    duplicates: list[dict] = []
    head = expected_prev

    for record in records:
        seq = record.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            return ChainVerdict(
                ok=False,
                code="seq-order",
                detail=f"record seq is not an integer: {seq!r}",
                resend_from=server_last_seq + 1,
            )
        if seq <= server_last_seq:
            duplicates.append(record)
            continue
        if seq != expected_seq:
            # Applies to the first new record too: a batch must resume at
            # held_head + 1, never skip forward past unheld records. The
            # whole batch is refused -- nothing merges -- so the recovery
            # position is always the server-held head + 1.
            return ChainVerdict(
                ok=False,
                code="seq-gap",
                detail=f"expected seq {expected_seq}, got {seq}",
                resend_from=server_last_seq + 1,
            )
        if record.get("prev_hash") != head:
            return ChainVerdict(
                ok=False,
                code="chain-mismatch",
                detail=f"seq {seq} does not chain onto the held head",
                resend_from=server_last_seq + 1,
            )
        head = record_hash(head, record)
        expected_seq = seq + 1
        new.append(record)

    if new and claimed_head != head:
        return ChainVerdict(
            ok=False,
            code="head-mismatch",
            detail="pushed chain_head does not match the computed head of the batch",
            resend_from=server_last_seq + 1,
        )

    final_seq = max(server_last_seq, new[-1]["seq"] if new else server_last_seq)
    return ChainVerdict(
        ok=True,
        new_records=tuple(new),
        duplicate_records=tuple(duplicates),
        accepted_through=final_seq,
        final_head=head,
        resend_from=final_seq + 1,
    )


@dataclass(frozen=True)
class RecordRejection:
    """One journal record refused at merge time, with the reason."""

    seq: int
    code: str
    detail: str


@dataclass(frozen=True)
class LegalityVerdict:
    accepted: tuple[dict, ...] = ()
    rejected: tuple[RecordRejection, ...] = field(default_factory=tuple)


def check_legality(
    records: tuple[dict, ...] | list[dict], *, allowed_actions: tuple[str, ...] | None
) -> LegalityVerdict:
    """Re-check each record against the autonomy envelope it operated under.

    ``allowed_actions`` comes from the cited policy version's signed
    envelope; ``None`` means the cited version is not one this node could
    have held (unknown or not active), which refuses every record. This is
    the server-side shadow of the node's own fail-closed ladder — the merge
    must not launder an action the signed envelope never allowed.
    """
    if allowed_actions is None:
        return LegalityVerdict(
            rejected=tuple(
                RecordRejection(
                    seq=record["seq"],
                    code="policy-version-unavailable",
                    detail="no active policy pack for the cited version",
                )
                for record in records
            )
        )
    allowed = set(allowed_actions)
    accepted: list[dict] = []
    rejected: list[RecordRejection] = []
    for record in records:
        if record["action_type"] in allowed:
            accepted.append(record)
        else:
            rejected.append(
                RecordRejection(
                    seq=record["seq"],
                    code="action-not-in-envelope",
                    detail=(
                        f"{record['action_type']} is not in the cited pack's "
                        f"allowed_actions"
                    ),
                )
            )
    return LegalityVerdict(accepted=tuple(accepted), rejected=tuple(rejected))


# --- the wire pushability gate -------------------------------------------------
#
# The frozen contract's ceilings, restated from the control plane's
# JournalRecord / JournalExecutionModel wire models (the server-side models
# stay authoritative; tests cross-check the two). The node needs this shape
# check on ITS side because a record the server would 422 is worse than an
# unpushed one: contiguity means nothing behind it could merge either, so a
# malformed record would wedge reconciliation silently and forever.

_WIRE_EXECUTION_STATUSES = frozenset({"executed", "failed", "dry_run"})


def record_wire_error(record: Mapping[str, Any]) -> str | None:
    """Why the frozen journal wire contract cannot carry ``record``, or None.

    The reconciler's pre-push gate: a record this refuses must never be
    sent — the server would refuse the whole batch (422), and with batch
    contiguity there is no way around the bad record. Field-by-field it
    mirrors the control plane's ``JournalRecord`` model, including the
    execution dict's exact key set — extras are dropped by the server's
    parser, and a dropped extra is a recomputed hash that no longer
    matches: the wedge the pin exists to prevent.
    """
    if not isinstance(record, Mapping):
        return "record is not a mapping"
    keys = set(record)
    allowed_keys = set(RECORD_FIELDS) | {"prev_hash"}
    missing = allowed_keys - keys
    if missing:
        return f"missing fields: {sorted(missing)}"
    extra = keys - allowed_keys
    if extra:
        return f"unknown fields: {sorted(extra)}"
    seq = record["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        return f"seq must be a positive integer, got {seq!r}"
    for field_name, limit in (
        ("ts", 32),
        ("mode", 32),
        ("idempotency_key", 200),
        ("action_type", 40),
        ("target", 256),
        ("decision_rule", 1000),
    ):
        value = record[field_name]
        if not isinstance(value, str) or not 1 <= len(value) <= limit:
            return f"{field_name} must be a string of 1..{limit} chars"
    try:
        parse_ts(record["ts"])
    except ValueError:
        return "ts is not a wire timestamp"
    execution = record["execution"]
    if not isinstance(execution, Mapping):
        return "execution must be an object"
    if set(execution) - {"status", "executor", "at"}:
        return "execution carries fields the wire contract drops"
    status = execution.get("status")
    if status not in _WIRE_EXECUTION_STATUSES:
        return f"execution.status must be one of {sorted(_WIRE_EXECUTION_STATUSES)}"
    executor = execution.get("executor")
    if not isinstance(executor, str) or not 1 <= len(executor) <= 100:
        return "execution.executor must be a string of 1..100 chars"
    at = execution.get("at")
    if at is not None:
        if not isinstance(at, str) or len(at) > 32:
            return "execution.at must be a wire timestamp or absent"
        try:
            parse_ts(at)
        except ValueError:
            return "execution.at is not a wire timestamp"
    prev_hash = record["prev_hash"]
    if (
        not isinstance(prev_hash, str)
        or len(prev_hash) != 64
        or any(c not in "0123456789abcdef" for c in prev_hash)
    ):
        return "prev_hash must be 64 lowercase hex chars"
    return None
