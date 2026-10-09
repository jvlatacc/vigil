# Reading one agent run's status: the ledger read behind
# GET /api/v1/agent-runs/{run_id}, shared by the HTTP router and the MCP tool.
# Reports from state the worker persisted, using only the two permitted reads
# against agent_events; workflow_runs says whether the run was accepted at all.

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_status(session: Any, run_id: str) -> Optional[Dict[str, Any]]:
    """Status of one agent run, or None when there is no such run.

    Canonical form: workflow_runs.run_id is text, so the compare there is exact.
    """
    try:
        run_id = str(uuid.UUID(run_id))
    except ValueError:
        return None

    counted = session.execute(
        text(
            "SELECT count(*) AS events FROM agent_events WHERE run_id = CAST(:run_id AS uuid)"
        ),
        {"run_id": run_id},
    ).one_or_none()
    events = int(counted.events) if counted is not None else 0
    if events == 0:
        # Only the worker writes agent_events; POST wrote workflow_runs. A run with
        # that row and no events is accepted but not picked up yet, not unknown.
        if _has_run_row(session, run_id):
            return {"run_id": run_id, "status": "queued", "events": 0}
        return None

    terminal = session.execute(
        text(
            "SELECT payload FROM agent_events "
            "WHERE run_id = CAST(:run_id AS uuid) AND kind = 'terminal' ORDER BY seq LIMIT 1"
        ),
        {"run_id": run_id},
    ).one_or_none()
    if terminal is None:
        return {"run_id": run_id, "status": "running", "events": events}

    payload = terminal.payload
    return {
        "run_id": run_id,
        "status": "terminal",
        "events": events,
        "outcome": payload.get("outcome"),
        "reason": payload.get("reason"),
    }


def _has_run_row(session: Any, run_id: str) -> bool:
    row = session.execute(
        text("SELECT 1 FROM workflow_runs WHERE run_id = :run_id"),
        {"run_id": run_id},
    ).one_or_none()
    return row is not None
