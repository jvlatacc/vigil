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
