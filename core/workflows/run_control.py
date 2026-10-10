# Steering a workflow run that is parked or going: the preconditions and the
# hand-off behind POST /api/workflows/runs/{run_id}/{cancel,resume}, shared by
# the console router and the MCP tools so a run steered either way walks the
# same gates. What a decision does to a paused run lives in run_resume; how a
# stop is asked for lives in run_cancel; this composes them and owns the
# "is there actually something to steer" checks.

from __future__ import annotations

from typing import Any, Dict


class RunNotFound(RuntimeError):
    """No workflow run carries this id."""


class RunNotPaused(RuntimeError):
    """The run is not waiting on a person, so there is nothing to resume."""


class NoPendingApproval(RuntimeError):
    """The run is parked with no approval action left to decide."""


class AmbiguousPendingApprovals(RuntimeError):
    """More than one pending approval waits on this run; resume names no
    action, so with several pending it would pick one unseen."""


def _services(run_service=None, approval_service=None):
    """Bare-construct what the caller did not supply.

    The API passes its app.state instances so tests can override them; a
    caller without a request object (the MCP tool) takes fresh ones, which
    are stateless over the database.
    """
    if run_service is None:
        from core.workflows.workflow_run_service import WorkflowRunService

        run_service = WorkflowRunService()
    if approval_service is None:
        from core.response.approval_service import ApprovalService

        approval_service = ApprovalService()
    return run_service, approval_service


# Resume a paused run: approve its one pending approval and re-enter the phase
# loop. Human control is untouched -- the decision here is the caller's own
# acting on a row that waited on a person; only the mechanical wakeup lives here.
async def resume_paused_run(
    run_id: str,
    decided_by: str,
    run_service=None,
    approval_service=None,
) -> Dict[str, Any]:
    """Approve the run's single pending approval and ask the agent layer to
    pick the run back up.

    Raises ``RunNotFound``, ``RunNotPaused``, ``NoPendingApproval`` and
    ``AmbiguousPendingApprovals``; every surface maps those onto its own
    error shape.
    """
    from core.response.approval_service import ActionStatus
    from core.workflows.run_resume import resume_run

    run_service, approval_service = _services(run_service, approval_service)

    run = run_service.get_run(run_id)
    if not run:
        raise RunNotFound(f"Run not found: {run_id}")
    if run.get("status") != "paused":
        raise RunNotPaused(f"Run {run_id} is not paused (status={run.get('status')})")

    pending = approval_service.list_actions(
        status=ActionStatus.PENDING, workflow_run_id=run_id
    )
    if not pending:
        raise NoPendingApproval(f"Run {run_id} has no pending approval")
    if len(pending) > 1:
        raise AmbiguousPendingApprovals(
            f"Run {run_id} has {len(pending)} pending approvals; "
            "decide each through /approvals/{action_id}"
        )

    approval_service.approve_action(pending[0].action_id, approved_by=decided_by)
    return await resume_run(run_id, pending[0].action_id, decided_by)


async def cancel_run(
    run_id: str,
    reason: str,
    actor: str,
    run_service=None,
    approval_service=None,
) -> Dict[str, Any]:
    """Reject any pending approval on the run and finalise it ``cancelled``.

    Raises ``RunNotFound`` when no run carries the id; every surface maps
    that onto its own error shape.
    """
    from core.response.approval_service import ActionStatus
    from core.workflows.run_cancel import stop_run
    from core.workflows.run_resume import resume_run

    run_service, approval_service = _services(run_service, approval_service)

    run = run_service.get_run(run_id)
    if not run:
        raise RunNotFound(f"Run not found: {run_id}")

    pending = approval_service.list_actions(
        status=ActionStatus.PENDING, workflow_run_id=run_id
    )
    for action in pending:
        approval_service.reject_action(
            action.action_id, reason=reason, rejected_by=actor
        )

    # A rejection ends the run, but the agent layer is what ends it: this hands
    # the decision over and that side journals it and stops.
    if run.get("status") == "paused" and pending:
        return await resume_run(run_id, pending[0].action_id, actor)

    # Ask the run to stop, then make sure it does: the abort lets a hunt settle itself
    # and write a report, and the escalation behind it covers a worker that cannot.
    stopped = stop_run(run_id, reason, actor)

    run_service.finalize_run(
        run_id,
        status="cancelled",
        error=f"Cancelled: {reason}",
    )
    return {
        "success": True,
        "status": "cancelled",
        "run_id": run_id,
        "rejection_reason": reason,
        **stopped,
    }
