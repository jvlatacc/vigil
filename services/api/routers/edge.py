"""Edge control plane: Warden node enrollment, policy fetch, journal
reconcile — the /api/v1/edge contract of the Local Autonomy Mesh.

Two kinds of caller, each with its own fail-closed auth:

- **Warden nodes** present a per-node bearer token (``require_edge_node``),
  verified by sha256 against ``edge_nodes.token_hash``; unknown → 401,
  revoked → 403. These routes are how a node fetches its signed policy pack
  and reconciles its decision journal.
- **Operators** use the console session plus ``settings.write`` for node
  administration (list, revoke). Enrollment is its own posture: a one-time
  enrollment token minted by an operator (``core/edge/enrollment``), keyed
  by ``EDGE_ENROLLMENT_TOKEN`` — **503 when that secret is unset**, the
  ``/internal`` shared-secret precedent: an unconfigured edge surface must
  refuse, never fall open.

Reconcile semantics (POST /journal): the pushed batch must chain exactly
onto the server-held head — sha256(prev_hash ‖ record), the agent_events
pattern — else 409 with the position to resend from. Records that verify
are then re-checked against the policy version they cite and merged into
``approval_actions`` with edge provenance, deduped by ``idempotency_key``.
A record that was not legal under its cited pack is refused from the merge
(never an HTTP error — the batch's chain position still advances, so an
otherwise-honest node is not wedged; the refusal is listed in the response
and nothing is laundered into the approval table).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from core.auth.permissions import permission_gate
from core.edge.enrollment import (
    ENROLLMENT_SECRET_NAME,
    EnrollmentTokenError,
    validate_node_id,
    verify_enrollment_token,
)
from core.edge.journal import (
    approval_row_for,
    check_legality,
    verify_batch,
)
from core.edge.wire import parse_ts, strict_json_loads
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.secrets import get_secret
from core.storage.models import User
from core.storage.models.edge import EdgeJournalReceipt, EdgeNode, EdgePolicy
from core.storage.models.workflow import ApprovalAction
from core.time import utcnow
from services.api.errors import INTERNAL_ERROR_DETAIL
from services.api.middleware.auth import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/v1/edge",
    tags=["edge"],
    auth=Auth.ROUTER_MANAGED,
    legacy_prefixes=("/api/edge",),
    reason=(
        "Machine callers on both sides: Warden nodes authenticate with "
        "per-node bearer tokens verified against edge_nodes (401 unknown, "
        "403 revoked), enrollment uses a one-time HMAC token keyed by "
        "EDGE_ENROLLMENT_TOKEN (503 when unset — the /internal shared-secret "
        "posture), and node administration uses the console session plus "
        "settings.write. The shared session dependency cannot express "
        "node-token auth, so the router enforces auth per route."
    ),
)

_SHA256_HEX = r"^[0-9a-f]{64}$"


class EdgePolicyIntegrityError(Exception):
    """A stored edge_policies row no longer matches what was signed."""


# --------------------------------------------------------------------------
# Wire shapes
# --------------------------------------------------------------------------


class EnrollRequest(BaseModel):
    segment_labels: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=20
    )


class EnrollResponse(BaseModel):
    node_id: str
    token: str


class RevokeRequest(BaseModel):
    reason: Annotated[str, Field(max_length=500)] = ""


class EdgeNodeResponse(BaseModel):
    node_id: str
    segment_labels: list[str]
    status: str
    last_seen: datetime | None
    enrolled_at: datetime
    enrolled_by: str
    revoked_at: datetime | None
    revoked_by: str | None
    revocation_reason: str | None


class EdgeNodesResponse(BaseModel):
    count: int
    nodes: list[EdgeNodeResponse]


class EdgePolicyResponse(BaseModel):
    policy_version: int
    envelope: dict[str, Any]
    payload_hash: str
    not_before: datetime
    not_after: datetime


class JournalExecutionModel(BaseModel):
    status: Literal["executed", "failed", "dry_run"]
    executor: Annotated[str, Field(max_length=100)]
    at: Annotated[str | None, Field(max_length=32)] = None

    @field_validator("at")
    @classmethod
    def _at_is_wire_ts(cls, value: str | None) -> str | None:
        if value is not None:
            parse_ts(value)
        return value


class JournalRecord(BaseModel):
    """One decision in a Warden journal. The field set is frozen — it is
    exactly what ``core.edge.journal.record_hash`` covers — so extras are
    refused and both sides hash the same content."""

    model_config = {"extra": "forbid"}

    seq: int = Field(ge=1)
    ts: Annotated[str, Field(max_length=32)]
    mode: Annotated[str, Field(max_length=32)]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=200)]
    action_type: Annotated[str, Field(min_length=1, max_length=40)]
    target: Annotated[str, Field(min_length=1, max_length=256)]
    decision_rule: Annotated[str, Field(min_length=1, max_length=1000)]
    execution: JournalExecutionModel
    prev_hash: Annotated[str, Field(pattern=_SHA256_HEX)]

    @field_validator("ts")
    @classmethod
    def _ts_is_wire_ts(cls, value: str) -> str:
        parse_ts(value)
        return value


class JournalPush(BaseModel):
    model_config = {"extra": "forbid"}

    node_id: Annotated[str, Field(min_length=1, max_length=50)]
    policy_version: int = Field(ge=1)
    chain_head: Annotated[str, Field(pattern=_SHA256_HEX)]
    records: list[JournalRecord] = Field(min_length=1)


class RecordRejectionModel(BaseModel):
    seq: int
    code: str
    detail: str


class JournalResponse(BaseModel):
    accepted_through: int
    duplicate_ids: list[str]
    rejected: list[RecordRejectionModel]
    receipt_id: str | None
    merged_count: int


class ChainGapResponse(BaseModel):
    reason: str
    detail: str
    server_last_seq: int
    server_head: str | None
    resend_from: int


# --------------------------------------------------------------------------
# Auth dependencies (fail-closed)
# --------------------------------------------------------------------------


def _presented_bearer(authorization: str | None, *, kind: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=f"Missing {kind} bearer token")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail=f"Missing {kind} bearer token")
    return token


def require_enrollment_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify the one-time enrollment token and return the node id it binds.

    503 when ``EDGE_ENROLLMENT_TOKEN`` is unset — an unconfigured enrollment
    surface must refuse, the ``internal_auth`` precedent.
    """
    secret = get_secret(ENROLLMENT_SECRET_NAME)
    if not secret:
        logger.error(
            "edge enrollment refused: %s is not configured", ENROLLMENT_SECRET_NAME
        )
        raise HTTPException(
            status_code=503,
            detail="Edge enrollment is not configured",
        )
    token = _presented_bearer(authorization, kind="enrollment")
    try:
        return verify_enrollment_token(token, secret=secret, now=datetime.now(UTC))
    except EnrollmentTokenError as exc:
        raise HTTPException(
            status_code=401, detail=f"Enrollment token rejected ({exc.code})"
        ) from exc


def require_edge_node(
    session: UnitOfWorkSession,
    authorization: Annotated[str | None, Header()] = None,
) -> EdgeNode:
    """Resolve the authenticated Warden node from its per-node bearer token.

    Unknown token → 401; revoked or absent node → 403. A valid token also
    refreshes ``last_seen`` — the node heartbeat.
    """
    token = _presented_bearer(authorization, kind="edge node")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    node = session.query(EdgeNode).filter(EdgeNode.token_hash == token_hash).first()
    if node is None:
        raise HTTPException(status_code=401, detail="Unknown edge node token")
    if node.status != "active":
        raise HTTPException(status_code=403, detail="Edge node is revoked")
    node.last_seen = utcnow()
    return node


# --------------------------------------------------------------------------
# Session-backed operations (thin; the rules live in core/edge)
# --------------------------------------------------------------------------


def _node_response(node: EdgeNode) -> EdgeNodeResponse:
    return EdgeNodeResponse(
        node_id=node.node_id,
        segment_labels=list(node.segment_labels or []),
        status=node.status,
        last_seen=node.last_seen,
        enrolled_at=node.enrolled_at,
        enrolled_by=node.enrolled_by,
        revoked_at=node.revoked_at,
        revoked_by=node.revoked_by,
        revocation_reason=node.revocation_reason,
    )


def _enroll_node(
    session: UnitOfWorkSession, *, node_id: str, segment_labels: list[str]
) -> EnrollResponse:
    try:
        validate_node_id(node_id)
    except EnrollmentTokenError as exc:
        raise HTTPException(status_code=400, detail="Node id is not valid") from exc
    if session.get(EdgeNode, node_id) is not None:
        # One-time, enforced by identity: a node id exists at most once. A
        # revoked node stays revoked — re-enrollment is a new identity.
        raise HTTPException(
            status_code=409,
            detail=f"Edge node {node_id} already exists; re-enrollment requires a new identity",
        )
    token = secrets.token_urlsafe(32)
    session.add(
        EdgeNode(
            node_id=node_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            segment_labels=segment_labels,
            status="active",
            enrolled_by="enrollment-token",
        )
    )
    session.flush()
    return EnrollResponse(node_id=node_id, token=token)


def _list_nodes(session: UnitOfWorkSession) -> EdgeNodesResponse:
    rows = session.query(EdgeNode).order_by(EdgeNode.enrolled_at).all()
    return EdgeNodesResponse(
        count=len(rows), nodes=[_node_response(row) for row in rows]
    )


def _revoke_node(
    session: UnitOfWorkSession, *, node_id: str, reason: str, revoked_by: str
) -> EdgeNodeResponse:
    node = session.get(EdgeNode, node_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Edge node {node_id} is not enrolled"
        )
    if node.status == "revoked":
        return _node_response(node)  # idempotent: already revoked
    node.status = "revoked"
    node.revoked_at = utcnow()
    node.revoked_by = revoked_by[:100]
    node.revocation_reason = reason or None
    return _node_response(node)


def _active_policy(session: UnitOfWorkSession, *, node_id: str) -> EdgePolicy:
    row = (
        session.query(EdgePolicy)
        .filter(EdgePolicy.node_id == node_id, EdgePolicy.status == "active")
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail="No active policy pack for this node"
        )
    return row


def _allowed_actions(policy_row: EdgePolicy | None) -> tuple[str, ...] | None:
    """The cited pack's allowed_actions, or None when it could not have
    governed the node (unknown version, not active).

    The stored envelope is control-plane-authored, but it is still re-bound
    to what was signed before parsing: its payload must hash to the
    ``payload_hash`` recorded at signing time. A tampered or forked row
    fails integrity — 500, category detail, nothing parsed.
    """
    if policy_row is None or policy_row.status != "active":
        return None
    envelope = policy_row.envelope or {}
    payload_b64 = envelope.get("payload")
    if not isinstance(payload_b64, str):
        raise EdgePolicyIntegrityError("policy row has no payload")
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise EdgePolicyIntegrityError("policy payload is not base64") from exc
    if hashlib.sha256(payload).hexdigest() != policy_row.payload_hash:
        raise EdgePolicyIntegrityError(
            "policy payload does not match its recorded hash"
        )
    doc = strict_json_loads(payload)
    autonomy = doc.get("autonomy_envelope") or {}
    allowed = autonomy.get("allowed_actions")
    if not isinstance(allowed, list) or not all(isinstance(a, str) for a in allowed):
        raise EdgePolicyIntegrityError("policy payload has no usable allowed_actions")
    return tuple(allowed)


def _reconcile(
    session: UnitOfWorkSession, *, node: EdgeNode, push: JournalPush
) -> JournalResponse | ChainGapResponse:
    last_receipt = (
        session.query(EdgeJournalReceipt)
        .filter(EdgeJournalReceipt.node_id == node.node_id)
        .order_by(EdgeJournalReceipt.last_seq.desc())
        .first()
    )
    server_last_seq = last_receipt.last_seq if last_receipt else 0
    server_head = last_receipt.chain_head if last_receipt else None

    records = [record.model_dump() for record in push.records]
    verdict = verify_batch(
        records,
        server_last_seq=server_last_seq,
        server_head=server_head,
        claimed_head=push.chain_head,
    )
    if not verdict.ok:
        return ChainGapResponse(
            reason=verdict.code,
            detail=verdict.detail,
            server_last_seq=server_last_seq,
            server_head=server_head,
            resend_from=verdict.resend_from,
        )

    policy_row = session.get(EdgePolicy, (node.node_id, push.policy_version))
    try:
        allowed = _allowed_actions(policy_row)
    except EdgePolicyIntegrityError:
        logger.exception("edge policy integrity failure for node %s", node.node_id)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from None

    legality = check_legality(verdict.new_records, allowed_actions=allowed)

    # Seq-level replays (records at or below the held watermark) never reach
    # the merge loop — verify_batch classifies them first. Surface them here
    # so an at-least-once repush is visible in the response, alongside the
    # key-level duplicates the merge loop detects below.
    duplicate_ids: list[str] = [
        record["idempotency_key"] for record in verdict.duplicate_records
    ]
    merged_count = 0
    for record in legality.accepted:
        key: str = record["idempotency_key"]
        existing = (
            session.query(ApprovalAction)
            .filter(
                ApprovalAction.idempotency_key == key,
                ApprovalAction.status != "failed",
            )
            .first()
        )
        if existing is not None:
            duplicate_ids.append(key)
            continue
        row = _approval_row(
            record, node_id=node.node_id, policy_version=push.policy_version
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            # Concurrent insert won the idempotency race — the dedupe index
            # is the backstop; the batch continues.
            duplicate_ids.append(key)
            continue
        merged_count += 1

    receipt_id: str | None = None
    if verdict.new_records:
        first = verdict.new_records[0]["seq"]
        last = verdict.new_records[-1]["seq"]
        receipt_id = f"ejr-{node.node_id}-{first}-{last}"[:80]
        session.add(
            EdgeJournalReceipt(
                receipt_id=receipt_id,
                node_id=node.node_id,
                policy_version=push.policy_version,
                first_seq=first,
                last_seq=last,
                chain_head=verdict.final_head,
                record_count=len(verdict.new_records),
            )
        )
        session.flush()
    elif last_receipt is not None:
        receipt_id = last_receipt.receipt_id

    return JournalResponse(
        accepted_through=verdict.accepted_through,
        duplicate_ids=duplicate_ids,
        rejected=[
            RecordRejectionModel(seq=r.seq, code=r.code, detail=r.detail)
            for r in legality.rejected
        ],
        receipt_id=receipt_id,
        merged_count=merged_count,
    )


def _approval_row(record: dict, *, node_id: str, policy_version: int) -> ApprovalAction:
    """The approval_actions row for a record, with DB-ready timestamps."""
    row = approval_row_for(record, node_id=node_id, policy_version=policy_version)
    if row["executed_at"] is not None:
        row["executed_at"] = parse_ts(row["executed_at"]).replace(tzinfo=None)
    row["created_by"] = f"edge:{node_id}"[:100]
    return ApprovalAction(**row)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.post("/enroll", response_model=EnrollResponse)
def enroll(
    body: EnrollRequest,
    session: UnitOfWorkSession,
    node_id: str = Depends(require_enrollment_token),
) -> EnrollResponse:
    """Exchange a one-time enrollment token for a per-node bearer token."""
    return _enroll_node(session, node_id=node_id, segment_labels=body.segment_labels)


@router.get(
    "/nodes",
    response_model=EdgeNodesResponse,
    dependencies=[permission_gate("settings.write")],
)
def list_nodes(session: UnitOfWorkSession) -> EdgeNodesResponse:
    """List enrolled Warden nodes and their status."""
    return _list_nodes(session)


@router.post(
    "/nodes/{node_id}/revoke",
    response_model=EdgeNodeResponse,
    dependencies=[permission_gate("settings.write")],
)
def revoke_node(
    node_id: str,
    body: RevokeRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_active_user),
) -> EdgeNodeResponse:
    """Revoke a node: its bearer token stops working immediately."""
    return _revoke_node(
        session, node_id=node_id, reason=body.reason, revoked_by=current_user.username
    )


@router.get("/policy", response_model=EdgePolicyResponse)
def get_current_policy(
    session: UnitOfWorkSession,
    node: EdgeNode = Depends(require_edge_node),
) -> EdgePolicyResponse:
    """Fetch the node's current signed policy pack."""
    policy_row = _active_policy(session, node_id=node.node_id)
    return EdgePolicyResponse(
        policy_version=policy_row.policy_version,
        envelope=policy_row.envelope,
        payload_hash=policy_row.payload_hash,
        not_before=policy_row.not_before,
        not_after=policy_row.not_after,
    )


@router.post(
    "/journal",
    response_model=JournalResponse,
    responses={
        409: {"model": ChainGapResponse, "description": "Chain gap or mismatch"}
    },
)
def reconcile_journal(
    body: JournalPush,
    session: UnitOfWorkSession,
    node: EdgeNode = Depends(require_edge_node),
) -> JournalResponse | ChainGapResponse | JSONResponse:
    """Reconcile a hash-chained journal batch into approval_actions."""
    if body.node_id != node.node_id:
        raise HTTPException(
            status_code=403,
            detail="Journal node_id does not match the authenticated node",
        )
    outcome = _reconcile(session, node=node, push=body)
    if isinstance(outcome, ChainGapResponse):
        # A refused batch is a real 409 body, not a JournalResponse -- the
        # node must see reason/server position/resend_from at the top level.
        # JSONResponse in the union is the raw carrier for exactly this body;
        # the route's response_model stays JournalResponse.
        return JSONResponse(status_code=409, content=outcome.model_dump())
    return outcome
