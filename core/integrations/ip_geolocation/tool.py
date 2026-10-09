import sys
from pathlib import Path

# Spawned as ``python3 core/integrations/<vendor>/tool.py`` with a narrowed env,
# so the repo root is not on sys.path and PYTHONPATH is not forwarded. Add it
# here so the ``core.*`` imports below resolve; otherwise they fail at spawn.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import asyncio
import ipaddress
import json
import logging
from typing import Optional

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from core.integrations._base.tool_errors import classified_error
from core.integrations._base.tool_result import run_tool

logger = logging.getLogger(__name__)


def result(data):
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


# The lookup target leaves the host in the query string, so a bogon target
# would disclose an internal address to the provider and the answer is worth-
# less anyway. Named explicitly, mirroring core/platform/url_safety.py: the
# metadata addresses get their own line because that is the failure that
# matters for a SOC tool, even though both are link-local.
_METADATA_ADDRESSES = (
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
)


def bogon_reason(ip: str) -> Optional[str]:
    """Why this lookup target must not leave the host; None when it may.

    Refuses RFC1918, loopback, link-local (the cloud metadata service
    included), multicast, reserved and unspecified ranges before any outbound
    call, plus non-literal inputs: the tool is ``geolocate_ip`` and resolving a
    hostname here would add a DNS-rebinding surface the caller never asked
    for.
    """
    try:
        addr = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return "lookup target must be a literal IPv4 or IPv6 address"
    # ::ffff:10.0.0.1 connects as real IPv4, so it faces the same checks.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr in _METADATA_ADDRESSES:
        return "cloud metadata addresses are not looked up"
    if addr.is_loopback:
        return "loopback addresses are not looked up"
    if addr.is_private:
        return "private (RFC1918) addresses are not looked up"
    if addr.is_link_local:
        return "link-local addresses are not looked up"
    if addr.is_multicast:
        return "multicast addresses are not looked up"
    if addr.is_reserved:
        return "reserved addresses are not looked up"
    if addr.is_unspecified:
        return "unspecified addresses are not looked up"
    return None


async def handle_list_tools():
    return [
        types.Tool(
            name="geolocate_ip",
            description="Get geolocation for IP address",
            inputSchema={
                "type": "object",
                "properties": {"ip": {"type": "string"}},
                "required": ["ip"],
            },
        ),
        types.Tool(
            name="geolocate_batch",
            description="Geolocate multiple IPs",
            inputSchema={
                "type": "object",
                "properties": {"ips": {"type": "array", "items": {"type": "string"}}},
                "required": ["ips"],
            },
        ),
    ]


async def handle_call_tool(name: str, arguments: dict | None):
    args = arguments or {}

    def lookup_ip(ip):
        # Refusal happens before any outbound call: the query itself is the
        # disclosure.
        reason = bogon_reason(ip)
        if reason is not None:
            return {"ip": ip, "error": reason}
        try:
            # ipwho.is, not ip-api.com: the hardening standard is HTTPS-only,
            # and ip-api's free tier serves plain HTTP by design — its own
            # docs say SSL needs the paid tier. ipwho.is is keyless HTTPS
            # with the same shape of answer (country/region/city/isp/org/
            # lat/lon), remapped below to the tool's original keys.
            resp = httpx.get(f"https://ipwho.is/{ip}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") is True:
                    conn = data.get("connection") or {}
                    return {
                        "ip": ip,
                        "country": data.get("country"),
                        "region": data.get("region"),
                        "city": data.get("city"),
                        "isp": conn.get("isp"),
                        "org": conn.get("org"),
                        "lat": data.get("latitude"),
                        "lon": data.get("longitude"),
                    }
            return {"ip": ip, "error": "Lookup failed"}
        except Exception as e:
            # str(e) can carry the provider URL or a proxy error body — the
            # agent channel gets a classified string, the log keeps the detail.
            return {"ip": ip, "error": classified_error("ip-geolocation", name, e)}

    if name == "geolocate_ip":
        ip = args.get("ip")
        if not ip:
            return result({"error": "ip required"})
        return result(lookup_ip(ip))

    elif name == "geolocate_batch":
        ips = args.get("ips", [])
        if not ips:
            return result({"error": "ips required"})
        results = [lookup_ip(ip) for ip in ips[:10]]
        return result({"count": len(results), "results": results})

    return result({"error": f"Unknown tool: {name}"})


async def _on_list_tools(_ctx, _params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(_ctx, params):
    return await run_tool(handle_call_tool, params)


server = Server(
    "ip-geolocation",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(
            read,
            write,
            InitializationOptions(
                server_name="ip-geolocation",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
