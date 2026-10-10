# Starting an agent run: the orchestration behind POST /api/v1/agent-runs,
# shared by the HTTP router and the MCP tool so a run started either way is
# the same run, recorded the same way. "Runs" in 1.0 means agent runs (not
# workflow runs); see core/api/v1/README.md.

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.agents import run_limits
from core.agents.queue import (
    RUN_KINDS,
    build_start_job,
    enqueue_run,
    new_run_id,
)
from core.workflows.enablement import disabled_message, is_enabled

logger = logging.getLogger(__name__)

# The scheme the agent layer resolves against /internal/playbooks
# (services/agent/core/playbooks.ts::WORKFLOW_SCHEME).
WORKFLOW_SCHEME = "workflow:"


class UnknownRunKind(ValueError):
    """A run_kind outside RUN_KINDS."""


class WorkflowDisabled(RuntimeError):
    """The workflow the run names is turned off. Carries the operator-facing
    message ``disabled_message`` produced, so every surface answers the same
    words for the same switch."""


class RunQueueUnavailable(RuntimeError):
    """The queue that would carry the run refused it."""


# Mint a run id and enqueue it. The worker opens the ledger, not this call.
async def start_run(
    *,
    run_kind: str = "hunt",
    playbook: str,
    config: str,
    arch: str = "",
    prompt: str = "",
    overrides: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    enqueued_by: str,
) -> Dict[str, Any]:
    """Validate, record and enqueue one agent run.

    Raises ``UnknownRunKind`` for a kind outside ``RUN_KINDS``,
    ``WorkflowDisabled`` when the playbook names a workflow that is off,
    ``run_limits.OverrideRefused`` for overrides outside the limits, and
    ``RunQueueUnavailable`` when the queue refuses. Each surface maps those
    onto its own error shape; none of that mapping belongs here.
    """
    if run_kind not in RUN_KINDS:
        raise UnknownRunKind(f"unknown run_kind: {run_kind}")

    # A run that names a workflow is a start of that workflow.
    named = playbook.removeprefix(WORKFLOW_SCHEME).strip()
    if playbook.startswith(WORKFLOW_SCHEME) and not is_enabled(named):
        raise WorkflowDisabled(disabled_message(named))

    run_limits.check_overrides(overrides)

    run_id = new_run_id()
    payload: Dict[str, Any] = {
        "arch": arch,
        "playbook": playbook,
        "config": config,
        "prompt": prompt,
    }
    if overrides is not None:
        payload["overrides"] = overrides

    # Best-effort: without a workflow_runs row a parked run cannot raise an
    # answerable checkpoint. Like every write to that table, the ledger is truth.
    _begin_run_row(
        run_id,
        run_kind=run_kind,
        playbook=playbook,
        prompt=prompt,
        triggered_by=enqueued_by,
    )

    job = build_start_job(
        run_id=run_id,
        run_kind=run_kind,
        request=payload,
        enqueued_by=enqueued_by,
        tenant_id=tenant_id,
    )
    try:
        job_id = await enqueue_run(job)
    except Exception as exc:  # the queue is the only thing this can fail on
        logger.error("failed to enqueue agent run %s: %s", run_id, exc)
        raise RunQueueUnavailable("run queue unavailable") from exc

    return {"run_id": run_id, "job_id": job_id}


# The playbook reference names the workflow when there is one; a run started from
# file paths is named for the loop it runs, which is all the console needs to list it.
def _begin_run_row(
    run_id: str,
    *,
    run_kind: str,
    playbook: str,
    prompt: str,
    triggered_by: str,
) -> None:
    from core.workflows.workflow_run_service import WorkflowRunService
    from core.workflows.workflows_service import WorkflowsService

    named = playbook.removeprefix(WORKFLOW_SCHEME).strip()
    workflow_id = named if playbook.startswith(WORKFLOW_SCHEME) else run_kind
    # A bare run_kind names no definition, so it has no version to record.
    try:
        version = (
            WorkflowsService().version_of(workflow_id)
            if playbook.startswith(WORKFLOW_SCHEME)
            else None
        )
    except Exception as exc:  # noqa: BLE001 — the row is best-effort
        logger.warning("no workflow version for %s: %s", workflow_id, exc)
        version = None
    WorkflowRunService().begin_run(
        workflow_id=workflow_id,
        workflow_name=workflow_id,
        workflow_source="agent",
        workflow_version=version,
        trigger_context={"run_kind": run_kind, "prompt": prompt},
        triggered_by=triggered_by,
        run_id=run_id,
    )
