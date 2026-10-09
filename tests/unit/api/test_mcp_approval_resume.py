"""A decision made over MCP frees a parked run the way the HTTP router does.

Spec D4 (headless Vigil): MCP approve/reject recorded the decision through the
same ApprovalService the /api/v1 approvals router uses, but only the router
asked the agent layer to pick the run back up -- an MCP-only operator waited
for the parked-run sweeper (60 s default) instead of the immediate resume the
REST path enjoys. Three contracts are pinned here:

- the resume hook is the one the router calls (core.workflows.run_resume
  .resume_run), invoked only when the decided action is bound to a workflow
  run, with the decider the surface bound -- never an argument;
- best-effort -- the decision stands whatever the wakeup does: a hook that
  fails or cannot reach the run queue still returns the decision, reported as
  ``run_resume: "skipped: <reason>"``;
- nothing decided (unknown action, no principal, no right) never reaches the
  hook.

The domain modules are patched, not the HTTP layer: the router keeps its own
request/response shapes, which the contract tests already pin.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _json(out):
    return json.loads(out)


# The registry's shape for a decided action: asdict(PendingAction). The fields
# the resume hand-off reads are the ones the tests assert on.
def _decided(**overrides):
    action = {
        "action_id": "a-1",
        "action_type": "quarantine_host",
        "title": "Isolate the host",
        "status": "approved",
        "approved_by": "nestor",
        "workflow_run_id": "r-1",
    }
    action.update(overrides)
    return action


# The shape core.workflows.run_resume.resume_run returns, including its two
# swallow-don't-raise failures (no ledger, queue unavailable).
def _resume(success=True, error=None):
    if success:
        return {
            "success": True,
            "status": "resuming",
            "run_id": "r-1",
            "job_id": "j-1",
        }
    return {"success": False, "run_id": "r-1", "error": error}


# --- The hand-off -------------------------------------------------------------


def test_approve_on_run_bound_action_invokes_the_resume_hook():
    from tools.mcp import vigil

    calls = []

    async def fake_resume(run_id, action_id, decided_by):
        calls.append((run_id, action_id, decided_by))
        return _resume()

    with patch(
        "core.agents.tool_registry.approve_action",
        lambda *, action_id: _decided(action_id=action_id),
    ), patch("core.workflows.run_resume.resume_run", fake_resume):
        out = _json(asyncio.run(vigil.approve_action("a-1")))

    assert calls == [("r-1", "a-1", "nestor")]
    assert out["run_resume"] == "enqueued"
    assert out["action_id"] == "a-1"
    assert out["status"] == "approved"


def test_reject_on_run_bound_action_invokes_the_resume_hook():
    from tools.mcp import vigil

    calls = []

    async def fake_resume(run_id, action_id, decided_by):
        calls.append((run_id, action_id, decided_by))
        return _resume()

    with patch(
        "core.agents.tool_registry.reject_action",
        lambda *, action_id, reason: _decided(
            action_id=action_id, status="rejected", approved_by="nestor"
        ),
    ), patch("core.workflows.run_resume.resume_run", fake_resume):
        out = _json(asyncio.run(vigil.reject_action("a-1", "out of scope")))

    assert calls == [("r-1", "a-1", "nestor")]
    assert out["run_resume"] == "enqueued"
    assert out["status"] == "rejected"


# --- Best-effort wakeup -------------------------------------------------------


def test_failing_resume_hook_still_returns_the_decision():
    from tools.mcp import vigil

    async def exploding_resume(run_id, action_id, decided_by):
        raise RuntimeError("redis down")

    with patch(
        "core.agents.tool_registry.approve_action",
        lambda *, action_id: _decided(action_id=action_id),
    ), patch("core.workflows.run_resume.resume_run", exploding_resume):
        out = _json(asyncio.run(vigil.approve_action("a-1")))

    # The decision is intact and is not an error; only the wakeup is reported.
    assert out["run_resume"] == "skipped: redis down"
    assert out["action_id"] == "a-1"
    assert out["status"] == "approved"
    assert "error" not in out


def test_hook_reporting_queue_unavailable_reports_skipped():
    from tools.mcp import vigil

    async def unqueued_resume(run_id, action_id, decided_by):
        return _resume(success=False, error="run queue unavailable")

    with patch(
        "core.agents.tool_registry.approve_action",
        lambda *, action_id: _decided(action_id=action_id),
    ), patch("core.workflows.run_resume.resume_run", unqueued_resume):
        out = _json(asyncio.run(vigil.approve_action("a-1")))

    assert out["run_resume"] == "skipped: run queue unavailable"
    assert out["status"] == "approved"
    assert "error" not in out


def test_action_not_bound_to_a_run_skips_without_the_hook():
    from tools.mcp import vigil

    hook_seen = []

    async def fake_resume(run_id, action_id, decided_by):
        hook_seen.append((run_id, action_id))
        return _resume()

    with patch(
        "core.agents.tool_registry.approve_action",
        lambda *, action_id: _decided(action_id=action_id, workflow_run_id=None),
    ), patch("core.workflows.run_resume.resume_run", fake_resume):
        out = _json(asyncio.run(vigil.approve_action("a-1")))

    assert not hook_seen
    assert out["run_resume"] == "skipped: action is not bound to a workflow run"
    assert out["status"] == "approved"


# --- Nothing decided, nothing resumed ------------------------------------------


def test_no_decision_never_reaches_the_hook():
    from tools.mcp import vigil

    hook_seen = []

    async def fake_resume(run_id, action_id, decided_by):
        hook_seen.append((run_id, action_id))
        return _resume()

    with patch(
        "core.agents.tool_registry.approve_action",
        lambda *, action_id: {
            "error": f"Action not found or cannot be approved: {action_id}"
        },
    ), patch("core.workflows.run_resume.resume_run", fake_resume):
        out = _json(asyncio.run(vigil.approve_action("a-1")))

    assert not hook_seen
    assert "error" in out
