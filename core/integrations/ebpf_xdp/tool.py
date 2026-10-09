"""eBPF/XDP MCP tool server — Vigil's surface onto the kernel enforcement daemon.

Exposes the spec's three kernel primitives (XDP packet drop, socket-level
redirect, process interdiction) plus release and status, talking to the
per-host `services/enforcement` daemon over its token-authed /v1 API. Configured
via Settings → Integrations (`ebpf-xdp`) or the VIGIL_ENFORCEMENT_* environment;
every tool is a no-op returning a clear "not configured" result when the
integration is disabled.

Real containment belongs to the approval queue: the xdp_* containment tools are
verb-destructive, so chat's ad-hoc surface never reaches them (see
core/llm/chat_layers.py) — the approved-action executor calls the same
module-level helpers this server dispatches to.
"""

import sys
from pathlib import Path

# Spawned as ``python3 core/integrations/<vendor>/tool.py`` with a narrowed env,
# so the repo root is not on sys.path and PYTHONPATH is not forwarded. Add it
# here so the ``core.*`` imports below resolve; otherwise they fail at spawn.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from core.config import is_integration_enabled
from core.integrations._base.config import resolve
from core.integrations._base.tool_result import run_tool
from core.integrations.ebpf_xdp.descriptor import EBPF_XDP

logger = logging.getLogger(__name__)

# The three enforcement kinds of the v1 contract
# (services/enforcement/contract/action-request.schema.json). The daemon owns
# target validation and the TTL floor — the client reports refusals, never
# second-guesses them.
KIND_XDP_DROP = "xdp_drop"
KIND_SOCKET_REDIRECT = "socket_redirect"
KIND_PROCESS_INTERDICT = "process_interdict"

DEFAULT_TIMEOUT = 30

_DISABLED = {
    # Uniform with the helpers' failure shape: an executor checking
    # result.get("success", True) must never read the disabled no-op as success.
    "success": False,
    "error": "ebpf_xdp_integration_disabled",
    "message": (
        "eBPF/XDP enforcement is not configured. Set VIGIL_ENFORCEMENT_URL and "
        "VIGIL_ENFORCEMENT_TOKEN (or configure the ebpf-xdp integration in "
        "Settings → Integrations) and enable it."
    ),
}


def _result(data: Dict[str, Any]):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _config() -> Optional[Dict[str, Any]]:
    if not is_integration_enabled("ebpf-xdp"):
        return None
    cfg = resolve(EBPF_XDP)
    if not cfg.get("enforcement_url") or not cfg.get("enforcement_token"):
        return None
    return cfg


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _normalize(status_code: int, body: Any) -> Dict[str, Any]:
    """Merge the wire body with the executor's success flag.

    Error replies keep the daemon's closed-vocabulary ``error`` code at the top
    level — the executor maps it onto ``mark_failed`` and the MCP result
    contract (``payload_is_error``) flags it — while success replies carry
    action_id/state/evidence verbatim for ``mark_executed``.
    """
    payload = dict(body) if isinstance(body, dict) else {}
    payload["success"] = status_code in (200, 201) and not payload.get("error")
    payload["status_code"] = status_code
    return payload


def _transport_failure(exc: Exception) -> Dict[str, Any]:
    # Not one of the daemon's error codes — the enforcer never answered, so
    # mark_failed sees a client-side failure it can retry, not a kernel verdict.
    return {
        "success": False,
        "error": "enforcer_unreachable",
        "message": str(exc),
    }


def _default_action_id(tool: str, target: str) -> str:
    # Deterministic, so a retried MCP call replays against the daemon's
    # action_id idempotency instead of double-enforcing. The approval pipeline
    # always passes the action row's own id, which overrides this.
    return f"{tool}:{target}"


def _ttl_or_default(cfg: Dict[str, Any], ttl_seconds: Optional[int]) -> Optional[int]:
    if ttl_seconds is not None:
        return int(ttl_seconds)
    default = cfg.get("default_ttl_seconds")
    return int(default) if default else None


async def handle_list_tools():
    return [
        types.Tool(
            name="xdp_block_ip",
            description=(
                "Drop all packets from a source IP in the NIC driver (XDP), on the "
                "host running the enforcement daemon. Reverses with xdp_unblock_ip "
                "or self-expires after ttl_seconds. Real containment: goes through "
                "the approval queue, never ad-hoc chat."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IPv4/IPv6 address"},
                    "reason": {
                        "type": "string",
                        "description": "Why this enforcement exists; lands in the audit trail",
                    },
                    "ttl_seconds": {
                        "type": "integer",
                        "description": "Containment lifetime; daemon default when omitted",
                    },
                    "action_id": {
                        "type": "string",
                        "description": (
                            "Caller-unique id, echoed in the response evidence. "
                            "Defaults to a deterministic id from the target so "
                            "retries replay instead of double-enforcing."
                        ),
                    },
                },
                "required": ["ip", "reason"],
            },
        ),
        types.Tool(
            name="xdp_unblock_ip",
            description=(
                "Release an enforcement by action_id (returned from xdp_block_ip or "
                "stored with the approval action's execution evidence)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                },
                "required": ["action_id"],
            },
        ),
        types.Tool(
            name="xdp_redirect_socket",
            description=(
                "Steer flows matching an IP (and optional port) to the daemon's "
                "configured sink instead of dropping them — preserving traffic for "
                "forensics. Same TTL and release semantics as xdp_block_ip."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string"},
                    "port": {"type": "integer", "minimum": 0, "maximum": 65535},
                    "reason": {"type": "string"},
                    "ttl_seconds": {"type": "integer"},
                    "action_id": {"type": "string"},
                },
                "required": ["ip", "reason"],
            },
        ),
        types.Tool(
            name="xdp_interdict_process",
            description=(
                "Deny connect/exec for a target process (BPF LSM on the process's "
                "cgroup; signal-based suspension on kernels without LSM BPF — the "
                "response evidence reports which mode ran). Same TTL semantics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "minimum": 1},
                    "reason": {"type": "string"},
                    "ttl_seconds": {"type": "integer"},
                    "action_id": {"type": "string"},
                },
                "required": ["pid", "reason"],
            },
        ),
        types.Tool(
            name="xdp_status",
            description=(
                "Read-only: the enforcement daemon's capability per primitive "
                "(degradation is per-primitive), plus the live enforcement entries. "
                "Returns the not-configured error when the integration is disabled."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def handle_call_tool(name: str, arguments: dict | None):
    args = arguments or {}

    try:
        if name == "xdp_block_ip":
            return _result(
                await asyncio.to_thread(
                    xdp_block_ip,
                    ip=args.get("ip"),
                    reason=args.get("reason", "Vigil SOC block"),
                    ttl_seconds=args.get("ttl_seconds"),
                    action_id=args.get("action_id"),
                )
            )
        if name == "xdp_unblock_ip":
            return _result(
                await asyncio.to_thread(
                    xdp_unblock_ip,
                    action_id=args.get("action_id"),
                )
            )
        if name == "xdp_redirect_socket":
            return _result(
                await asyncio.to_thread(
                    xdp_redirect_socket,
                    ip=args.get("ip"),
                    reason=args.get("reason", "Vigil SOC redirect"),
                    port=args.get("port", 0),
                    ttl_seconds=args.get("ttl_seconds"),
                    action_id=args.get("action_id"),
                )
            )
        if name == "xdp_interdict_process":
            return _result(
                await asyncio.to_thread(
                    xdp_interdict_process,
                    pid=args.get("pid"),
                    reason=args.get("reason", "Vigil SOC interdict"),
                    ttl_seconds=args.get("ttl_seconds"),
                    action_id=args.get("action_id"),
                )
            )
        if name == "xdp_status":
            return _result(await asyncio.to_thread(xdp_status))
        return _result({"error": f"Unknown tool: {name}"})
    except Exception as e:  # noqa: BLE001
        logger.exception("eBPF/XDP tool %s failed", name)
        return _result({"error": str(e), "tool": name})


# ---------------------------------------------------------------------------
# Module-level helpers — the single source of truth for the enforcement API
# surface, kept config-resolving so the approved-action executor can import and
# call them exactly as this MCP surface does (the Cloudflare convention).
# ---------------------------------------------------------------------------


def xdp_block_ip(
    ip: Optional[str],
    reason: str,
    ttl_seconds: Optional[int] = None,
    action_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Enforce an XDP drop for a source IP (contract kind ``xdp_drop``)."""
    if not ip:
        return {"success": False, "error": "ip required"}
    return _enforce(
        kind=KIND_XDP_DROP,
        ip=ip,
        port=0,
        pid=0,
        ttl_seconds=ttl_seconds,
        reason=reason,
        action_id=action_id or _default_action_id("xdp_block_ip", ip),
        idempotency_key=f"xdp_block_ip:{ip}",
    )


def xdp_unblock_ip(action_id: Optional[str]) -> Dict[str, Any]:
    """Release the enforcement identified by ``action_id`` (DELETE route)."""
    if not action_id:
        return {"success": False, "error": "action_id required"}
    cfg = _config()
    if cfg is None:
        return dict(_DISABLED)
    try:
        resp = httpx.delete(
            f"{cfg['enforcement_url'].rstrip('/')}/v1/actions/{action_id}",
            headers=_headers(str(cfg["enforcement_token"])),
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return _transport_failure(e)
    return _decoded(resp)


def xdp_redirect_socket(
    ip: Optional[str],
    reason: str,
    port: int = 0,
    ttl_seconds: Optional[int] = None,
    action_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Redirect flows for an IP (optionally an L4 port) to the sink."""
    if not ip:
        return {"success": False, "error": "ip required"}
    port = int(port or 0)
    return _enforce(
        kind=KIND_SOCKET_REDIRECT,
        ip=ip,
        port=port,
        pid=0,
        ttl_seconds=ttl_seconds,
        reason=reason,
        action_id=action_id
        or _default_action_id("xdp_redirect_socket", f"{ip}:{port}" if port else ip),
        idempotency_key=f"xdp_redirect_socket:{ip}:{port}",
    )


def xdp_interdict_process(
    pid: Optional[int],
    reason: str,
    ttl_seconds: Optional[int] = None,
    action_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Interdict a process by pid (contract kind ``process_interdict``)."""
    if not pid:
        return {"success": False, "error": "pid required"}
    return _enforce(
        kind=KIND_PROCESS_INTERDICT,
        ip=None,
        port=0,
        pid=int(pid),
        ttl_seconds=ttl_seconds,
        reason=reason,
        action_id=action_id or _default_action_id("xdp_interdict_process", str(pid)),
        idempotency_key=f"xdp_interdict_process:{pid}",
    )


def xdp_status() -> Dict[str, Any]:
    """Capability per primitive plus the live enforcement entries."""
    cfg = _config()
    if cfg is None:
        return dict(_DISABLED)
    url = str(cfg["enforcement_url"]).rstrip("/")
    try:
        health = _decoded(httpx.get(f"{url}/healthz", timeout=DEFAULT_TIMEOUT))
    except httpx.HTTPError as e:
        return _transport_failure(e)
    if not health.get("success"):
        return health
    try:
        listing = _decoded(
            httpx.get(
                f"{url}/v1/actions",
                headers=_headers(str(cfg["enforcement_token"])),
                timeout=DEFAULT_TIMEOUT,
            )
        )
    except httpx.HTTPError as e:
        listing = _transport_failure(e)
    status = dict(health)
    status["actions"] = listing.get("actions", []) if listing.get("success") else []
    if not listing.get("success"):
        status["actions_error"] = listing.get("error")
    return status


def _enforce(
    kind: str,
    ip: Optional[str],
    port: int,
    pid: int,
    ttl_seconds: Optional[int],
    reason: str,
    action_id: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    cfg = _config()
    if cfg is None:
        return dict(_DISABLED)
    # The contract's target carries all three fields with 0/absent meaning
    # "not targeted"; ip is forbidden for process_interdict, so it is omitted
    # there rather than sent empty.
    target: Dict[str, Any] = {"port": port, "pid": pid}
    if kind != KIND_PROCESS_INTERDICT:
        target["ip"] = ip
    payload: Dict[str, Any] = {
        "action_id": action_id,
        "kind": kind,
        "target": target,
        "reason": reason[:4096],
        "idempotency_key": idempotency_key,
    }
    ttl = _ttl_or_default(cfg, ttl_seconds)
    if ttl is not None:
        payload["ttl_seconds"] = ttl
    try:
        resp = httpx.post(
            f"{str(cfg['enforcement_url']).rstrip('/')}/v1/actions",
            headers=_headers(str(cfg["enforcement_token"])),
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return _transport_failure(e)
    return _decoded(resp)


def _decoded(resp: httpx.Response) -> Dict[str, Any]:
    try:
        body = resp.json() if resp.content else {}
    except ValueError:
        return {
            "success": False,
            "error": "invalid_response",
            "message": f"enforcer returned non-JSON (status {resp.status_code})",
            "status_code": resp.status_code,
        }
    return _normalize(resp.status_code, body)


async def _on_list_tools(_ctx, _params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(_ctx, params):
    return await run_tool(handle_call_tool, params)


server = Server(
    "ebpf-xdp",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="ebpf-xdp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
