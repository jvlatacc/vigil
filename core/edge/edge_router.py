# The edge sync surface: how a daemon enrolls, pulls its signed bundle, and
# uploads its journal. Per-node bearer credentials (registry-backed) govern the
# node's own routes; the operator revocation route rides the shared internal
# token, exactly like every other /internal machine route. The router is
# mounted with include_in_schema=False: the edge fleet has no public contract,
# and /api/v1 stays frozen.

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from core.agents.internal_auth import authorise
from core.edge import bundles, events, registry, signing
from core.edge.registry import (
    AuthenticationFailed,
    EdgeNode,
    EnrollmentSecretMissing,
    EnrollmentTokenInvalid,
    NodeNotEnrolled,
)
from core.routing import Auth, RouterMeta

router = APIRouter(include_in_schema=False)

ROUTER_META = RouterMeta(
    prefix="/internal/edge",
    tags=["internal-edge"],
    auth=Auth.ROUTER_MANAGED,
    reason=(
        "Machine-to-machine edge sync: each route authenticates a per-node\n"
        "bearer credential (or, for revocation, the shared internal token)\n"
        "inside the handler; the user-session dependency does not apply.\n"
        "Reachability is the NetworkPolicy's job since ADR 0014."
    ),
)

logger = logging.getLogger(__name__)

_CREDENTIAL_SCHEME = "Bearer "


def _bearer_credential(authorization: Optional[str], what: str) -> str:
    """Extract the bearer credential, or refuse with 401."""
    if not authorization or not authorization.startswith(_CREDENTIAL_SCHEME):
        raise HTTPException(status_code=401, detail=f"missing {what} bearer credential")
    return authorization[len(_CREDENTIAL_SCHEME) :].strip()


def _authenticated_node(node_id: str, authorization: Optional[str]) -> EdgeNode:
    """Authenticate a node's own route. Unknown, revoked, and wrong
    credentials all read as 401 — no distinction an attacker could use."""
    credential = _bearer_credential(authorization, "edge node")
    try:
        return registry.authenticate_node(node_id, credential)
    except (NodeNotEnrolled, AuthenticationFailed) as e:
        logger.info("Edge node %s refused: %s", node_id, e)
        raise HTTPException(status_code=401, detail="bad or missing node credential")


class EnrollRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=44)
    enrollment_token: str = Field(..., min_length=1, max_length=512)
    segment_scope: Dict[str, Any]


class HeartbeatRequest(BaseModel):
    boot_id: Optional[str] = Field(default=None, max_length=128)
    bundle_version: Optional[int] = Field(default=None, ge=0)
    autonomy_tier: Optional[str] = Field(default=None, max_length=16)
    lease_state: Optional[str] = Field(default=None, max_length=32)
    # The node's durable-ack watermark (reconciliation exchange: acked_upto
    # in, commit_watermark back). Persisted for the drift signal.
    acked_upto: Optional[int] = Field(default=None, ge=0)


class EdgeEventBatch(BaseModel):
    events: List[Dict[str, Any]] = Field(default_factory=list)


class RevokeRequest(BaseModel):
    reason: str = Field(default="", max_length=512)


@router.post("/enroll", status_code=201)
def enroll(body: EnrollRequest) -> Dict[str, Any]:
    """Exchange a one-time enrollment token for a node credential.

    Fail closed: an unset enrollment secret is a 503 (the deployment is
    misconfigured, not the caller wrong), and an unknown, expired, or
    node-mismatched token is a 401. The credential is returned once; only
    its hash is kept.
    """
    try:
        credential = registry.enroll(
            body.node_id, body.segment_scope, body.enrollment_token
        )
    except EnrollmentSecretMissing as e:
        logger.error("Edge enrollment refused: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except EnrollmentTokenInvalid:
        # A fixed detail on purpose: nothing about the token is echoed back.
        raise HTTPException(status_code=401, detail="invalid enrollment token")
    except NodeNotEnrolled as e:
        # Only reachable here for a malformed node_id (the token has already
        # been verified) — a client-side shape problem, not an auth failure.
        raise HTTPException(status_code=400, detail=str(e))
    return {"node_id": body.node_id, "credential": credential}


@router.get("/{node_id}/policy")
def pull_policy(
    node_id: str,
    cursor: Optional[int] = None,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Cursor-keyed bundle pull. No backfill: a cold start (no cursor)
    and a stale cursor both receive the newest bundle only — never the
    version history in between."""
    node = _authenticated_node(node_id, authorization)
    latest = bundles.latest_bundle_for_node(dict(node.segment_scope))
    if latest is None:
        return {"bundle": None, "current_version": None}
    if cursor is not None and cursor >= latest.version:
        return {"bundle": None, "current_version": latest.version}
    try:
        verified = bundles.verify_stored_bundle(
            latest, signing.control_plane_trust_root()
        )
    except (bundles.BundleServiceError, signing.SigningError) as e:
        # A tampered stored row — or a deployment with no signing key —
        # is never served: the node keeps its last-known-good bundle and
        # this reads as no change. Fail closed, never serve unverified.
        logger.error(
            "Refusing to serve bundle %s v%s: %s", latest.bundle_id, latest.version, e
        )
        return {"bundle": None, "current_version": None}
    return {
        "bundle": bundles.bundle_row_to_response(latest),
        "payload": verified.payload,
        "current_version": latest.version,
    }


@router.post("/{node_id}/events")
def post_events(
    node_id: str,
    batch: EdgeEventBatch,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Upload a bounded journal batch. Acks are durable: only events that
    committed here (or were already committed) are acked, so the daemon
    can clear those journal ranges and never lose an unacked record."""
    node = _authenticated_node(node_id, authorization)
    if len(batch.events) > events.MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"batch exceeds {events.MAX_EVENTS_PER_BATCH} events",
        )
    result = events.import_events(node, batch.events)
    return {
        "acked": result.accepted,
        "duplicates": result.duplicates,
        "rejected": result.rejected,
    }


@router.post("/{node_id}/heartbeat")
def heartbeat(
    node_id: str,
    body: HeartbeatRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Liveness plus drift signal: the version the node should adopt next."""
    _authenticated_node(node_id, authorization)
    try:
        return registry.record_heartbeat(
            node_id,
            boot_id=body.boot_id,
            bundle_version=body.bundle_version,
            autonomy_tier=body.autonomy_tier,
            lease_state=body.lease_state,
            acked_upto=body.acked_upto,
        )
    except (NodeNotEnrolled, AuthenticationFailed):
        # Revoked between authentication and heartbeat: the node is gone.
        raise HTTPException(status_code=401, detail="bad or missing node credential")


@router.post("/nodes/{node_id}/revoke")
def revoke(
    node_id: str,
    body: RevokeRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Kill a node's credential. Operator surface: the shared internal
    token governs it (fail closed — unset token → 503, wrong → 401), and
    revocation propagates as 401s on the node's next sync call."""
    authorise(authorization, "edge node revocation")
    try:
        return registry.revoke_node(node_id, revoked_by="internal", reason=body.reason)
    except NodeNotEnrolled as e:
        raise HTTPException(status_code=404, detail=str(e))
