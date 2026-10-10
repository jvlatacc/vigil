"""The fast path's adjudication enqueue: an adjudicate run over one speculative row.

The shadow-adjudication mold — the same run kind, playbook, budgets and
enqueue mechanics — with one difference: the brief is the speculative-action
record itself, built from the row as the ledger holds it.

The ordering guarantee is structural, not hoped for. This runs in the
processor's fast-path hook, after the speculative row has committed, and
re-reads the row from the ledger before anything else: a row that is gone
or already resolved enqueues nothing, and the brief can only describe a
row the database actually holds.

The shadow-adjudication workflow's own switch is honoured: nothing starts
a workflow while it is off, and this run is that workflow.
"""

import logging
from typing import Any, Dict, Optional

from core.agents.projections import run_id_for
from core.agents.queue import build_start_job, enqueue_run
from core.response.approval_service import ActionStatus, ApprovalService, PendingAction
from core.response.fastpath.adjudication import (
    VERDICT_PENDING,
    adjudication_hypothesis,
    build_adjudication_brief,
)
from core.response.fastpath.config import FastPathConfig
from core.workflows.enablement import is_enabled
from core.workflows.routing import SHADOW_WORKFLOW_ID
from core.workflows.workflow_run_service import WorkflowRunService
from core.workflows.workflows_service import WorkflowsService
from services.daemon.config import OrchestratorConfig

logger = logging.getLogger(__name__)


def adjudication_run_id(action_id: str) -> str:
    """A run id derived from the action id, like every derived run id.

    Deterministic, so a daemon restart re-enters the same run id and the
    enqueue's own dedupe — not a new run beside the old one.
    """
    return run_id_for(f"{action_id}-adjudication")


def build_adjudication_request(
    row: PendingAction, config: FastPathConfig
) -> Dict[str, Any]:
    """The start-job request: the record as the brief, the verdict as the goal.

    Budgets are the orchestrator's own defaults — the same ceilings an
    investigation gets, env-tunable the same way — because this is a real
    model run with tools, not a stub; the TTL sweep bounds the verdict's
    authority regardless of how long the run takes.
    """
    budgets = OrchestratorConfig()
    prompt = build_adjudication_brief(row)
    hypothesis = adjudication_hypothesis(row)
    return {
        # The workflow resolves both layers, so no config path travels beside it.
        "playbook": f"workflow:{SHADOW_WORKFLOW_ID}",
        "config": "",
        "arch": "",
        "prompt": prompt,
        "hypotheses": [hypothesis],
        # Stated, not guessed: the claim names the restricted target.
        "hypothesis_subjects": {hypothesis: [row.target]} if row.target else {},
        # The record is the evidence; nothing to recall.
        "recall_keys": [],
        "overrides": {
            "budgets": {
                "max_calls": budgets.max_iterations_per_agent,
                "max_cost_usd": budgets.max_cost_per_investigation,
                "max_wall_ms": budgets.max_runtime_per_investigation * 1000,
            }
        },
    }


async def enqueue_speculative_adjudication(
    action: PendingAction,
    config: Optional[FastPathConfig] = None,
) -> Optional[str]:
    """Enqueue the adjudication of one committed speculative row.

    Returns the run id, or None when nothing was enqueued: the feature is
    off, the workflow is off, the row is gone or already resolved. A
    queue that refuses is logged and the run row finalized failed — the
    row itself waits for the TTL sweep, which is the fail-safe either way.
    """
    settings = config or FastPathConfig()
    if not settings.adjudication_enabled:
        return None
    if not is_enabled(SHADOW_WORKFLOW_ID):
        logger.debug(
            "no adjudication for %s: the %s workflow is off",
            action.action_id,
            SHADOW_WORKFLOW_ID,
        )
        return None

    # The brief is built only after the row exists: re-read the row from
    # the ledger, never trust the in-memory object. A row that vanished or
    # was resolved between the fast path's commit and this call has
    # nothing left to adjudicate.
    approvals = ApprovalService()
    committed = approvals.get_action(action.action_id)
    if committed is None:
        logger.warning("no speculative row %s to adjudicate", action.action_id)
        return None
    if committed.status != ActionStatus.SPECULATIVE.value:
        logger.info(
            "speculative row %s is already %s; nothing to adjudicate",
            committed.action_id,
            committed.status,
        )
        return None

    run_id = adjudication_run_id(committed.action_id)
    runs = WorkflowRunService()
    # A restart re-enters the same derived run id; one on record is not
    # started twice.
    if runs.get_run(run_id) is not None:
        logger.info("adjudication run %s already recorded; not re-enqueued", run_id)
        return run_id
    request = build_adjudication_request(committed, settings)
    recorded = runs.begin_run(
        run_id=run_id,
        workflow_id=SHADOW_WORKFLOW_ID,
        workflow_name=SHADOW_WORKFLOW_ID,
        workflow_source="agent",
        workflow_version=WorkflowsService().version_of(SHADOW_WORKFLOW_ID),
        trigger_context={
            "run_kind": "adjudicate",
            "speculative_action_id": committed.action_id,
            "speculative_target": committed.target,
            "verdict_status": VERDICT_PENDING,
        },
        triggered_by="fast-path",
    )
    if recorded is None:
        # No run row, no record: without it the verdict scan and the resume
        # path have nothing to key on. The TTL sweep stays the fail-safe.
        logger.warning("no workflow_runs row for adjudication run %s", run_id)
        return None

    job = build_start_job(run_id, "adjudicate", request, enqueued_by="fast-path")
    try:
        await enqueue_run(job, job_id=run_id)
    except Exception as exc:
        # Otherwise the row reads as running forever with no job behind it.
        if recorded is not None:
            runs.finalize_run(
                run_id, status="failed", error=f"Could not enqueue: {exc}"
            )
        raise
    logger.info(
        "enqueued adjudication of speculative action %s as run %s",
        committed.action_id,
        run_id,
    )
    return run_id
