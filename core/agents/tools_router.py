# The one way the TypeScript agent layer reaches a Python tool. Bounds are applied
# here rather than after serialisation, which would malform the result.

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import nullcontext
from typing import Any, ContextManager, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.agents.integration_tools import resolve_integration_call
from core.agents.internal_auth import authorise
from core.agents.mcp_tools import MCPFailure, execute_mcp_tool, split_tool_name
from core.agents.tool_registry import MANIFEST, execute_backend_tool
from core.audit import tool_calls
from core.auth import tool_principal
from core.auth.permissions import username_has_tool_permission
from core.deps import provide_mcp_registry
from core.integrations.mcp.registry import MCPRegistry
from core.integrations.mcp.surface import VIGIL_SERVER, acting_as
from core.llm.tool_schemas import CALL_INTEGRATION_TOOL
from core.routing import Auth, RouterMeta

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/internal/tools",
    tags=["internal-tools"],
    auth=Auth.ROUTER_MANAGED,
    reason=(
        "A shared secret: the caller is the agent layer, not a session. Reachability\n"
        "is the NetworkPolicy's job since ADR 0014, not a loopback check."
    ),
)
logger = logging.getLogger(__name__)

SOURCE_SYSTEM = "vigil"


class Bounds(BaseModel):
    max_rows: int = Field(..., gt=0)
    timeout_ms: int = Field(..., gt=0)


class InvokeRequest(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    bounds: Bounds
    # An API-signed token for the session's user (core/auth/tool_principal.py) and
    # ToolPrincipal in contracts/tool.ts. Absent means no person: tools record "agent".
    principal: Optional[str] = None
    # The hunt or workflow run the call belongs to, when one is; it lands on the
    # audit row so a run's calls can be pulled together in an investigation.
    run_id: Optional[str] = None


def _failure(kind: str, **detail: Any) -> Dict[str, Any]:
    return {"ok": False, "failure": {"kind": kind, **detail}}


# Where a tool that answers an envelope keeps the rows. Read as one object the whole
# envelope is one row, so max_rows never bites however much came back.
_ENVELOPE_ROWS = ("results", "rows", "events", "items", "data")


# Whatever the ladder returned, as rows. A bare mapping is one row rather than no
# rows, so a tool answering with a single object is not read as an empty result.
def _rows(result: Any) -> List[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        # An envelope reporting a failure is not an empty result: unwrapping it to its
        # own empty rows list reads as "the query ran and found nothing", which is the
        # one answer a hunt must not confuse with "the query could not be run".
        if result.get("error"):
            return [result]
        for field in _ENVELOPE_ROWS:
            held = result.get(field)
            if isinstance(held, list):
                return held
    return [result]


# The ladder reports a failure in-band rather than raising, so that shape is read
# back out here.
def _errored(result: Any) -> Optional[str]:
    if isinstance(result, dict) and isinstance(result.get("error"), str):
        return result["error"]
    return None


# Python's wording for a call that did not fit its signature. A TypeError from
# inside a tool is not one, and invalid_args tells the model to retry until the cap.
_SIGNATURE_MISMATCH = (
    "unexpected keyword argument",
    "required positional argument",
    "required keyword-only argument",
    "positional argument",
)


def _is_bad_arguments(exc: TypeError) -> bool:
    return any(phrase in str(exc) for phrase in _SIGNATURE_MISMATCH)


# The names a row cap travels under: "limit" alone misses splunk_execute's max_results,
# and the MCP servers are the ones that answer in bulk.
_ROW_CAP_ARGS = ("limit", "max_results", "max_count")


# The cap reaches the tool rather than only its answer, and a caller asking for less
# keeps its own number. What ignores the cap is still truncated below.
#
# Only names the call already carries are lowered: setting all of them would hand a
# tool a keyword its signature does not take. When the call names none, a cap is
# attached only if the tool's schema already declares one — get_finding takes
# finding_id alone, and injecting limit made every point-read invalid_args.
def _schema_row_caps(
    tool: str, registry: Optional["MCPRegistry"] = None
) -> Optional[Tuple[str, ...]]:
    """The row-cap arguments ``tool`` declares, or None if nothing describes it.

    MANIFEST covers the backend tools. An MCP tool is described by the registry
    instead, and looking only in MANIFEST reported every one of them as
    undescribed -- which is how ``limit`` came to be sent to tools that do not
    take one.
    """
    spec = MANIFEST.get(tool)
    if spec is None and registry is not None:
        try:
            spec = next(
                (t for t in registry.get_all_tools() if t.get("name") == tool), None
            )
        except Exception:  # noqa: BLE001 - an unreadable registry describes nothing
            spec = None
    if spec is None:
        return None
    properties = (spec.get("input_schema") or spec.get("inputSchema") or {}).get(
        "properties"
    ) or {}
    return tuple(name for name in _ROW_CAP_ARGS if name in properties)


def _bounded(
    args: Dict[str, Any],
    max_rows: int,
    tool: str,
    registry: Optional["MCPRegistry"] = None,
) -> Dict[str, Any]:
    named = [name for name in _ROW_CAP_ARGS if name in args]
    if named:
        lowered = {
            name: min(args[name], max_rows) if isinstance(args[name], int) else max_rows
            for name in named
        }
        return {**args, **lowered}

    declared = _schema_row_caps(tool, registry)
    if not declared:
        # Nothing describes a row cap on this tool, or it has none. Sending one
        # anyway is a keyword its signature does not take; what it answers is
        # still truncated below, so the cap is not lost by not being sent.
        return {**args}
    return {**args, declared[0]: max_rows}


# The telemetry plane the rows came out of, which is what a hunt counts corroboration
# over. One label for everything leaves a worker's own typed string as the only domain.
def _source_system(tool: str, registry: MCPRegistry) -> str:
    try:
        split = split_tool_name(tool, registry.get_active_servers())
    except Exception:  # noqa: BLE001 — a registry that cannot be read names no server
        return SOURCE_SYSTEM
    return SOURCE_SYSTEM if split is None else split[0]


def _server_for(tool: str, args: Dict[str, Any], registry: MCPRegistry) -> str:
    """The server a permission key is scoped to, mirroring _run's routing.

    The same name the dispatch will execute is the name the permission and the
    audit row are written against — otherwise the check and the call could
    disagree about what was about to run. Unlike _source_system this fails
    closed on an unreadable registry: no server name, no scoping, no call.
    A call_integration_tool whose inner name is refused falls back to the
    Vigil scope — the baseline key still applies, and the dispatch refuses it
    anyway, so the fallback grants nothing.
    """
    if tool == CALL_INTEGRATION_TOOL:
        try:
            tool, args = resolve_integration_call(registry, args)
        except MCPFailure:
            return VIGIL_SERVER
    split = split_tool_name(tool, registry.get_active_servers())
    return VIGIL_SERVER if split is None else split[0]


# Backend tools first, then the MCP servers. One ceiling governs both, so a tool
# does not get a second timeout by virtue of living on the other side.
#
# call_integration_tool stands for the integration call it names, so that call is
# what runs, bounded and attributed as if it had been declared itself.
async def _run(body: InvokeRequest, registry: MCPRegistry) -> Tuple[Any, bool, str]:
    seconds = body.bounds.timeout_ms / 1000
    tool, raw = body.tool, body.args
    if tool == CALL_INTEGRATION_TOOL:
        tool, raw = resolve_integration_call(registry, raw)
    args = _bounded(raw, body.bounds.max_rows, tool, registry)

    result, handled = await asyncio.wait_for(
        execute_backend_tool(tool, args, registry=registry), timeout=seconds
    )
    if handled:
        return result, True, SOURCE_SYSTEM
    result, handled = await asyncio.wait_for(
        execute_mcp_tool(tool, args, seconds, registry), timeout=seconds
    )
    return result, handled, _source_system(tool, registry)


# The call itself, with every failure mapped to the envelope it reports as. The
# second element is whether the tool answered: the audit row records outcome ok
# or error, and this is where that is decided.
async def _dispatch(
    body: InvokeRequest, registry: MCPRegistry, bound: ContextManager[None]
) -> Tuple[Dict[str, Any], bool]:
    try:
        # The tool runs in this context (or a copy of it), so it sees the binding.
        with bound:
            result, handled, source = await _run(body, registry)
    except asyncio.TimeoutError:
        return _failure("timeout", timeoutMs=body.bounds.timeout_ms), False
    # An MCP server that could not be reached is a gap in visibility, not a defect
    # in the call, and the hunt records the two differently.
    except MCPFailure as exc:
        if exc.kind == "timeout":
            return _failure("timeout", timeoutMs=body.bounds.timeout_ms), False
        return _failure(exc.kind, detail=exc.detail), False
    except TypeError as exc:
        if _is_bad_arguments(exc):
            return _failure("invalid_args", detail=str(exc)), False
        logger.exception("tool %s failed", body.tool)
        return _failure("backend_error", detail=str(exc)), False

    # refused is for a name nothing implements. A tool that ran and could not
    # answer is a backend_error: the contract keeps the two apart deliberately.
    if not handled:
        return _failure("refused", detail=f"no such tool: {body.tool}"), False
    errored = _errored(result)
    if errored is not None:
        return _failure("backend_error", detail=errored), False

    rows = _rows(result)
    capped = len(rows) > body.bounds.max_rows
    return {
        "ok": True,
        "rows": rows[: body.bounds.max_rows],
        "rowCount": min(len(rows), body.bounds.max_rows),
        "capped": capped,
        "sourceSystem": source,
    }, True


@router.post("/invoke")
async def invoke(
    body: InvokeRequest,
    authorization: Optional[str] = Header(default=None),
    registry: MCPRegistry = Depends(provide_mcp_registry),
) -> Dict[str, Any]:
    authorise(authorization, "tool invocation")
    # A token that does not verify is refused, never read as "no person": that
    # would record a person's work as an agent's.
    username: Optional[str] = None
    bound: ContextManager[None] = nullcontext()
    if body.principal is not None:
        try:
            username = tool_principal.verify(body.principal)
            bound = acting_as(username)
        except tool_principal.InvalidPrincipal:
            raise HTTPException(status_code=401, detail="bad or expired principal")

    # A person's standing decides whether the call runs at all. A call with no
    # person behind it — a hunt — has no role to check and keeps the access it
    # had; what changes is that it is now recorded below as an agent's, not
    # invisible. The deny row is written first and fails the write if it cannot
    # land: a refusal nobody can account for is not an enforcement decision.
    server = _server_for(body.tool, body.args, registry)
    if username is not None and not username_has_tool_permission(username, server):
        tool_calls.record_tool_call(
            actor_username=username,
            surface=tool_calls.SURFACE_AGENT,
            server_name=server,
            tool_name=body.tool,
            args=body.args,
            decision=tool_calls.DECISION_DENY,
            deny_reason="permission",
            trace_id=tool_calls.current_trace_id(),
            run_id=body.run_id,
        )
        raise HTTPException(status_code=403, detail="tool not permitted for this role")

    started = time.perf_counter()
    try:
        response, ok = await _dispatch(body, registry, bound)
    except Exception as exc:  # noqa: BLE001
        # The agent layer reads the failure envelope (no session, shared secret);
        # the exception-text ratchet allow-lists this handler for that reason.
        logger.exception("tool %s failed", body.tool)
        response, ok = _failure("backend_error", detail=str(exc)), False
    # The allow row is written after the call answers, so it carries the real
    # outcome and duration. Its write failing fails the request the same way:
    # the caller does not read an unaudited success.
    tool_calls.record_tool_call(
        actor_username=username or tool_calls.ACTOR_AGENT,
        surface=tool_calls.SURFACE_AGENT,
        server_name=server,
        tool_name=body.tool,
        args=body.args,
        decision=tool_calls.DECISION_ALLOW,
        outcome="ok" if ok else "error",
        duration_ms=int((time.perf_counter() - started) * 1000),
        trace_id=tool_calls.current_trace_id(),
        run_id=body.run_id,
    )
    return response
