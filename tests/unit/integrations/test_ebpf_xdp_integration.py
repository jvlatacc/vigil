"""Tests for the eBPF/XDP enforcement integration slice.

Covers:
- core/integrations/ebpf_xdp/descriptor.py — auto-discovery by the _base glob
  (no central list to edit), the four configured fields, the one secret.
- core/integrations/ebpf_xdp/tool.py — the MCP surface: exactly the five tools
  when enabled, the not-configured no-op when disabled; the module-level REST
  helpers the approved-action executor imports, shaped to the
  services/enforcement contract (HTTP mocked).
- mcp-config.json — the ebpf-xdp entry declares the VIGIL_ENFORCEMENT_*
  placeholders, so the existing MCPService dormancy machinery keeps the server
  dormant-by-design when the env is unset.
- core/llm/chat_layers.py — the xdp_* containment tools are verb-destructive
  and never reachable from chat's ad-hoc surface; xdp_status is.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.integrations._base.descriptor import get_descriptor
from core.integrations.integration_secrets import env_var_for
from core.integrations.mcp.service import extract_required_env_vars
from core.llm.chat_layers import _is_destructive_mcp, integration_tools

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.unit

TOOL_NAMES = [
    "xdp_block_ip",
    "xdp_unblock_ip",
    "xdp_redirect_socket",
    "xdp_interdict_process",
    "xdp_status",
]


def _import_ebpf_xdp_tool():
    """Load core/integrations/ebpf_xdp/tool.py by path (no package side effects)."""
    spec = importlib.util.spec_from_file_location(
        "ebpf_xdp_tool_under_test",
        REPO_ROOT / "core" / "integrations" / "ebpf_xdp" / "tool.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ebpf_xdp_tool_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _enabled(xdp, url="http://127.0.0.1:6986", token="tok", **extra):
    """The integration enabled with a resolved config (secrets store mocked)."""
    with patch.object(xdp, "is_integration_enabled", return_value=True), patch.object(
        xdp,
        "resolve",
        return_value={
            "enforcement_url": url,
            "enforcement_token": token,
            "default_ttl_seconds": 3600,
            **extra,
        },
    ):
        yield


def _fake_response(status_code: int, body) -> MagicMock:
    fake = MagicMock()
    fake.status_code = status_code
    fake.content = json.dumps(body).encode()
    fake.json.return_value = body
    return fake


# ---------------------------------------------------------------------------
# Descriptor — auto-discovery and the deployment's env-var names
# ---------------------------------------------------------------------------


def test_descriptor_auto_discovered():
    d = get_descriptor("ebpf-xdp")
    assert d is not None
    assert d.field_names == (
        "enforcement_url",
        "enforcement_token",
        "default_interface",
        "default_ttl_seconds",
    )
    assert d.secret_fields == ("enforcement_token",)
    assert d.mcp_server_names == ("ebpf-xdp",)


def test_default_ttl_declared_as_int():
    d = get_descriptor("ebpf-xdp")
    ttl = next(f for f in d.fields if f.name == "default_ttl_seconds")
    assert ttl.coerce(None) == 3600
    assert ttl.coerce("900") == 900


def test_env_var_names_match_the_daemon_deployment():
    # The daemon (services/enforcement/cmd/enforcement/main.go) reads these very
    # names from the host env; the resolver's env fallback must spell them the
    # same way or one shared secret ends up with two names.
    assert env_var_for("ebpf-xdp", "enforcement_url") == "VIGIL_ENFORCEMENT_URL"
    assert env_var_for("ebpf-xdp", "enforcement_token") == "VIGIL_ENFORCEMENT_TOKEN"


# ---------------------------------------------------------------------------
# MCP surface — five tools when enabled; the disabled no-op
# ---------------------------------------------------------------------------


def test_five_tools_listed_when_enabled():
    xdp = _import_ebpf_xdp_tool()
    tools = asyncio.run(xdp.handle_list_tools())
    assert [t.name for t in tools] == TOOL_NAMES


def test_disabled_integration_is_a_noop_with_a_clear_error():
    xdp = _import_ebpf_xdp_tool()
    with patch.object(xdp, "is_integration_enabled", return_value=False):
        out = xdp.xdp_block_ip(ip="203.0.113.7", reason="test")
    assert out["success"] is False
    assert out["error"] == "ebpf_xdp_integration_disabled"
    # The MCP result contract flags a truthy top-level error key.
    assert out["error"]


def test_enabled_but_unresolved_config_is_still_the_noop():
    xdp = _import_ebpf_xdp_tool()
    with patch.object(xdp, "is_integration_enabled", return_value=True), patch.object(
        xdp,
        "resolve",
        return_value={"enforcement_url": None, "enforcement_token": None},
    ):
        out = xdp.xdp_status()
    assert out["error"] == "ebpf_xdp_integration_disabled"


# ---------------------------------------------------------------------------
# Dormancy — the mcp-config entry drives the existing required-env machinery
# ---------------------------------------------------------------------------


def test_mcp_config_entry_declares_both_required_env_vars():
    config = json.loads((REPO_ROOT / "mcp-config.json").read_text())
    entry = config["mcpServers"]["ebpf-xdp"]
    assert entry["command"] == "python3"
    assert entry["args"] == ["core/integrations/ebpf_xdp/tool.py"]
    assert entry["cwd"] == "${workspaceFolder}"
    assert extract_required_env_vars(entry.get("env"), entry.get("args", [])) == [
        "VIGIL_ENFORCEMENT_TOKEN",
        "VIGIL_ENFORCEMENT_URL",
    ]


# ---------------------------------------------------------------------------
# Chat ad-hoc exclusion — containment verbs, pinned for the kernel slice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "ebpf-xdp_xdp_block_ip",
        "ebpf-xdp_xdp_unblock_ip",
        "ebpf-xdp_xdp_redirect_socket",
        "ebpf-xdp_xdp_interdict_process",
    ],
)
def test_containment_tools_are_verb_destructive(name):
    assert _is_destructive_mcp(name) is True


def test_status_tool_is_not_destructive():
    assert _is_destructive_mcp("ebpf-xdp_xdp_status") is False


def test_chat_surface_reaches_only_xdp_status():
    tools = [
        {
            "name": f"ebpf-xdp_{n}",
            "description": "x",
            "input_schema": {"type": "object"},
        }
        for n in TOOL_NAMES
    ]
    reachable = {t["name"] for t in integration_tools(tools)}
    assert reachable == {"ebpf-xdp_xdp_status"}


# ---------------------------------------------------------------------------
# Module-level helpers — the executor's client, shaped to the wire contract
# ---------------------------------------------------------------------------


def test_helpers_importable_by_executor():
    xdp = _import_ebpf_xdp_tool()
    for name in TOOL_NAMES:
        assert callable(getattr(xdp, name)), name


def test_block_posts_the_contract_request():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(
        201,
        {
            "action_id": "aa-2026-10-09-4417",
            "state": "enforced",
            "evidence": {
                "attach_point": "eth0/xdp",
                "map": "/sys/fs/bpf/vigil/xdp_block_v1",
                "map_slot": 17,
                "counters": {"dropped_packets": 0},
            },
            "expires_at": "2026-10-09T23:12:04Z",
            "replayed": False,
        },
    )
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake) as posted:
        out = xdp.xdp_block_ip(
            ip="203.0.113.7",
            reason="C2",
            ttl_seconds=3600,
            action_id="aa-2026-10-09-4417",
        )
    assert out["success"] is True
    assert out["state"] == "enforced"
    assert out["evidence"]["map_slot"] == 17
    body = posted.call_args.kwargs["json"]
    assert body == {
        "action_id": "aa-2026-10-09-4417",
        "kind": "xdp_drop",
        "target": {"ip": "203.0.113.7", "port": 0, "pid": 0},
        "ttl_seconds": 3600,
        "reason": "C2",
        "idempotency_key": "xdp_block_ip:203.0.113.7",
    }
    headers = posted.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"


def test_block_omitted_action_id_is_deterministic_so_retries_replay():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(
        200, {"action_id": "x", "state": "enforced", "replayed": True}
    )
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake) as posted:
        xdp.xdp_block_ip(ip="203.0.113.7", reason="C2")
    body = posted.call_args.kwargs["json"]
    assert body["action_id"] == "xdp_block_ip:203.0.113.7"
    assert body["idempotency_key"] == "xdp_block_ip:203.0.113.7"


def test_block_uses_the_descriptor_default_ttl_when_omitted():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(201, {"action_id": "x", "state": "enforced"})
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake) as posted:
        xdp.xdp_block_ip(ip="203.0.113.7", reason="C2")
    assert posted.call_args.kwargs["json"]["ttl_seconds"] == 3600


def test_block_with_no_resolved_default_ttl_omits_the_field():
    # The daemon then applies its own default — one default per side is enough.
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(201, {"action_id": "x", "state": "enforced"})
    with _enabled(xdp, default_ttl_seconds=None), patch.object(
        xdp.httpx, "post", return_value=fake
    ) as posted:
        xdp.xdp_block_ip(ip="203.0.113.7", reason="C2")
    assert "ttl_seconds" not in posted.call_args.kwargs["json"]


def test_interdict_sends_pid_and_omits_ip():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(201, {"action_id": "x", "state": "enforced"})
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake) as posted:
        out = xdp.xdp_interdict_process(pid=4242, reason="coin miner")
    assert out["success"] is True
    body = posted.call_args.kwargs["json"]
    assert body["kind"] == "process_interdict"
    assert body["target"] == {"port": 0, "pid": 4242}
    assert "ip" not in body["target"]
    assert body["idempotency_key"] == "xdp_interdict_process:4242"


def test_redirect_carries_the_port_when_set():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(201, {"action_id": "x", "state": "enforced"})
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake) as posted:
        xdp.xdp_redirect_socket(ip="203.0.113.7", reason="forensics", port=8080)
    body = posted.call_args.kwargs["json"]
    assert body["kind"] == "socket_redirect"
    assert body["target"] == {"ip": "203.0.113.7", "port": 8080, "pid": 0}
    assert body["idempotency_key"] == "xdp_redirect_socket:203.0.113.7:8080"


def test_replayed_reply_reports_success_without_claiming_fresh_enforcement():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(
        200, {"action_id": "aa-1", "state": "enforced", "replayed": True}
    )
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake):
        out = xdp.xdp_block_ip(ip="203.0.113.7", reason="C2", action_id="aa-1")
    assert out["success"] is True
    assert out["replayed"] is True


def test_daemon_error_codes_pass_through_verbatim():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(
        422,
        {"error": "ttl_below_floor", "message": "below the 60s floor"},
    )
    with _enabled(xdp), patch.object(xdp.httpx, "post", return_value=fake):
        out = xdp.xdp_block_ip(ip="203.0.113.7", reason="C2", ttl_seconds=10)
    assert out["success"] is False
    assert out["error"] == "ttl_below_floor"


def test_unauthenticated_reply_is_reported_not_swallowed():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(401, {"error": "unauthorized", "message": "bad token"})
    with _enabled(xdp, token="wrong"), patch.object(
        xdp.httpx, "post", return_value=fake
    ):
        out = xdp.xdp_block_ip(ip="203.0.113.7", reason="C2")
    assert out["success"] is False
    assert out["error"] == "unauthorized"


def test_unreachable_enforcer_is_a_client_failure_not_a_kernel_verdict():
    xdp = _import_ebpf_xdp_tool()
    with _enabled(xdp), patch.object(
        xdp.httpx, "post", side_effect=httpx.ConnectError("connection refused")
    ):
        out = xdp.xdp_block_ip(ip="203.0.113.7", reason="C2")
    assert out["success"] is False
    assert out["error"] == "enforcer_unreachable"


def test_release_uses_the_delete_route_and_returns_released_state():
    xdp = _import_ebpf_xdp_tool()
    fake = _fake_response(
        200,
        {
            "action_id": "aa-1",
            "state": "released",
            "evidence": {
                "attach_point": "eth0/xdp",
                "map": "/sys/fs/bpf/vigil/xdp_block_v1",
                "map_slot": 17,
                "counters": {"dropped_packets": 4096},
            },
            "expires_at": "2026-10-09T23:12:04Z",
            "replayed": False,
            "released_at": "2026-10-09T22:12:04Z",
        },
    )
    with _enabled(xdp), patch.object(xdp.httpx, "delete", return_value=fake) as deleted:
        out = xdp.xdp_unblock_ip(action_id="aa-1")
    assert out["success"] is True
    assert out["state"] == "released"
    assert "/v1/actions/aa-1" in deleted.call_args.args[0]


def test_release_without_action_id_is_refused_locally():
    xdp = _import_ebpf_xdp_tool()
    with _enabled(xdp):
        out = xdp.xdp_unblock_ip(action_id=None)
    assert out["success"] is False
    assert out["error"] == "action_id required"


def test_status_composes_healthz_and_the_action_list():
    xdp = _import_ebpf_xdp_tool()
    health = _fake_response(
        200,
        {
            "status": "ok",
            "uptime_seconds": 30,
            "kernel_faked": "ci-fake",
            "primitives": {"xdp_drop": {"supported": True}},
        },
    )
    listing = _fake_response(
        200, {"actions": [{"action_id": "aa-1", "state": "enforced"}]}
    )
    with _enabled(xdp), patch.object(
        xdp.httpx, "get", side_effect=[health, listing]
    ) as getter:
        out = xdp.xdp_status()
    assert out["success"] is True
    assert out["primitives"]["xdp_drop"]["supported"] is True
    assert [a["action_id"] for a in out["actions"]] == ["aa-1"]
    # healthz is deliberately unauthenticated; the action list carries the token.
    assert "/healthz" in getter.call_args_list[0].args[0]
    assert "/v1/actions" in getter.call_args_list[1].args[0]
    assert getter.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer tok"


def test_status_survives_a_failed_list_call():
    xdp = _import_ebpf_xdp_tool()
    health = _fake_response(
        200,
        {"status": "ok", "uptime_seconds": 1, "kernel_faked": "", "primitives": {}},
    )
    forbidden = _fake_response(401, {"error": "unauthorized", "message": "no"})
    with _enabled(xdp), patch.object(xdp.httpx, "get", side_effect=[health, forbidden]):
        out = xdp.xdp_status()
    assert out["success"] is True
    assert out["actions"] == []
    assert out["actions_error"] == "unauthorized"
