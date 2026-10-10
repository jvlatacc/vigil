"""The decoy-session read tool: in the manifest, dispatchable, bounded, and
principal-scoped.

The transcripts it answers with are evidence — attacker-typed credentials ride
in them as payload — so an unattributed caller is refused, the way an approval
is refused, and the bulk ``raw`` capture never leaves the evidence row.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest

from core.agents import tool_registry
from core.agents.builtins import BUILTIN_AGENTS
from core.agents.tool_registry import (
    MANIFEST,
    _decoy_transcript_key,
    execute_backend_tool,
)
from core.integrations.mcp import in_process
from core.integrations.mcp.surface import acting_as
from core.llm.tool_schemas import ALL_TOOLS
from tools.mcp import vigil

pytestmark = pytest.mark.unit

SESSION_ID = "sess-20261009-200102-ab12cd"
SERVICE = "ssh-decoy-01"
ROUTING_ACTION = "action-20261009-200102-ab12cd"


def _finding(**overrides):
    """One stored decoy-session Finding, in the shape the capture pipeline writes."""
    base = SimpleNamespace(
        finding_id=SESSION_ID,
        data_source="vigil-decoy",
        severity="high",
        timestamp=datetime(2026, 10, 9, 20, 31, 2),
        source_metadata={
            "decoy_service": SERVICE,
            "attacker_entity_key": "ip:203.0.113.7",
            "session_start": "2026-10-09T20:31:02Z",
            "session_end": "2026-10-09T20:44:51Z",
            "routing_action_id": ROUTING_ACTION,
        },
        entity_context={
            "src_ip": "203.0.113.7",
            "entity_keys": ["ip:203.0.113.7"],
            "decoy_service": SERVICE,
        },
        mitre_prediction_rows=[
            SimpleNamespace(technique_id="T1110.001", confidence=1.0)
        ],
    )
    return SimpleNamespace(**{**base.__dict__, **overrides})


def _transcript(**overrides):
    """The matching CaseEvidence row, in the shape the capture pipeline writes."""
    base = SimpleNamespace(
        evidence_id=7,
        name=f"decoy {SERVICE} session {SESSION_ID}",
        analysis_results={
            "decoy_service": SERVICE,
            "attacker_entity_key": "ip:203.0.113.7",
            "session_start": "2026-10-09T20:31:02Z",
            "session_end": "2026-10-09T20:44:51Z",
            "routing_action_id": ROUTING_ACTION,
            "auth_attempts": [
                {"user": "root", "result": "success", "credential": "canary"}
            ],
            "commands": ["whoami", "cat /etc/passwd"],
            "files_dropped": [{"name": "x.sh", "sha256": "9f86d081"}],
            "mitre_techniques": ["T1110.001", "T1078"],
            "mitre_names": {"T1110.001": "Password Guessing"},
            "raw": {"protocol_events": "the bulk capture lives here"},
        },
    )
    return SimpleNamespace(**{**base.__dict__, **overrides})


class FakeQuery:
    """Stands in for the ORM query chain; it does not evaluate criteria."""

    def __init__(self, rows):
        self._rows = rows
        self._cap = None

    def filter(self, *criteria):
        return self

    def order_by(self, *criteria):
        return self

    def limit(self, count):
        self._cap = count
        return self

    def all(self):
        return self._rows if self._cap is None else self._rows[: self._cap]


class FakeDB:
    """Stands in for the unit_of_work session: rows in memory, keyed by model.

    The data_source filter the real query applies is not evaluated here, so
    canned findings are always decoy findings.
    """

    def __init__(self, findings=(), evidence=()):
        self._findings = list(findings)
        self._evidence = list(evidence)

    def get(self, model, pk):
        if model.__name__ != "Finding":
            return None
        return next((f for f in self._findings if f.finding_id == pk), None)

    def query(self, model):
        rows = self._findings if model.__name__ == "Finding" else self._evidence
        return FakeQuery(rows)


def _fake_store(monkeypatch, db):
    """Swap the transaction seam for the in-memory store; reports whether it
    was ever opened."""
    opened = []

    @contextmanager
    def fake_uow(session=None):
        opened.append(True)
        yield db

    monkeypatch.setattr("core.storage.unit_of_work.unit_of_work", fake_uow)
    return opened


# ---------------------------------------------------------------------------
# Manifest membership and bounds
# ---------------------------------------------------------------------------


def test_listed_in_the_manifest():
    assert "query_decoy_sessions" in MANIFEST
    assert "query_decoy_sessions" in {tool["name"] for tool in ALL_TOOLS}
    published = {tool["name"] for tool in in_process.list_tools()}
    assert "query_decoy_sessions" in published


def test_the_router_lowers_its_row_cap():
    from core.agents import tools_router

    # The schema declares limit, so the caller's row ceiling reaches the tool
    # rather than only its answer.
    assert tools_router._schema_row_caps("query_decoy_sessions") == ("limit",)
    bounded = tools_router._bounded({"limit": 5000}, 10, "query_decoy_sessions")
    assert bounded["limit"] == 10


def test_limit_is_clamped_to_the_ceiling(monkeypatch):
    opened = _fake_store(monkeypatch, FakeDB(findings=[_finding()]))

    with acting_as("analyst"):
        ceiling = tool_registry.query_decoy_sessions(limit=10**6)
        assert ceiling["limit"] == tool_registry._DECOY_SESSIONS_MAX_LIMIT
        floor = tool_registry.query_decoy_sessions(limit=0)
    assert floor["limit"] == 1
    assert opened == [True, True]


def test_limit_must_be_an_integer(monkeypatch):
    opened = _fake_store(monkeypatch, FakeDB(findings=[_finding()]))
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions(limit="many")
    assert "limit must be an integer" in result["error"]
    assert opened == []  # refused before the store was opened


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_refuses_an_unattributed_caller(monkeypatch):
    opened = _fake_store(monkeypatch, FakeDB(findings=[_finding()]))

    result, handled = await execute_backend_tool("query_decoy_sessions", {})

    assert handled is True
    assert result == {"error": "Decoy sessions cannot be read: no principal is bound"}
    assert opened == []


@pytest.mark.asyncio
async def test_dispatch_reads_for_a_bound_principal(monkeypatch):
    opened = _fake_store(
        monkeypatch, FakeDB(findings=[_finding()], evidence=[_transcript()])
    )

    with acting_as("analyst"):
        result, handled = await execute_backend_tool("query_decoy_sessions", {})

    assert handled is True
    assert opened == [True]
    assert result["returned"] == 1
    assert result["sessions"][0]["session_id"] == SESSION_ID


# ---------------------------------------------------------------------------
# Row shaping
# ---------------------------------------------------------------------------


def test_rows_carry_the_transcript_without_the_raw_capture(monkeypatch):
    opened = _fake_store(
        monkeypatch, FakeDB(findings=[_finding()], evidence=[_transcript()])
    )
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions()

    row = result["sessions"][0]
    assert row["decoy_service"] == SERVICE
    assert row["attacker_entity_key"] == "ip:203.0.113.7"
    assert row["routing_action_id"] == ROUTING_ACTION
    assert row["commands"] == ["whoami", "cat /etc/passwd"]
    assert row["files_dropped"] == [{"name": "x.sh", "sha256": "9f86d081"}]
    assert row["auth_attempts"] == [
        {"user": "root", "result": "success", "credential": "canary"}
    ]
    assert row["mitre_names"] == {"T1110.001": "Password Guessing"}
    assert row["evidence_id"] == 7
    # raw is the drill-down, held in the evidence row; it never rides a row.
    assert "raw" not in row
    assert opened == [True]


def test_predictions_come_from_the_stored_prediction_rows(monkeypatch):
    opened = _fake_store(
        monkeypatch, FakeDB(findings=[_finding()], evidence=[_transcript()])
    )
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions()

    assert result["sessions"][0]["mitre_predictions"] == [
        {"technique_id": "T1110.001", "confidence": 1.0}
    ]
    assert opened == [True]


def test_a_session_without_its_transcript_still_returns(monkeypatch):
    opened = _fake_store(monkeypatch, FakeDB(findings=[_finding()], evidence=[]))
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions()

    row = result["sessions"][0]
    assert row["session_id"] == SESSION_ID
    assert row["mitre_predictions"], "predictions live on the Finding, not the evidence"
    assert "commands" not in row  # no transcript: the gap is visible, not faked
    assert opened == [True]


def test_has_more_is_honest(monkeypatch):
    second = _finding(finding_id="sess-2", timestamp=datetime(2026, 10, 9, 21, 0, 0))
    opened = _fake_store(
        monkeypatch, FakeDB(findings=[second, _finding()], evidence=[])
    )
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions(limit=1)

    assert result["returned"] == 1
    assert result["has_more"] is True
    assert opened == [True]


def test_session_id_scopes_to_one_session(monkeypatch):
    other = _finding(finding_id="sess-9", source_metadata={"decoy_service": SERVICE})
    opened = _fake_store(monkeypatch, FakeDB(findings=[_finding(), other], evidence=[]))
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions(session_id=SESSION_ID)

    assert result["returned"] == 1
    assert result["sessions"][0]["session_id"] == SESSION_ID
    assert result["has_more"] is False
    assert opened == [True]


@pytest.mark.parametrize("missing_id", ["sess-absent", SESSION_ID])
def test_an_unknown_session_id_is_an_empty_page_not_an_error(monkeypatch, missing_id):
    # The wrong data_source case: a real Finding id that is not a decoy session
    # reads the same as a nonexistent one — "captured nothing", not "query failed".
    opened = _fake_store(
        monkeypatch,
        FakeDB(
            findings=(
                [_finding(data_source="sysmon")] if missing_id == SESSION_ID else []
            )
        ),
    )
    with acting_as("analyst"):
        result = tool_registry.query_decoy_sessions(session_id=missing_id)

    assert result == {"returned": 0, "has_more": False, "limit": 20, "sessions": []}
    assert opened == [True]


def test_the_transcript_name_agrees_with_the_capture_pipeline():
    # The join key mirrors decoy_session_capture's evidence name — the static
    # agreement the capture-wire test pins from the decoy side.
    assert _decoy_transcript_key(SERVICE, SESSION_ID) == (
        f"decoy {SERVICE} session {SESSION_ID}"
    )


# ---------------------------------------------------------------------------
# The MCP mirror
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_mcp_mirror_delegates_to_the_backend_read(monkeypatch):
    seen = {}

    def spy(**kwargs):
        seen.update(kwargs)
        return {"returned": 0, "has_more": False, "limit": 20, "sessions": []}

    monkeypatch.setattr(tool_registry, "query_decoy_sessions", spy)

    text = vigil.query_decoy_sessions(session_id=SESSION_ID, limit=5)

    assert seen == {"session_id": SESSION_ID, "decoy_service": None, "limit": 5}
    assert json.loads(text)["returned"] == 0


def test_the_two_doors_publish_the_same_arguments():
    # The shared-doors contract, for this tool: the MCP wrapper and the
    # manifest must agree on the argument names a caller may pass.
    published_tools = {tool["name"]: tool for tool in in_process.list_tools()}
    published = set(
        (published_tools["query_decoy_sessions"].get("input_schema") or {}).get(
            "properties"
        )
        or {}
    )
    declared = set(MANIFEST["query_decoy_sessions"]["input_schema"]["properties"])
    assert published == declared == {"session_id", "decoy_service", "limit"}


def test_the_four_analysts_are_recommended_the_tool():
    by_id = {agent["id"]: agent for agent in BUILTIN_AGENTS}
    for agent_id in ("investigator", "responder", "mitre_analyst", "threat_intel"):
        assert "query_decoy_sessions" in by_id[agent_id]["recommended_tools"], agent_id
