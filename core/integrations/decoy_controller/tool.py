"""Decoy-controller MCP tool server.

Exposes decoy-steering operations for the agent path: steer a suspicious
source into the decoy farm, remove one lease's redirect, reconcile what the
controller holds, and the emergency drain. Configured via Settings →
Integrations (``decoy_controller``); every tool is a no-op returning a clear
"not configured" result when the integration is disabled.

The sync REST helpers at the bottom (``_steer``/``_unsteer``/``_reconcile``/
``_drain``) are the daemon path: ``core/deception/backends.py``'s
``ControllerBackend`` imports them exactly the way the Cloudflare executor
imports this slice's helpers.
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
from core.integrations.decoy_controller.descriptor import DECOY_CONTROLLER

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 10


def _result(data: Dict[str, Any]):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _config() -> Optional[Dict[str, Any]]:
    if not is_integration_enabled("decoy_controller"):
        return None
    cfg = resolve(DECOY_CONTROLLER)
    if not cfg.get("base_url") or not cfg.get("api_token"):
        return None
    return cfg


def _headers(api_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Sync REST helpers — the daemon path (ControllerBackend imports these)
# ---------------------------------------------------------------------------


def _steer(
    base_url: str,
    api_token: str,
    lease_id: str,
    source_ip: str,
    destination_ips: list,
    ports: list,
    ttl_seconds: int,
) -> Dict[str, Any]:
    """Upsert one lease's redirect on the controller. Idempotent on lease_id."""
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/steer",
            headers=_headers(api_token),
            json={
                "lease_id": lease_id,
                "source_ip": source_ip,
                "destination_ips": list(destination_ips),
                "ports": [int(p) for p in ports],
                "ttl_seconds": int(ttl_seconds),
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return {"success": False, "error": f"controller unreachable: {e}"}
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    success = resp.status_code in (200, 201) and data.get("applied", False)
    return {
        "success": success,
        "status_code": resp.status_code,
        "backend": "controller",
        "backend_ref": data.get("ref"),
        "lease_id": lease_id,
        "ttl_seconds": data.get("ttl_seconds", ttl_seconds),
        "error": None if success else f"steer rejected ({resp.status_code})",
        "errors": data.get("detail"),
    }


def _unsteer(
    base_url: str, api_token: str, lease_id: str, backend_ref: Optional[str] = None
) -> Dict[str, Any]:
    """Remove one lease's redirect. Removing an unknown lease succeeds."""
    try:
        resp = httpx.delete(
            f"{base_url.rstrip('/')}/steer/{lease_id}",
            headers=_headers(api_token),
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return {"success": False, "error": f"controller unreachable: {e}"}
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    return {
        "success": resp.status_code in (200, 202, 204),
        "status_code": resp.status_code,
        "backend": "controller",
        "backend_ref": backend_ref,
        "lease_id": lease_id,
        "removed": data.get("removed", False),
        "error": None,
    }


def _reconcile(base_url: str, api_token: str) -> Dict[str, Any]:
    """What the controller currently holds. A pure read — always safe."""
    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/reconcile",
            headers=_headers(api_token),
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return {"success": False, "error": f"controller unreachable: {e}"}
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    return {
        "success": resp.status_code == 200,
        "status_code": resp.status_code,
        "backend": "controller",
        "driver": data.get("driver"),
        "count": data.get("count", 0),
        "rules": data.get("rules", []),
        "error": None,
    }


def _drain(base_url: str, api_token: str, reason: str) -> Dict[str, Any]:
    """Emergency removal of every rule on the controller."""
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/drain",
            headers=_headers(api_token),
            json={"reason": reason[:512]},
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return {"success": False, "error": f"controller unreachable: {e}"}
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    return {
        "success": resp.status_code == 200,
        "status_code": resp.status_code,
        "backend": "controller",
        "removed": data.get("removed", []),
        "count": data.get("count", 0),
        "error": None,
    }


# ---------------------------------------------------------------------------
# MCP tool surface — the agent path
# ---------------------------------------------------------------------------


async def handle_list_tools():
    return [
        types.Tool(
            name="decoy_steer",
            description=(
                "Transparently redirect a suspicious source into the decoy farm "
                "on a TTL lease. Idempotent per lease; re-calling with the same "
                "lease renews it. No deny signal reaches the source."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "lease_id": {"type": "string"},
                    "source_ip": {"type": "string", "description": "IPv4/IPv6 address"},
                    "destination_ips": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Internal targets the probes hit",
                    },
                    "ports": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Suspicious ports to redirect",
                    },
                    "ttl_seconds": {"type": "integer"},
                },
                "required": ["lease_id", "source_ip", "destination_ips", "ports"],
            },
        ),
        types.Tool(
            name="decoy_unsteer",
            description=(
                "Remove one lease's redirect; the source's traffic returns to "
                "normal paths. Reversible with decoy_steer on the same lease."
            ),
            inputSchema={
                "type": "object",
                "properties": {"lease_id": {"type": "string"}},
                "required": ["lease_id"],
            },
        ),
        types.Tool(
            name="decoy_reconcile",
            description=(
                "List the redirects the decoy controller currently holds "
                "(read-only). Use before/after any steering change."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="decoy_drain",
            description=(
                "Emergency: remove EVERY redirect the controller holds "
                "(the operator kill-switch). Use when containment fails."
            ),
            inputSchema={
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        ),
    ]


async def handle_call_tool(name: str, arguments: dict | None):
    args = arguments or {}
    cfg = _config()
    if cfg is None:
        return _result(
            {
                "error": "decoy_controller integration is not configured/enabled. "
                "Set base_url and api_token in Settings → Integrations."
            }
        )

    try:
        if name == "decoy_steer":
            missing = [
                key
                for key in ("lease_id", "source_ip", "destination_ips", "ports")
                if not args.get(key)
            ]
            if missing:
                return _result({"error": f"missing required fields: {missing}"})
            return _result(
                _steer(
                    base_url=cfg["base_url"],
                    api_token=cfg["api_token"],
                    lease_id=str(args["lease_id"]),
                    source_ip=str(args["source_ip"]),
                    destination_ips=list(args["destination_ips"]),
                    ports=list(args["ports"]),
                    ttl_seconds=int(args.get("ttl_seconds") or 3600),
                )
            )
        if name == "decoy_unsteer":
            if not args.get("lease_id"):
                return _result({"error": "lease_id required"})
            return _result(
                _unsteer(
                    base_url=cfg["base_url"],
                    api_token=cfg["api_token"],
                    lease_id=str(args["lease_id"]),
                )
            )
        if name == "decoy_reconcile":
            return _result(
                _reconcile(base_url=cfg["base_url"], api_token=cfg["api_token"])
            )
        if name == "decoy_drain":
            return _result(
                _drain(
                    base_url=cfg["base_url"],
                    api_token=cfg["api_token"],
                    reason=str(args.get("reason") or "operator kill-switch"),
                )
            )
        return _result({"error": f"Unknown tool: {name}"})
    except (TypeError, ValueError) as e:
        return _result({"error": f"invalid arguments: {e}"})


async def _on_list_tools(_ctx, _params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(_ctx, params):
    return await run_tool(handle_call_tool, params)


server = Server(
    "decoy_controller",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="decoy_controller",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
