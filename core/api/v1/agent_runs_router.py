# Agent runs — the frozen /api/v1/agent-runs surface: start, list, get, steer.
# "Runs" in 1.0 means agent runs (not workflow runs); see core/api/v1/README.md.

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.agents import run_limits, run_start
from core.agents.directives import (
    DIRECTIVE_FIELDS,
    DIRECTIVE_KINDS,
    InvalidDirective,
    RunAlreadyEnded,
    UnknownRun,
    enqueue_directive,
)
from core.agents.queue import RUN_KINDS
from core.agents.run_status import run_status as run_status_of
from core.auth.current_user import get_current_user
from core.auth.permissions import permission_gate
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import User

router = APIRouter()

_RUN_AGENTS = [permission_gate("ai_chat.use")]

ROUTER_META = RouterMeta(
    prefix="/api/v1/agent-runs",
    tags=["agent-runs"],
    auth=Auth.REQUIRED,
    legacy_prefixes=("/api/agent-runs",),
)
logger = logging.getLogger(__name__)


class StartRunRequest(BaseModel):
    run_kind: str = Field(default="hunt", description=f"One of {', '.join(RUN_KINDS)}.")
    arch: str = Field(
        default="",
        description="Arch file path; empty routes through the run-kind registry.",
    )
    playbook: str = Field(
        ..., description="Path to the playbook: the scenario as data."
    )
    config: str = Field(..., description="Path to the deployment config.")
    prompt: str = Field(default="", description="What the run is being asked to do.")
    overrides: Optional[Dict[str, Any]] = None
    tenant_id: Optional[str] = None


class StartRunResponse(BaseModel):
    run_id: str
    job_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str = Field(..., description="queued, running or terminal.")
    events: int = Field(
        ..., description="Events on the ledger, so progress is visible."
    )
    outcome: Optional[str] = None
    reason: Optional[str] = None


class RunListItem(BaseModel):
    run_id: Optional[str] = None
    run_kind: Optional[str] = Field(
        default=None, description="hunt, lead, compose, ... — from the run's trigger."
    )
    status: Optional[str] = None
    triggered_by: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class RunListResponse(BaseModel):
    runs: list[RunListItem]
    count: int = Field(..., description="Number of runs in this page.")


# List agent runs newest-first from workflow_runs (filtered to source=agent);
# per-run detail is GET /{run_id}, which reads the ledger. See README.
@router.get("", response_model=RunListResponse)
def list_runs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> RunListResponse:
    from core.workflows.workflow_run_service import WorkflowRunService

    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = WorkflowRunService().list_runs(
        workflow_source="agent",
        status=status,
        limit=limit,
        offset=offset,
    )
    items = [
        RunListItem(
            run_id=r.get("run_id"),
            run_kind=(r.get("trigger_context") or {}).get("run_kind"),
            status=r.get("status"),
            triggered_by=r.get("triggered_by"),
            started_at=(str(r["started_at"]) if r.get("started_at") else None),
            finished_at=(str(r["finished_at"]) if r.get("finished_at") else None),
        )
        for r in rows
    ]
    return RunListResponse(runs=items, count=len(items))


# Start and status delegate to core.agents.run_start / core.agents.run_status:
# the MCP server's start_agent_run and get_agent_run drive the same code, so a
# run started over either surface is begun and reported the same way.
@router.post(
    "", dependencies=_RUN_AGENTS, response_model=StartRunResponse, status_code=202
)
async def start_run(request: StartRunRequest) -> StartRunResponse:
    try:
        started = await run_start.start_run(
            run_kind=request.run_kind,
            playbook=request.playbook,
            config=request.config,
            arch=request.arch,
            prompt=request.prompt,
            overrides=request.overrides,
            tenant_id=request.tenant_id,
            enqueued_by="api",
        )
    except run_start.UnknownRunKind as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except run_start.WorkflowDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except run_limits.OverrideRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except run_start.RunQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    return StartRunResponse(**started)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, session: UnitOfWorkSession) -> RunStatusResponse:
    status = run_status_of(session, run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id}") from None
    return RunStatusResponse(**status)


class DirectiveRequest(BaseModel):
    kind: str = Field(..., description=f"One of {', '.join(DIRECTIVE_KINDS)}.")
    text: str = Field(
        default="",
        max_length=2000,
        description="What the operator is telling the run.",
    )
    actor: Optional[str] = Field(
        default=None, description="Who is steering. Defaults to the session user."
    )
    fields: Optional[Dict[str, Any]] = Field(
        default=None, description=f"Any of {', '.join(DIRECTIVE_FIELDS)}."
    )


class DirectiveResponse(BaseModel):
    directive_id: str
    kind: str
    created_at: str


# Steer a run that is already going. It queues rather than journals: the run
# holding the ledger is what turns a directive into a ledger event.
@router.post(
    "/{run_id}/directives",
    dependencies=_RUN_AGENTS,
    response_model=DirectiveResponse,
    status_code=202,
)
def queue_directive(
    run_id: str,
    body: DirectiveRequest,
    session: UnitOfWorkSession,
    current_user: User = Depends(get_current_user),
) -> DirectiveResponse:
    try:
        directive = enqueue_directive(
            session,
            run_id=run_id,
            kind=body.kind,
            body=body.text,
            actor=current_user.username,
            fields=body.fields,
        )
    except UnknownRun as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except RunAlreadyEnded as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except InvalidDirective as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    return DirectiveResponse(
        directive_id=directive["directive_id"],
        kind=directive["kind"],
        created_at=directive["created_at"],
    )
