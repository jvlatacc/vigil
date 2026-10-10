"""The operational tools drive the same modules the HTTP twins drive.

Spec D3 (headless Vigil): twelve tools on /mcp for the run lifecycle, the
workflow catalog, findings, case operations and case metrics. Three contracts
are pinned per tool:

- delegation -- the tool calls the same domain function its frozen HTTP twin
  calls, so the two surfaces cannot disagree; no business logic in the tool
  layer. The domain function is patched and the hand-off asserted, not the
  service internals.
- caller binding -- the actor is the surface's bound caller (``caller()``),
  never an argument. One schema-level test holds the whole set: no tool
  publishes an actor-shaped parameter at all.
- error shape -- a failure comes back as ``{"error": ...}`` JSON; a tool never
  raises into the MCP transport.

The tests patch the domain modules, not the HTTP layer: the HTTP twins keep
their own request/response shapes, which the contract tests already pin.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

OPERATIONAL_TOOLS = frozenset(
    {
        "start_agent_run",
        "get_agent_run",
        "queue_agent_directive",
        "cancel_agent_run",
        "resume_agent_run",
        "list_workflows",
        "get_workflow",
        "update_finding",
        "search_cases",
        "merge_cases",
        "export_case_iocs",
        "get_case_metrics",
    }
)

# Every name a tool could use to let its caller choose the recorded actor.
# The surface binds the caller; an argument by any of these names would let a
# caller choose what the record says about who acted.
_ACTOR_PARAM_NAMES = {
    "actor",
    "actor_id",
    "approved_by",
    "created_by",
    "decided_by",
    "enqueued_by",
    "rejected_by",
    "updated_by",
    "user_id",
    "username",
}


@contextmanager
def _any_session():
    """A stand-in for the tool file's own session helper: these tests pin the
    hand-off, not the database."""
    yield MagicMock(name="session")


@pytest.fixture
def caller_named():
    """The surface caller is bound to a name, the way a credential does."""
    with patch(
        "core.integrations.mcp.surface.current_caller", return_value="nestor"
    ):
        yield "nestor"


def _json(out):
    return json.loads(out)


# --- Actor binding (schema level) --------------------------------------------


def test_no_operational_tool_takes_the_actor_as_an_argument():
    from tools.mcp import vigil

    offenders = []
    for tool in vigil.mcp._tool_manager.list_tools():
        if tool.name not in OPERATIONAL_TOOLS:
            continue
        named = set((tool.parameters or {}).get("properties") or {})
        leaked = sorted(named & _ACTOR_PARAM_NAMES)
        if leaked:
            offenders.append(f"{tool.name}: {', '.join(leaked)}")

    assert not offenders, (
        "These tools let the caller choose the recorded actor, which makes the "
        f"record worthless: {offenders}. The actor is caller()."
    )


# --- Agent runs ---------------------------------------------------------------


def test_start_agent_run_delegates_and_binds_the_caller(caller_named):
    from core.agents import run_start
    from tools.mcp import vigil

    captured = {}

    async def fake_start(**kwargs):
        captured.update(kwargs)
        return {"run_id": "r-1", "job_id": "j-1"}

    with patch.object(run_start, "start_run", fake_start):
        out = _json(
            asyncio.run(
                vigil.start_agent_run(
                    playbook="scenarios/lateral-movement.yaml",
                    config="configs/lab-deployment.yaml",
                    run_kind="hunt",
                    prompt="sweep the pivot",
                    overrides={"max_steps": 5},
                )
            )
        )

    assert out == {"run_id": "r-1", "job_id": "j-1"}
    assert captured["enqueued_by"] == caller_named
    assert captured["run_kind"] == "hunt"
    assert captured["playbook"] == "scenarios/lateral-movement.yaml"
    assert captured["config"] == "configs/lab-deployment.yaml"
    assert captured["overrides"] == {"max_steps": 5}


def test_start_agent_run_reports_a_queue_failure_as_json():
    from core.agents import run_start
    from tools.mcp import vigil

    async def failing(**kwargs):
        raise run_start.RunQueueUnavailable("redis down")

    with patch.object(run_start, "start_run", failing):
        out = _json(asyncio.run(vigil.start_agent_run(playbook="p", config="c")))

    assert "error" in out and "redis down" in out["error"]


def test_get_agent_run_delegates_to_the_shared_read():
    from core.agents import run_status as run_status_module
    from tools.mcp import vigil

    captured = {}

    def fake_read(session, run_id):
        captured["session"] = session
        captured["run_id"] = run_id
        return {"run_id": run_id, "status": "running", "events": 3}

    with patch.object(run_status_module, "run_status", fake_read), patch(
        "tools.mcp.vigil._service_session", _any_session
    ):
        out = _json(vigil.get_agent_run("r-1"))

    assert out["status"] == "running"
    assert captured["run_id"] == "r-1"


def test_get_agent_run_unknown_run_is_an_error_not_a_crash():
    from core.agents import run_status as run_status_module
    from tools.mcp import vigil

    with patch.object(run_status_module, "run_status", lambda s, r: None), patch(
        "tools.mcp.vigil._service_session", _any_session
    ):
        out = _json(vigil.get_agent_run("nope"))

    assert out == {"error": "no such run: nope"}


def test_queue_agent_directive_delegates_and_binds_the_caller(caller_named):
    from core.agents import directives
    from tools.mcp import vigil

    captured = {}

    def fake_enqueue(session, **kwargs):
        captured.update(kwargs)
        return {"directive_id": "d-1", "kind": "redirect", "created_at": "now"}

    with patch.object(directives, "enqueue_directive", fake_enqueue), patch(
        "tools.mcp.vigil._service_session", _any_session
    ):
        out = _json(
            vigil.queue_agent_directive("r-1", kind="redirect", text="follow the pivot")
        )

    assert out["directive_id"] == "d-1"
    assert captured["actor"] == caller_named
    assert captured["body"] == "follow the pivot"


def test_queue_agent_directive_refusal_is_json():
    from core.agents import directives
    from tools.mcp import vigil

    def refusing(session, **kwargs):
        raise directives.InvalidDirective("unknown kind: nudge")

    with patch.object(directives, "enqueue_directive", refusing), patch(
        "tools.mcp.vigil._service_session", _any_session
    ):
        out = _json(vigil.queue_agent_directive("r-1", kind="nudge"))

    assert "unknown kind" in out["error"]


def test_cancel_agent_run_delegates_to_run_control(caller_named):
    from core.response.approval_service import ApprovalService
    from core.workflows import run_control
    from core.workflows.workflow_run_service import WorkflowRunService
    from tools.mcp import vigil

    captured = {}

    async def fake_cancel(run_id, reason, actor, run_service, approval_service):
        captured.update(
            run_id=run_id,
            reason=reason,
            actor=actor,
            run_service=run_service,
            approval_service=approval_service,
        )
        return {"status": "cancelled"}

    with patch.object(run_control, "cancel_run", fake_cancel):
        out = _json(asyncio.run(vigil.cancel_agent_run("r-1", reason="superseded")))

    assert out == {"status": "cancelled"}
    assert captured["actor"] == caller_named
    assert captured["reason"] == "superseded"
    # The same services the HTTP twin's Depends() provides -- not bespoke ones.
    assert isinstance(captured["run_service"], WorkflowRunService)
    assert isinstance(captured["approval_service"], ApprovalService)


def test_cancel_agent_run_unknown_run_is_json():
    from core.workflows import run_control
    from tools.mcp import vigil

    async def missing(run_id, reason, actor, run_service, approval_service):
        raise run_control.RunNotFound(f"no such run: {run_id}")

    with patch.object(run_control, "cancel_run", missing):
        out = _json(asyncio.run(vigil.cancel_agent_run("nope", reason="x")))

    assert "no such run" in out["error"]


def test_resume_agent_run_delegates_to_run_control(caller_named):
    from core.response.approval_service import ApprovalService
    from core.workflows import run_control
    from core.workflows.workflow_run_service import WorkflowRunService
    from tools.mcp import vigil

    captured = {}

    async def fake_resume(run_id, decided_by, run_service, approval_service):
        captured.update(
            run_id=run_id,
            decided_by=decided_by,
            run_service=run_service,
            approval_service=approval_service,
        )
        return {"status": "running", "resumed": True}

    with patch.object(run_control, "resume_paused_run", fake_resume):
        out = _json(asyncio.run(vigil.resume_agent_run("r-1")))

    assert out == {"status": "running", "resumed": True}
    assert captured["decided_by"] == caller_named
    assert isinstance(captured["run_service"], WorkflowRunService)
    assert isinstance(captured["approval_service"], ApprovalService)


def test_resume_agent_run_without_pending_approval_is_json():
    from core.workflows import run_control
    from tools.mcp import vigil

    async def no_approval(run_id, decided_by, run_service, approval_service):
        raise run_control.NoPendingApproval(f"Run {run_id} has no pending approval")

    with patch.object(run_control, "resume_paused_run", no_approval):
        out = _json(asyncio.run(vigil.resume_agent_run("r-1")))

    assert "no pending approval" in out["error"]


# --- Workflow catalog ----------------------------------------------------------


def test_list_workflows_delegates_to_the_catalog():
    from core.workflows import catalog
    from core.workflows.workflows_service import WorkflowsService
    from tools.mcp import vigil

    captured = {}

    def fake_listing(service):
        captured["service"] = service
        return {"workflows": [{"workflow_id": "sweep"}], "count": 1}

    with patch.object(catalog, "listing", fake_listing):
        out = _json(vigil.list_workflows())

    assert out["count"] == 1
    assert isinstance(captured["service"], WorkflowsService)


def test_get_workflow_delegates_to_the_catalog_detail():
    from core.workflows import catalog
    from tools.mcp import vigil

    with patch.object(
        catalog, "detail", lambda service, workflow_id: {"workflow_id": workflow_id}
    ):
        out = _json(vigil.get_workflow("sweep"))

    assert out == {"workflow_id": "sweep"}


def test_get_workflow_missing_is_json_not_null():
    from core.workflows import catalog
    from tools.mcp import vigil

    with patch.object(catalog, "detail", lambda service, workflow_id: None):
        out = _json(vigil.get_workflow("ghost"))

    assert out == {"error": "Workflow not found: ghost"}


# --- Findings -------------------------------------------------------------------


def _finding_service(get_finding=None, update_finding=None):
    service = MagicMock(name="data_service")
    service.get_finding.return_value = get_finding
    service.update_finding.return_value = update_finding
    return service


def test_update_finding_delegates_to_the_data_service():
    from tools.mcp import vigil

    service = _finding_service(
        get_finding={"finding_id": "f-1"}, update_finding=True
    )

    with patch.object(vigil, "get_data_service", return_value=service):
        out = _json(vigil.update_finding("f-1", severity="critical", status="new"))

    assert out["success"] is True
    assert out["updated_fields"] == ["severity", "status"]
    assert out["finding"] == {"finding_id": "f-1"}
    service.update_finding.assert_called_once_with(
        "f-1", severity="critical", status="new"
    )


def test_update_finding_missing_finding_is_json():
    from tools.mcp import vigil

    with patch.object(
        vigil, "get_data_service", return_value=_finding_service(get_finding=None)
    ):
        out = _json(vigil.update_finding("ghost", severity="critical"))

    assert out == {"error": "Finding not found"}


def test_update_finding_with_no_fields_is_json():
    from tools.mcp import vigil

    service = _finding_service(get_finding={"finding_id": "f-1"})
    with patch.object(vigil, "get_data_service", return_value=service):
        out = _json(vigil.update_finding("f-1"))

    assert out == {"error": "No updates provided"}
    service.update_finding.assert_not_called()


# --- Case operations --------------------------------------------------------------


def test_search_cases_delegates_to_the_search_service():
    from core.cases import case_search_service
    from tools.mcp import vigil

    captured = {}

    class FakeSearch:
        def search_cases(self, **kwargs):
            captured.update(kwargs)
            return {"results": [], "count": 0}

    with patch.object(case_search_service, "CaseSearchService", FakeSearch):
        out = _json(
            vigil.search_cases(
                query_text="lateral movement",
                status=["open"],
                created_after="2026-01-01T00:00:00Z",
            )
        )

    assert out == {"results": [], "count": 0}
    assert captured["status"] == ["open"]
    assert captured["created_after"] == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_search_cases_failure_is_json():
    from core.cases import case_search_service
    from tools.mcp import vigil

    class FailingSearch:
        def search_cases(self, **kwargs):
            raise RuntimeError("search index offline")

    with patch.object(case_search_service, "CaseSearchService", FailingSearch):
        out = _json(vigil.search_cases())

    assert "search index offline" in out["error"]


def test_merge_cases_delegates_and_binds_the_caller(caller_named):
    from core.cases import case_workflow_service
    from tools.mcp import vigil

    captured = {}

    class FakeWorkflowService:
        def merge_cases(self, target, source, username):
            captured.update(target=target, source=source, username=username)
            return 4

    data_service = MagicMock(name="data_service")
    data_service.get_case.return_value = {"case_id": "c-1"}

    with patch.object(
        case_workflow_service, "CaseWorkflowService", FakeWorkflowService
    ), patch.object(vigil, "get_data_service", return_value=data_service):
        out = _json(vigil.merge_cases("c-1", source_case_id="c-2"))

    assert out["success"] is True
    assert out["findings_moved"] == 4
    assert out["source_case_status"] == "closed"
    assert captured == {"target": "c-1", "source": "c-2", "username": caller_named}


def test_merge_cases_refuses_to_merge_a_case_into_itself(caller_named):
    from core.cases import case_workflow_service
    from tools.mcp import vigil

    class NeverCalled:
        def merge_cases(self, *args, **kwargs):
            raise AssertionError("merge_cases must not be called on a self-merge")

    with patch.object(
        case_workflow_service, "CaseWorkflowService", NeverCalled
    ):
        out = _json(vigil.merge_cases("c-1", source_case_id="c-1"))

    assert out == {"error": "Cannot merge a case into itself"}


def test_export_case_iocs_dispatches_by_format():
    from core.cases import case_ioc_service
    from tools.mcp import vigil

    class FakeIOCService:
        def export_iocs_json(self, case_id):
            return '{"iocs": []}'

        def export_iocs_csv(self, case_id):
            return "type,value"

        def export_iocs_stix(self, case_id):
            return {"type": "bundle"}

    with patch.object(case_ioc_service, "CaseIOCService", FakeIOCService):
        as_json = _json(vigil.export_case_iocs("c-1"))
        as_csv = _json(vigil.export_case_iocs("c-1", format="csv"))
        as_stix = _json(vigil.export_case_iocs("c-1", format="stix"))

    assert as_json == {"format": "json", "content": '{"iocs": []}'}
    assert as_csv == {"format": "csv", "content": "type,value"}
    assert as_stix == {"format": "stix", "content": {"type": "bundle"}}


def test_export_case_iocs_failure_is_json():
    from core.cases import case_ioc_service
    from tools.mcp import vigil

    class FailingIOCService:
        def export_iocs_json(self, case_id):
            raise RuntimeError("no such case")

    with patch.object(case_ioc_service, "CaseIOCService", FailingIOCService):
        out = _json(vigil.export_case_iocs("ghost"))

    assert "no such case" in out["error"]


# --- Case metrics ------------------------------------------------------------------


def test_get_case_metrics_summary_delegates_to_the_shared_read():
    from core.cases import case_metrics_queries
    from tools.mcp import vigil

    captured = {}

    def fake_summary(start, end):
        captured.update(start=start, end=end)
        return {"total_cases": 3}

    with patch.object(case_metrics_queries, "summary", fake_summary):
        out = _json(
            vigil.get_case_metrics(
                metric="summary",
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-02-01T00:00:00Z",
            )
        )

    assert out == {"total_cases": 3}
    assert captured["start"] == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_get_case_metrics_session_reads_get_the_tool_session():
    from core.cases import case_metrics_queries
    from tools.mcp import vigil

    captured = {}

    def fake_mttr(session, start, end, priority):
        captured.update(session=session, priority=priority)
        return {"average_mttr_seconds": None}

    with patch.object(case_metrics_queries, "mttr", fake_mttr), patch(
        "tools.mcp.vigil._service_session", _any_session
    ):
        out = _json(vigil.get_case_metrics(metric="mttr", priority="critical"))

    assert out == {"average_mttr_seconds": None}
    assert captured["priority"] == "critical"


def test_get_case_metrics_breached_reads_the_sla_service():
    from core.cases import case_sla_service
    from tools.mcp import vigil

    class FakeSLA:
        def get_breached_cases(self):
            return [{"case_id": "c-9"}]

    with patch.object(case_sla_service, "CaseSLAService", FakeSLA):
        out = _json(vigil.get_case_metrics(metric="breached"))

    assert out == {"breached_cases": [{"case_id": "c-9"}]}


def test_get_case_metrics_unknown_metric_names_the_valid_ones():
    from tools.mcp import vigil

    out = _json(vigil.get_case_metrics(metric="vibes"))

    assert "summary" in out["error"] and "mttr" in out["error"]


def test_get_case_metrics_bad_date_is_json_not_a_crash():
    from tools.mcp import vigil

    out = _json(vigil.get_case_metrics(metric="mttd", start_date="not-a-date"))

    assert "error" in out
