"""Console API for compiled policies: inspect, lifecycle, decisions, exports.

Console-only by design (ADR ``docs/adr/0001-jit-policy-fast-path.md``, locked
decision 6): this router is mounted automatically by router discovery (it is a
``core/**/*_router.py`` module) with ``Auth.REQUIRED``, and is deliberately
**not** part of the frozen ``core/api/v1`` contract — the policy lifecycle is
console-side governance, not an external API promise. The deny-by-default
security gate (``tests/security/test_route_auth_coverage.py``) covers every
route here automatically; ``tests/unit/policy_compiler/test_policies_router.py``
asserts the v1 absence explicitly and sweeps every route for a 401 when
unauthenticated.

Lifecycle edges (locked decision 3 — human re-arm through shadow, terminal
retirement):

- ``promote``: shadow → active. The only edge that removes human friction, and
  it is a human one: ``get_current_user`` resolves a signed-in session and
  refuses MCP credentials, so the actor is a person, never a program token.
- ``suspend``: shadow|active → suspended. The human stop button; the drift
  auto-brake lands in the same state.
- ``rearm``: suspended → shadow — never straight to active; re-promotion
  after review is a second, explicit promote.
- ``retire``: any non-retired state → retired. Terminal, kept for audit.

Candidate → shadow is not exposed here: that edge belongs to the compile
validation gate in the maturity job, not to a console button.

Every transition stamps the row's actor/timestamp columns (the audit surface
the storage model defines) and appends a ``ConfigAuditLog`` row, so who moved
which (policy id, version) against which content hash is reconstructable. The
IR is validated through :meth:`PolicyIR.from_dict` on every read — the same
load-time tamper check the evaluator applies; a row whose stored document does
not validate answers 500 rather than rendering or evaluating garbage.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, field_validator

from core.auth.current_user import get_current_user
from core.auth.permissions import permission_gate
from core.policy_compiler.models import PolicyIR, PolicyValidationError
from core.policy_compiler.renderers import render
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import ConfigAuditLog, User
from core.storage.models.policy_compiler import (
    POLICY_STATES,
    CompiledPolicy,
    CompiledPolicyDecision,
)
from core.time import utcnow

router = APIRouter()

# Lifecycle mutations are human-acted system-governance writes: the same
# administration grant the console's Settings/autonomy surfaces require
# (``_SETTINGS_WRITE`` in services/api/routers/config.py). No ``policies.*``
# permission exists in the role vocabulary yet; inventing one would 403 every
# seeded role until role management changes.
_LIFECYCLE_WRITE = [permission_gate("settings.write")]

ROUTER_META = RouterMeta(
    prefix="/api/compiled-policies",
    tags=["compiled-policies"],
    auth=Auth.REQUIRED,
)

# The export targets — the same set the renderer module ships, spelled as a
# Literal so a bad ``format`` is a 422 at validation, never a render fallback.
ExportFormat = Literal["rego", "snort", "suricata", "iptables"]

_EXPORT_EXTENSION = {
    "rego": "rego",
    "snort": "rules",
    "suricata": "rules",
    "iptables": "conf",
}

# The lifecycle state machine: action -> (allowed source states, target state).
_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "promote": (frozenset({"shadow"}), "active"),
    "suspend": (frozenset({"shadow", "active"}), "suspended"),
    "rearm": (frozenset({"suspended"}), "shadow"),
    "retire": (frozenset(POLICY_STATES) - {"retired"}, "retired"),
}

# Where each action stamps the actor and when, per the storage model's
# lifecycle columns.
_TRANSITION_COLUMNS = {
    "promote": ("promoted_by", "promoted_at"),
    "suspend": ("suspended_by", "suspended_at"),
    "rearm": ("rearmed_by", "rearmed_at"),
    "retire": ("retired_by", "retired_at"),
}


class LifecycleRequest(BaseModel):
    """Body for a lifecycle transition: which version, against which hash.

    ``content_hash`` is optional optimistic concurrency: a console that loaded
    the policy earlier sends the hash it saw, and a transition against a row
    that has since been recompiled (or otherwise changed) answers 409 instead
    of moving a version the actor was not looking at.
    """

    version: int
    content_hash: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _version_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be >= 1")
        return value


# --- Pure helpers (no HTTP, no I/O) -----------------------------------------


def _iso(value: Optional[Any]) -> Optional[str]:
    """ISO-8601 for a datetime column value; None passes through."""
    if value is None:
        return None
    return value.isoformat()


def _render_digest(text: str) -> str:
    """The 'sha256:<hex>' digest form the IR's ``renders`` field uses."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_transition(policy: CompiledPolicy, action: str, actor: str) -> str:
    """Move a policy row through one lifecycle edge; return the target state.

    Raises ``ValueError`` on a state the action may not leave — the handler
    maps that to 409. The row's IR document carries its state too (hash-excluded,
    so the recorded content hash still verifies); it is kept in step here so a
    stored document never disagrees with its row.
    """
    allowed, target = _TRANSITIONS[action]
    if policy.state not in allowed:
        raise ValueError(
            f"cannot {action} a policy in state {policy.state!r} "
            f"(allowed from: {sorted(allowed)})"
        )
    by_col, at_col = _TRANSITION_COLUMNS[action]
    now = utcnow()
    policy.state = target
    setattr(policy, by_col, actor)
    setattr(policy, at_col, now)
    policy.policy_ir = {**policy.policy_ir, "state": target}
    return target


def policy_summary(row: CompiledPolicy) -> dict[str, Any]:
    """One policy row as the console renders it.

    The stored IR is validated on read (the load-time tamper check) and the
    row's ``state`` column wins over the document's — the row is the
    lifecycle's writer.
    """
    ir = PolicyIR.from_dict(row.policy_ir)
    document = ir.to_dict()
    document["state"] = row.state
    return {
        "policy_id": row.policy_id,
        "version": row.version,
        "state": row.state,
        "content_hash": row.content_hash,
        "compiled_at": _iso(row.compiled_at),
        "compiled_by": row.compiled_by,
        "match": document["match"],
        "decision": document["decision"],
        "maturity": document["maturity"],
        "renders": dict(ir.renders),
        "lifecycle": {
            "promoted_by": row.promoted_by,
            "promoted_at": _iso(row.promoted_at),
            "suspended_by": row.suspended_by,
            "suspended_at": _iso(row.suspended_at),
            "rearmed_by": row.rearmed_by,
            "rearmed_at": _iso(row.rearmed_at),
            "retired_by": row.retired_by,
            "retired_at": _iso(row.retired_at),
        },
    }


def decision_record(row: CompiledPolicyDecision) -> dict[str, Any]:
    """One evaluation row as the console renders it."""
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "policy_id": row.policy_id,
        "policy_version": row.policy_version,
        "content_hash": row.content_hash,
        "mode": row.mode,
        "outcome": row.outcome,
        "decision": row.decision,
        "actual_decision": row.actual_decision,
        "agreement_source": row.agreement_source,
        "agrees": row.agrees,
        "evaluation_us": row.evaluation_us,
        "evaluated_at": _iso(row.evaluated_at),
    }


def agreement_counts(rows: Sequence[CompiledPolicyDecision]) -> dict[str, Any]:
    """Shadow-vs-actual agreement for a decision log, counted in memory.

    Rows whose actual outcome has not landed yet (``actual_decision`` NULL) are
    ``pending`` — the drift counters and the console's promotion evidence read
    the same pairing the storage model's CHECK constraints define.
    """
    counts: dict[str, Any] = {
        "by_mode": {"shadow": 0, "active": 0},
        "llm": {"agrees": 0, "disagrees": 0},
        "analyst": {"agrees": 0, "disagrees": 0},
        "pending": 0,
    }
    for row in rows:
        if row.mode in counts["by_mode"]:
            counts["by_mode"][row.mode] += 1
        if row.agreement_source in ("llm", "analyst"):
            bucket = counts[row.agreement_source]
            bucket["agrees" if row.agrees else "disagrees"] += 1
        else:
            counts["pending"] += 1
    return counts


# --- Row lookups (the fake-session-friendly query surface) -------------------


def _policy_row(
    session: Any, policy_id: str, version: Optional[int]
) -> Optional[CompiledPolicy]:
    """One (policy_id, version) row, or the version head when version is None."""
    if version is not None:
        return session.get(CompiledPolicy, (policy_id, version))
    rows = (
        session.query(CompiledPolicy)
        .filter(CompiledPolicy.policy_id == policy_id)
        .all()
    )
    if not rows:
        return None
    return max(rows, key=lambda row: row.version)


def _require_policy(
    session: Any, policy_id: str, version: Optional[int]
) -> CompiledPolicy:
    row = _policy_row(session, policy_id, version)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"policy {policy_id} version {version} not found",
        )
    return row


# --- Routes ------------------------------------------------------------------


@router.get("")
def list_policies(
    session: UnitOfWorkSession,
    state: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List compiled policies, newest version first, optionally by state."""
    query = session.query(CompiledPolicy)
    if state is not None:
        if state not in POLICY_STATES:
            raise HTTPException(
                status_code=422,
                detail=f"state must be one of {list(POLICY_STATES)}",
            )
        query = query.filter(CompiledPolicy.state == state)
    rows = query.order_by(
        CompiledPolicy.policy_id.asc(), CompiledPolicy.version.desc()
    ).all()
    return {
        "policies": [policy_summary(row) for row in rows],
        "total": len(rows),
    }


@router.get("/{policy_id}")
def get_policy(
    policy_id: str,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Inspect one policy: every version, newest first, with the head called out."""
    rows = (
        session.query(CompiledPolicy)
        .filter(CompiledPolicy.policy_id == policy_id)
        .order_by(CompiledPolicy.version.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"policy {policy_id} not found")
    return {
        "policy_id": policy_id,
        "head": policy_summary(rows[0]),
        "versions": [policy_summary(row) for row in rows],
    }


@router.get("/{policy_id}/decisions")
def list_decisions(
    policy_id: str,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
    version: Optional[int] = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """The evaluation log for one policy: rows plus shadow-vs-actual agreement.

    Counts cover every logged decision for the policy (the shadow window's
    promotion evidence), while ``decisions`` is the requested page. v1 fetches
    the policy's rows and counts in memory — per-archetype log volumes are
    modest; revisit with SQL aggregation if consoles page through large logs.
    """
    if _policy_row(session, policy_id, version) is None:
        raise HTTPException(
            status_code=404,
            detail=f"policy {policy_id} version {version} not found",
        )
    query = session.query(CompiledPolicyDecision).filter(
        CompiledPolicyDecision.policy_id == policy_id
    )
    if version is not None:
        query = query.filter(CompiledPolicyDecision.policy_version == version)
    rows = query.order_by(
        CompiledPolicyDecision.evaluated_at.desc(),
        CompiledPolicyDecision.id.desc(),
    ).all()
    return {
        "policy_id": policy_id,
        "version": version,
        "total": len(rows),
        "agreement": agreement_counts(rows),
        "decisions": [decision_record(row) for row in rows[offset : offset + limit]],
    }


@router.post("/{policy_id}/promote", dependencies=_LIFECYCLE_WRITE)
def promote_policy(
    policy_id: str,
    body: LifecycleRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Promote a shadow policy to active. Human-acted, audited."""
    return _transition(policy_id, body, "promote", current_user.username, session)


@router.post("/{policy_id}/suspend", dependencies=_LIFECYCLE_WRITE)
def suspend_policy(
    policy_id: str,
    body: LifecycleRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Suspend a shadow or active policy (the human stop button). Audited."""
    return _transition(policy_id, body, "suspend", current_user.username, session)


@router.post("/{policy_id}/rearm", dependencies=_LIFECYCLE_WRITE)
def rearm_policy(
    policy_id: str,
    body: LifecycleRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-arm a suspended policy back into shadow — never straight to active."""
    return _transition(policy_id, body, "rearm", current_user.username, session)


@router.post("/{policy_id}/retire", dependencies=_LIFECYCLE_WRITE)
def retire_policy(
    policy_id: str,
    body: LifecycleRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retire a policy. Terminal — kept for audit, never evaluated again."""
    return _transition(policy_id, body, "retire", current_user.username, session)


@router.get("/{policy_id}/export")
def export_policy(
    policy_id: str,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
    format: ExportFormat = Query(description="Render target format"),
    version: Optional[int] = Query(default=None),
) -> PlainTextResponse:
    """Download the policy rendered to an external enforcement format.

    The render is a fresh projection of the stored (validated) IR — the
    canonical artifact — so an export never depends on render digests having
    been recorded at compile time. The response carries the render's own
    digest so a download is self-describing and auditable against the IR.
    """
    policy = _require_policy(session, policy_id, version)
    try:
        ir = PolicyIR.from_dict(policy.policy_ir)
        rendered = render(ir, format)
    except PolicyValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"stored policy IR for {policy_id} v{policy.version} "
            f"failed validation: {exc}",
        ) from exc
    return PlainTextResponse(
        rendered,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{policy_id}-v{policy.version}'
                f'.{_EXPORT_EXTENSION[format]}"'
            ),
            "X-Vigil-Render-Sha256": _render_digest(rendered),
        },
    )


def _transition(
    policy_id: str,
    body: LifecycleRequest,
    action: str,
    actor: str,
    session: Any,
) -> dict[str, Any]:
    """Shared body of the four lifecycle actions: guard, move, audit, report."""
    policy = _require_policy(session, policy_id, body.version)
    if body.content_hash is not None and body.content_hash != policy.content_hash:
        raise HTTPException(
            status_code=409,
            detail=f"content hash mismatch: {policy_id} v{policy.version} changed "
            "since it was loaded (refusing to move a version the actor was "
            "not looking at)",
        )
    previous_state = policy.state
    try:
        target = apply_transition(policy, action, actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.add(
        ConfigAuditLog(
            config_type="compiled_policy",
            config_key=f"{policy_id}:v{body.version}",
            action=action,
            old_value={"state": previous_state},
            new_value={"state": target, "content_hash": policy.content_hash},
            changed_by=actor,
        )
    )
    return {
        "transition": {
            "action": action,
            "actor": actor,
            "from_state": previous_state,
            "to_state": target,
            "content_hash": policy.content_hash,
        },
        "policy": policy_summary(policy),
    }
