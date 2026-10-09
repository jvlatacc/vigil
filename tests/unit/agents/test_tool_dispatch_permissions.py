# The tool plane's dispatch gate. Backend tools answer through
# execute_backend_tool under tools.invoke; MCP tools answer through
# execute_mcp_tool under mcp.use, before any transport work; and Vigil's own
# server refuses at the same gate whatever door the call arrived through.
# These tests bind and refuse principals without a database: the engine behind
# the gate is AuthService.check_permission's, covered by its own suite.

from __future__ import annotations

import pytest

from core.agents import tool_registry
from core.agents.mcp_tools import execute_mcp_tool
from core.agents.tool_registry import ToolDenied, execute_backend_tool
from core.integrations.mcp.surface import acting_as

pytestmark = pytest.mark.unit


@pytest.fixture
def grants(monkeypatch):
    """A permission engine stub: holds exactly what ``holding`` names."""
    state = {"holding": set(), "asked": []}

    def fake(username: str, permission: str) -> bool:
        state["asked"].append((username, permission))
        return permission in state["holding"]

    monkeypatch.setattr(tool_registry, "username_has_permission", fake)
    return state


def _holding(grants, *permissions: str) -> None:
    grants["holding"] = set(permissions)


# --- The backend ladder: tools.invoke ----------------------------------------


class TestBackendDispatch:
    async def test_a_holder_executes(self, grants, monkeypatch):
        _holding(grants, "tools.invoke")
        ran = []

        def fake(args):
            ran.append(args)
            return {"ok": True}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        with acting_as("analyst"):
            result, handled = await execute_backend_tool("case_records", {})

        assert handled is True
        assert ran == [{}]
        assert result == {"ok": True}

    async def test_a_caller_without_the_permission_is_denied_before_the_tool_runs(
        self, grants, monkeypatch
    ):
        _holding(grants)  # nothing
        ran = []

        def fake(args):
            ran.append(args)
            return {}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        with acting_as("viewer"), pytest.raises(ToolDenied) as raised:
            await execute_backend_tool("case_records", {})

        assert ran == []  # nothing executed: no database, no side effects
        assert raised.value.tool_name == "case_records"
        assert raised.value.permission == "tools.invoke"
        assert raised.value.caller == "viewer"

    async def test_a_headless_run_passes_unchecked(self, grants, monkeypatch):
        # A hunt binds nobody; there is no principal to check against until
        # runs stamp their initiator. Nothing here may change under it.
        _holding(grants)  # nothing -- the check must not even be asked
        ran = []

        def fake(args):
            ran.append(args)
            return {"ok": True}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        result, handled = await execute_backend_tool("case_records", {})

        assert handled is True
        assert ran == [{}]
        assert grants["asked"] == []

    async def test_an_mcp_name_is_not_refused_by_the_backend_gate(self, grants):
        # The manifest is the backend gate's whole reach: an MCP tool name is
        # not in it, so a caller holding only mcp.use falls through to the MCP
        # half instead of being refused by a permission that does not apply.
        _holding(grants, "mcp.use")

        with acting_as("analyst"):
            result, handled = await execute_backend_tool("crowdstrike_isolate_host", {})

        assert (result, handled) == (None, False)
        assert grants["asked"] == []


# --- The MCP half: mcp.use, before any transport -----------------------------


class _Registry:
    """Knows one vendor tool and one Vigil tool, and nothing else."""

    def __init__(self, servers, names):
        self._servers, self._names = servers, names

    def get_active_servers(self):
        return list(self._servers)

    def get_tool_names(self):
        return list(self._names)


class _Client:
    def __init__(self):
        self.calls = []

    async def call_tool(self, server, tool, args, timeout):
        self.calls.append((server, tool, args, timeout))
        return {"content": [{"type": "text", "text": '{"ok": true}'}]}


class TestMcpDispatch:
    async def test_a_holder_reaches_the_server(self, grants, monkeypatch):
        _holding(grants, "mcp.use")
        client = _Client()

        import core.integrations.mcp.client as client_module

        monkeypatch.setattr(client_module, "process_mcp_client", lambda: client)

        with acting_as("analyst"):
            rows, handled = await execute_mcp_tool(
                "crowdstrike_isolate_host",
                {"host": "10.0.0.5"},
                5.0,
                _Registry(["crowdstrike"], ["crowdstrike_isolate_host"]),
            )

        assert handled is True
        assert rows == [{"ok": True}]
        assert client.calls == [
            ("crowdstrike", "isolate_host", {"host": "10.0.0.5"}, 5.0)
        ]

    async def test_a_denial_happens_before_any_transport(self, grants, monkeypatch):
        _holding(grants)  # nothing

        import core.integrations.mcp.client as client_module
        import core.integrations.mcp.in_process as in_process

        def no_client():
            raise AssertionError("the client was reached on a denied dispatch")

        async def no_in_process(name, args, timeout=30.0):
            raise AssertionError("the in-process call ran on a denied dispatch")

        monkeypatch.setattr(client_module, "process_mcp_client", no_client)
        monkeypatch.setattr(in_process, "call_tool", no_in_process)

        registry = _Registry(["crowdstrike"], ["crowdstrike_isolate_host"])
        with acting_as("viewer"), pytest.raises(ToolDenied) as raised:
            await execute_mcp_tool("crowdstrike_isolate_host", {}, 5.0, registry)

        assert raised.value.permission == "mcp.use"
        assert raised.value.tool_name == "crowdstrike_isolate_host"

    async def test_a_headless_run_passes_unchecked(self, grants, monkeypatch):
        _holding(grants)  # nothing -- the check must not even be asked
        client = _Client()

        import core.integrations.mcp.client as client_module

        monkeypatch.setattr(client_module, "process_mcp_client", lambda: client)

        rows, handled = await execute_mcp_tool(
            "crowdstrike_isolate_host",
            {},
            5.0,
            _Registry(["crowdstrike"], ["crowdstrike_isolate_host"]),
        )

        assert handled is True
        assert client.calls != []
        assert grants["asked"] == []

    async def test_a_name_no_server_carries_is_refused_not_denied(self, grants):
        # The gate sits after the known-name guard, so a denial names a tool
        # that exists; an unknown name stays the refusal it always was.
        _holding(grants)  # nothing

        with acting_as("viewer"):
            result, handled = await execute_mcp_tool(
                "ghost_tool", {}, 5.0, _Registry(["crowdstrike"], [])
            )

        assert (result, handled) == (None, False)
        assert grants["asked"] == []


# --- The run-stamped half: a headless run authorizes against its initiator ---


class TestRunStampedDispatch:
    async def test_a_run_whose_initiator_lacks_the_permission_is_denied(
        self, grants, monkeypatch
    ):
        # The run names itself; the person who started it holds nothing, so the
        # dispatch refuses exactly as a bound viewer's would.
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: "viewer")
        _holding(grants)  # nothing
        ran = []

        def fake(args):
            ran.append(args)
            return {}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        with pytest.raises(ToolDenied) as raised:
            await execute_backend_tool("case_records", {}, run_id="run-1")

        assert ran == []  # nothing executed: no database, no side effects
        assert raised.value.tool_name == "case_records"
        assert raised.value.permission == "tools.invoke"
        assert raised.value.caller == "viewer"

    async def test_a_run_whose_initiator_holds_the_permission_executes(
        self, grants, monkeypatch
    ):
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: "analyst")
        _holding(grants, "tools.invoke")
        ran = []

        def fake(args):
            ran.append(args)
            return {"ok": True}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        result, handled = await execute_backend_tool("case_records", {}, run_id="run-1")

        assert handled is True
        assert ran == [{}]
        assert grants["asked"] == [("analyst", "tools.invoke")]

    async def test_a_run_that_names_no_person_passes_unchecked(
        self, grants, monkeypatch
    ):
        # The orchestrator's schedules and an unnamed start have no person
        # behind them: run_initiator answers None, and the dispatch passes as
        # it did before runs carried an initiator at all.
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: None)
        _holding(grants)  # nothing -- the check must not even be asked
        ran = []

        def fake(args):
            ran.append(args)
            return {"ok": True}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        result, handled = await execute_backend_tool("case_records", {}, run_id="run-1")

        assert handled is True
        assert ran == [{}]
        assert grants["asked"] == []

    async def test_a_bound_caller_outranks_the_run_stamp(self, grants, monkeypatch):
        # The person bound to the call is who the check answers for; the run's
        # stamp is read only when nobody is bound.
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: "admin")
        _holding(grants)  # nothing -- viewer is bound, admin is never asked
        ran = []

        def fake(args):
            ran.append(args)
            return {}

        monkeypatch.setattr(tool_registry, "_case_records", fake)

        with acting_as("viewer"), pytest.raises(ToolDenied) as raised:
            await execute_backend_tool("case_records", {}, run_id="run-1")

        assert raised.value.caller == "viewer"
        assert grants["asked"] == [("viewer", "tools.invoke")]

    async def test_an_mcp_tool_is_gated_mcp_use_against_the_initiator(
        self, grants, monkeypatch
    ):
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: "viewer")
        _holding(grants)  # nothing

        import core.integrations.mcp.client as client_module

        def no_client():
            raise AssertionError("the client was reached on a denied dispatch")

        monkeypatch.setattr(client_module, "process_mcp_client", no_client)

        registry = _Registry(["crowdstrike"], ["crowdstrike_isolate_host"])
        with pytest.raises(ToolDenied) as raised:
            await execute_mcp_tool(
                "crowdstrike_isolate_host", {}, 5.0, registry, run_id="run-1"
            )

        assert raised.value.permission == "mcp.use"
        assert raised.value.caller == "viewer"

    async def test_an_mcp_run_that_names_no_person_reaches_the_server(
        self, grants, monkeypatch
    ):
        monkeypatch.setattr(tool_registry, "run_initiator", lambda run_id: None)
        _holding(grants)  # nothing -- the check must not even be asked
        client = _Client()

        import core.integrations.mcp.client as client_module

        monkeypatch.setattr(client_module, "process_mcp_client", lambda: client)

        rows, handled = await execute_mcp_tool(
            "crowdstrike_isolate_host",
            {},
            5.0,
            _Registry(["crowdstrike"], ["crowdstrike_isolate_host"]),
            run_id="run-1",
        )

        assert handled is True
        assert client.calls != []
        assert grants["asked"] == []


# --- Vigil's own server: one gate for every door -----------------------------


class TestVigilsOwnServer:
    async def test_a_denial_answers_as_an_error_result(self, grants):
        _holding(grants)  # nothing

        from tools.mcp import vigil

        with acting_as("viewer"):
            result = await vigil.mcp.call_tool("list_findings", {})

        # An error result carrying the denial's own words, not the tool's
        # answer: the gate refused before the tool could run anything.
        assert result.is_error is True
        assert "mcp.use" in result.content[0].text
        assert "viewer" in result.content[0].text

    async def test_a_holder_reaches_the_real_dispatch(self, grants):
        _holding(grants, "mcp.use")

        from tools.mcp import vigil

        # The gate lets it through; the tool manager answers for the name. An
        # unknown name raising the manager's error is the proof of delegation.
        with acting_as("analyst"), pytest.raises(Exception) as raised:
            await vigil.mcp.call_tool("no_such_tool_here", {})

        assert not isinstance(raised.value, ToolDenied)
        assert "no_such_tool_here" in str(raised.value)


class TestTheDenialItself:
    def test_names_the_caller_the_tool_and_the_permission(self):
        denial = ToolDenied("splunk_execute", "mcp.use", "viewer")
        assert denial.tool_name == "splunk_execute"
        assert denial.permission == "mcp.use"
        assert denial.caller == "viewer"
        assert "viewer" in str(denial)
        assert "splunk_execute" in str(denial)
        assert "mcp.use" in str(denial)

    def test_an_unbound_denial_says_so(self):
        denial = ToolDenied("splunk_execute", "mcp.use", None)
        assert "no principal" in str(denial)
