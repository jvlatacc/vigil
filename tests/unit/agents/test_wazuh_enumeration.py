"""enumerate_wazuh_findings: the read-only Wazuh enumeration tool.

Mirrors test_case_records.py: the schema must exist in ALL_TOOLS, the handler
runs through execute_backend_tool with the service seams faked at the _data()
boundary, and an empty result is zeros — never an "error" key (#1470 spec,
AC-2..AC-5). The seams this must NOT take — a list_cases-style post-read scan
or a get_findings_stats-style 10,000-row read — raise if reached.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.agents.builtins import BUILTIN_AGENTS
from core.agents.tool_registry import execute_backend_tool
from core.llm.tool_schemas import ALL_TOOLS

pytestmark = pytest.mark.unit

TOOL = "enumerate_wazuh_findings"


def _wazuh_row(**overrides):
    """One finding row in the shape FindingSchema.dump emits."""
    row = {
        "finding_id": "f-20261009-001",
        "severity": "high",
        "status": "new",
        "timestamp": "2026-10-09T12:00:00+00:00",
        "title": "sshd: authentication failed.",
        "description": "Oct 09 12:00:01 web01 sshd[123]: Failed password for root",
        "anomaly_score": 5 / 15,
        "data_source": "elastic",
        "source_metadata": {
            "vendor": "wazuh",
            "wazuh_alert_id": "1765106558.123",
            "rule_id": "5710",
            "rule_level": 5,
            "rule_name": "sshd: authentication failed.",
            "agent_name": "web01",
        },
        "mitre_predictions": {"T1110": 0.9},
    }
    row.update(overrides)
    return row


class _StubData:
    """Fakes the DatabaseDataService seams the handler calls, recording each.

    The wrong data paths are guarded: the cases section must come from the
    SQL-side EXISTS seam, the summary from SQL aggregation — a post-read scan
    or a Python row read behind these names is exactly the pattern the tool
    exists to avoid.
    """

    def __init__(self, findings=(), total=0, cases=None, summary=None):
        self.findings = list(findings)
        self.total = total
        self.cases = cases if cases is not None else {"total": 0, "cases": []}
        self.summary = summary or {"total": 0, "by_severity": {}, "by_status": {}}
        self.calls: list[tuple[str, dict]] = []

    def count_wazuh_findings(self, **filters):
        self.calls.append(("count_wazuh_findings", filters))
        return self.total

    def find_wazuh_findings(self, *, limit, offset, **filters):
        self.calls.append(
            ("find_wazuh_findings", {**filters, "limit": limit, "offset": offset})
        )
        return self.findings

    def cases_containing_wazuh_findings(self, **filters):
        self.calls.append(("cases_containing_wazuh_findings", filters))
        return self.cases

    def summarize_wazuh_findings(self, **filters):
        self.calls.append(("summarize_wazuh_findings", filters))
        return self.summary

    def get_findings(self, **_kwargs):
        raise AssertionError("findings must come from the SQL-side seam")

    def get_cases(self):
        raise AssertionError("cases must come from the EXISTS seam")

    def get_findings_stats(self):
        raise AssertionError("summary must come from the SQL aggregation seam")


def _stub_registry(monkeypatch, stub):
    monkeypatch.setattr("core.agents.tool_registry._data", lambda: stub)


def test_schema_names_enumerate_wazuh_findings():
    spec = next(t for t in ALL_TOOLS if t.get("name") == TOOL)
    properties = spec["input_schema"]["properties"]
    # limit declared so the /internal invoke router's row cap reaches the tool.
    assert "limit" in properties
    assert "offset" in properties
    assert "rule_id" in properties


@pytest.mark.asyncio
async def test_enumeration_returns_the_envelope(monkeypatch):
    case = {"case_id": "case-1", "title": "Brute force", "status": "open"}
    stub = _StubData(
        findings=[_wazuh_row()],
        total=1,
        cases={"total": 1, "cases": [case]},
        summary={"total": 1, "by_severity": {"high": 1}, "by_status": {"new": 1}},
    )
    _stub_registry(monkeypatch, stub)

    result, handled = await execute_backend_tool(
        TOOL,
        {
            "severity": "high",
            "rule_id": "5710",
            "timestamp_start": "2026-10-01T00:00:00+00:00",
        },
    )

    assert handled is True
    assert "error" not in result
    assert result["total"] == 1
    assert result["offset"] == 0
    assert result["limit"] == 50
    assert result["has_more"] is False
    assert result["cases"] == {"total": 1, "cases": [case]}
    assert result["summary"] == {
        "total": 1,
        "by_severity": {"high": 1},
        "by_status": {"new": 1},
    }
    [row] = result["findings"]
    assert row["finding_id"] == "f-20261009-001"
    assert row["wazuh_alert_id"] == "1765106558.123"
    assert row["rule_id"] == "5710"
    assert row["rule_level"] == 5
    assert row["agent_name"] == "web01"
    assert row["mitre_predictions"] == {"T1110": 0.9}
    # The ISO window the model sent reaches the seams parsed, with the other
    # filters intact — one predicate builder answers for every seam.
    for _name, filters in stub.calls:
        assert filters["severity"] == "high"
        assert filters["rule_id"] == "5710"
        assert filters["timestamp_start"] == datetime(2026, 10, 1, tzinfo=timezone.utc)
        assert filters["timestamp_end"] is None


@pytest.mark.asyncio
async def test_empty_is_a_result_not_an_error(monkeypatch):
    stub = _StubData()
    _stub_registry(monkeypatch, stub)

    result, handled = await execute_backend_tool(TOOL, {})

    assert handled is True
    assert result == {
        "total": 0,
        "offset": 0,
        "limit": 50,
        "has_more": False,
        "findings": [],
        "cases": {"total": 0, "cases": []},
        "summary": {"total": 0, "by_severity": {}, "by_status": {}},
    }
    assert "error" not in result


@pytest.mark.asyncio
async def test_has_more_reflects_the_total(monkeypatch):
    stub = _StubData(findings=[_wazuh_row(), _wazuh_row()], total=3)
    _stub_registry(monkeypatch, stub)

    result, _handled = await execute_backend_tool(TOOL, {"offset": 0, "limit": 2})

    assert result["has_more"] is True
    assert len(result["findings"]) == 2


@pytest.mark.asyncio
async def test_a_malformed_time_bound_is_an_error_dict(monkeypatch):
    _stub_registry(monkeypatch, _StubData())

    result, handled = await execute_backend_tool(TOOL, {"timestamp_start": "yesterday"})

    assert handled is True
    assert "error" in result


@pytest.mark.asyncio
async def test_a_backend_failure_is_an_error_dict(monkeypatch):
    def _broken():
        raise RuntimeError("database is down")

    monkeypatch.setattr("core.agents.tool_registry._data", _broken)

    result, handled = await execute_backend_tool(TOOL, {})

    assert handled is True
    assert "error" in result


def test_exactly_the_findings_and_case_consumers_hold_the_grant():
    """triage/correlator enumerate findings; reporter/compliance read cases.

    A grant pinned to a set: adding an agent is a one-line edit plus this
    assertion (AC-5).
    """
    expected = {"triage", "correlator", "reporter", "compliance"}
    holders = {
        agent["id"]
        for agent in BUILTIN_AGENTS
        if TOOL in agent.get("recommended_tools", [])
    }
    assert holders == expected
