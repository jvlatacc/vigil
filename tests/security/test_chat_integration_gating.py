"""Chat's reachable set defers to the dispatch gate's classification.

E5 (spec area B): chat's verb list had no write verbs, so
``pagerduty_manage_incidents`` read as ``read_only`` and rode that label
straight into the model. The reachable-set filter now asks the same question
the dispatch gate asks -- descriptor declaration first, fail-closed name
pattern otherwise -- so a tool classified mutating is unreachable here
whatever its name tokens spell. Chat does not *queue*: it has no
approval-resume path, so a parked call would hang the conversation.

The last test is the PagerDuty config ratchet: the shipped entry starts the
server without ``--enable-write-tools``, so its write tools never register to
reach at all. Re-adding the flag is a per-deployment opt-in, and this is the
tripwire that forces it to be a decision. On the pre-fix code these fail:
the write tools were reachable and the flag shipped on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.integrations.pagerduty.descriptor import PAGERDUTY  # noqa: E402
from core.llm.chat_layers import changes_for_tool, integration_tools  # noqa: E402

pytestmark = pytest.mark.unit

CONFIG = REPO / "mcp-config.json"


def _mcp(name, description="something useful"):
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object"},
    }


def _reachable(tools):
    return {t["name"] for t in integration_tools(tools)}


def test_pagerduty_write_tools_are_not_reachable():
    tools = [
        _mcp("pagerduty_create_incident"),
        _mcp("pagerduty_manage_incidents"),
        _mcp("pagerduty_add_responders"),
        _mcp("pagerduty_list_incidents"),
        _mcp("pagerduty_get_incident"),
    ]
    assert _reachable(tools) == {
        "pagerduty_list_incidents",
        "pagerduty_get_incident",
    }


def test_every_declared_pagerduty_write_tool_is_out_of_reach():
    from core.integrations._base.descriptor import flat_name_requires_approval

    for tool in PAGERDUTY.mutating_tools:
        name = f"pagerduty_{tool}"
        assert flat_name_requires_approval(name) is True, name
        assert name not in _reachable([_mcp(name)]), name


def test_write_shaped_tools_do_not_ride_a_read_only_label():
    assert changes_for_tool("pagerduty_manage_incidents") == "asks_first"
    assert changes_for_tool("pagerduty_create_incident") == "asks_first"
    assert changes_for_tool("pagerduty_list_incidents") == "read_only"


def test_pattern_gated_tools_are_out_of_reach():
    tools = [
        _mcp("carbon-black_cb_quarantine"),
        _mcp("microsoft-defender_mde_isolate"),
        _mcp("virustotal_get_ip_report"),
    ]
    assert _reachable(tools) == {"virustotal_get_ip_report"}


def test_shipped_pagerduty_entry_carries_no_write_tools_flag():
    # The ratchet (E5's config half): pagerduty ships read-only. Its 22 write
    # tools are a per-deployment opt-in -- re-adding --enable-write-tools is
    # meant to be a decision, and this is where making it un-decided fails.
    entry = json.loads(CONFIG.read_text())["mcpServers"]["pagerduty"]
    assert not any(
        arg.startswith("--enable-write-tools") for arg in entry.get("args", [])
    )
