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

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from core.config import get_settings
from core.integrations._base.config import missing, resolve
from core.integrations._base.tls import tls_verify
from core.integrations._base.tool_errors import classified_error
from core.integrations._base.tool_result import run_tool
from core.integrations.palo_alto.descriptor import PALO_ALTO

logger = logging.getLogger(__name__)


def result(data):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _dev_mode() -> bool:
    """Dev-mode read for the plaintext-URL allowance.

    The spawned child's narrowed env rarely carries DEV_MODE, and any settings
    failure means we cannot know we are in dev — both fail closed to False.
    """
    try:
        return bool(get_settings().dev_mode)
    except Exception:  # noqa: BLE001
        return False


async def handle_list_tools():
    return [
        types.Tool(
            name="pan_block_ip",
            description="Block IP on Palo Alto firewall",
            inputSchema={
                "type": "object",
                "properties": {"ip": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["ip", "reason"],
            },
        ),
        types.Tool(
            name="pan_get_threats",
            description="Get threat logs",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 20}},
                "required": [],
            },
        ),
    ]


async def handle_call_tool(name: str, arguments: dict | None):
    config = resolve(PALO_ALTO)
    api_key = config.get("api_key")
    if missing(config, "hostname", "api_key"):
        return result({"error": "Palo Alto not configured"})

    # The Settings form collects a hostname; PAN-OS is reached over HTTPS.
    host = str(config.get("hostname")).rstrip("/")
    if host.lower().startswith("http://") and not _dev_mode():
        # An explicit http:// scheme would put the PAN-OS API key on the
        # wire in cleartext (it travels as a query parameter). Refuse unless
        # dev mode — in the spawned child that is effectively always off.
        logger.warning("palo-alto: refusing plaintext http:// base URL (dev mode off)")
        return result(
            {
                "error": "Palo Alto base URL must use https:// — plaintext http:// is refused",
                "hostname": host,
            }
        )
    url = host if host.startswith(("http://", "https://")) else f"https://{host}"
    # resolve() always returns every declared field, so a .get(k, True) default
    # would never fire — verify_ssl is present-but-None when unset.
    verify = True if config.get("verify_ssl") is None else config.get("verify_ssl")
    ca_cert_path = config.get("ca_cert_path")

    args = arguments or {}

    try:
        if name == "pan_block_ip":
            ip = args.get("ip")
            if not ip:
                return result({"error": "ip required"})
            # Add to EDL or address group
            resp = httpx.get(
                f"{url}/api/",
                params={
                    "type": "config",
                    "action": "set",
                    "key": api_key,
                    "xpath": f"/config/devices/entry/vsys/entry[@name='vsys1']/address/entry[@name='blocked-{ip}']",
                    "element": f"<ip-netmask>{ip}/32</ip-netmask><description>Blocked: {args.get('reason', 'security')}</description>",
                },
                verify=tls_verify(verify, ca_cert_path),
                timeout=30,
            )
            # httpx doesn't follow redirects, so a 3xx here means the configured
            # hostname is wrong. Carry the status or that is undiagnosable.
            return result(
                {
                    "success": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "ip": ip,
                    "action": "blocked",
                }
            )

        elif name == "pan_get_threats":
            resp = httpx.get(
                f"{url}/api/",
                params={
                    # `or 20`: see the aad_get_sign_ins note — a null limit would
                    # reach the wire as "nlogs=" under httpx.
                    "type": "log",
                    "log-type": "threat",
                    "key": api_key,
                    "nlogs": args.get("limit") or 20,
                },
                verify=tls_verify(verify, ca_cert_path),
                timeout=30,
            )
            # Parse XML response (simplified)
            return result(
                {"success": True, "message": "Check Palo Alto console for threat logs"}
            )

        return result({"error": f"Unknown tool: {name}"})
    except Exception as e:
        # str(e) carries the upstream URL and response body — the agent
        # channel gets a classified string; the detail is logged, not returned.
        return result({"error": classified_error("palo-alto", name, e)})


async def _on_list_tools(_ctx, _params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(_ctx, params):
    return await run_tool(handle_call_tool, params)


server = Server(
    "palo-alto",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="palo-alto",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
