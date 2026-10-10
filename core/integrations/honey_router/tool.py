"""Honey-router MCP tool server.

Exposes the deception plane's enforcement as tools: route an attacker into
a decoy, unroute them, and list the decoys that may receive routes. The
autonomous path does NOT come through here — the daemon responder creates
``honey_route`` actions and the approval pipeline gates them; these tools
exist for operators and the analyst surface. Configured via Settings →
Integrations (``honey_router``); every tool is a no-op returning a clear
"not configured" result when the integration is disabled.

Route/unroute are enforcement writes: they only act when the integration
is enabled AND a backend is reachable, and they report failures honestly
(the ``isolate_host`` rule) rather than fabricating success.
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

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from core.config import is_integration_enabled
from core.integrations._base.tool_result import run_tool

logger = logging.getLogger(__name__)


def _result(data: Dict[str, Any]):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _config() -> Optional[Dict[str, Any]]:
    if not is_integration_enabled("honey_router"):
        return None
    return {"enabled": True}


def _not_configured() -> Dict[str, Any]:
    return {
        "error": "honey_router_integration_disabled",
        "message": (
            "Honey-routing enforcement is not configured. Enable the "
            "honey_router integration in Settings → Integrations."
        ),
    }


async def handle_list_tools():
    return [
        types.Tool(
            name="honey_route",
            description=(
                "Route an attacker's flows into a registered decoy "
                "(Cilium local redirect). Requires the honey_router "
                "integration enabled and a reachable enforcement backend."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "attacker_ip": {"type": "string"},
                    "decoy_id": {"type": "string"},
                    "ttl_seconds": {
                        "type": "integer",
                        "description": (
                            "How long the route may hold before the daemon's "
                            "TTL sweep releases it."
                        ),
                    },
                },
                "required": ["attacker_ip", "decoy_id"],
            },
        ),
        types.Tool(
            name="honey_unroute",
            description=(
                "Remove an attacker's decoy routing, restoring the normal "
                "traffic path. Idempotent: an already-removed route reports "
                "success."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "attacker_ip": {"type": "string"},
                },
                "required": ["attacker_ip"],
            },
        ),
        types.Tool(
            name="honey_list_decoys",
            description=(
                "Read-only: the active decoys honey-routing may target. "
                "Never includes canary credential references."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def handle_call_tool(name: str, arguments: dict | None):
    if _config() is None:
        return _result(_not_configured())

    args = arguments or {}
    # Lazy import: keeps the enforcement modules (and their storage imports)
    # off installs that never enable the integration.
    from core.integrations.honey_router import route as honey_router

    try:
        if name == "honey_route":
            decoy_id = args.get("decoy_id")
            if not decoy_id:
                return _result(
                    {"error": "missing_decoy_id", "message": "decoy_id is required"}
                )
            ttl = args.get("ttl_seconds")
            return _result(
                await asyncio.to_thread(
                    honey_router.route,
                    attacker_ip=args.get("attacker_ip", ""),
                    decoy_id=str(decoy_id),
                    ttl_seconds=int(ttl) if ttl is not None else None,
                )
            )
        if name == "honey_unroute":
            return _result(
                await asyncio.to_thread(
                    honey_router.unroute,
                    args.get("attacker_ip", ""),
                )
            )
        if name == "honey_list_decoys":
            return _result(await asyncio.to_thread(honey_router.list_active_decoys))
        return _result({"error": f"unknown honey-router tool {name}"})
    except Exception as e:  # noqa: BLE001 — the tool contract reports, never raises
        logger.exception("Honey-router tool %s failed", name)
        return _result({"error": str(e)})


async def _on_list_tools(_ctx, _params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(_ctx, params):
    return await run_tool(handle_call_tool, params)


server = Server(
    "honey-router",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="honey-router",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
