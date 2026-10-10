"""The configured cwd is forwarded to the spawned MCP server (E16).

An mcp-config entry's ``cwd`` was resolved at load time (``${workspaceFolder}``
→ the project root, or an absolute directory) and stored on the ``MCPServer``
model — and then dropped: the spawn site never passed it to
``StdioServerParameters``, so the SDK spawned every child in the backend's
working directory. An operator reading ``cwd`` as a boundary got nothing.

The contract now: the spawn site forwards ``server.cwd`` verbatim and the SDK
applies it to the child process (``mcp.client.stdio`` passes ``params.cwd``
through to ``anyio.open_process``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.integrations.mcp import client as mcp_client  # noqa: E402
from core.integrations.mcp.service import MCPService  # noqa: E402

pytestmark = pytest.mark.unit


class _SpawnProbe(RuntimeError):
    """Stops connect_to_server right after the parameters are built."""


@pytest.fixture
def demo_config(tmp_path):
    return {"command": "python", "args": ["-m", "tools.demo"]}


def test_configured_cwd_resolves_workspaceFolder_at_load(tmp_path, demo_config):
    """A relative ``${workspaceFolder}`` cwd resolves against the project root."""
    config = dict(demo_config, cwd="${workspaceFolder}/servers")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps({"mcpServers": {"demo": config}})
    )

    service = MCPService(project_root=tmp_path)

    assert service.servers["demo"].cwd == str(tmp_path / "servers")


def test_an_absolute_cwd_is_kept_verbatim(tmp_path, demo_config):
    config = dict(demo_config, cwd="/srv/mcp-workers")
    (tmp_path / "mcp-config.json").write_text(
        json.dumps({"mcpServers": {"demo": config}})
    )

    service = MCPService(project_root=tmp_path)

    assert service.servers["demo"].cwd == "/srv/mcp-workers"


def test_default_cwd_is_the_project_root(tmp_path, demo_config):
    """No cwd key — the child runs against the project root, which is what
    ``${workspaceFolder}`` substituted to all along."""
    (tmp_path / "mcp-config.json").write_text(
        json.dumps({"mcpServers": {"demo": demo_config}})
    )

    service = MCPService(project_root=tmp_path)

    assert service.servers["demo"].cwd == str(tmp_path)


async def test_the_spawn_site_forwards_the_server_cwd(tmp_path, demo_config):
    """The spawn site passes ``cwd=server.cwd`` into StdioServerParameters.

    A spy on the SDK parameters class stops the connection right after the
    parameters are built (``connect_to_server`` catches the probe and returns
    False); the recorded kwargs are the assertion.
    """
    (tmp_path / "mcp-config.json").write_text(
        json.dumps({"mcpServers": {"demo": dict(demo_config, cwd="/srv/mcp-workers")}})
    )
    service = MCPService(project_root=tmp_path)

    captured: dict = {}

    def _spy(**kwargs):
        captured.update(kwargs)
        raise _SpawnProbe

    original = mcp_client.StdioServerParameters
    mcp_client.StdioServerParameters = _spy
    try:
        client = mcp_client.MCPClient(service)
        # Returns False by design: the probe was caught and recorded.
        # skip_enabled_check=True — "demo" is not in the default-enabled
        # set, and the probe targets the spawn site, not the enable gate.
        await client.connect_to_server("demo", skip_enabled_check=True)
    finally:
        mcp_client.StdioServerParameters = original

    assert captured.get("cwd") == "/srv/mcp-workers", (
        "the spawn site dropped the configured cwd — the child runs in the "
        "backend's working directory (E16)"
    )
