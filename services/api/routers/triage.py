"""Read-only Triage queue. Nothing on this router writes."""

from typing import Optional

from fastapi import APIRouter, Query

from core.auth.permissions import permission_gate
from core.routing import Auth, RouterMeta
from services.api.triage_read import triage_payload

# The Triage queue is intake rows over findings, so it asks findings.read —
# the same right the findings surface itself asks for. Nothing here writes.
router = APIRouter(dependencies=[permission_gate("findings.read")])

ROUTER_META = RouterMeta(
    prefix="/api",
    tags=["triage"],
    auth=Auth.REQUIRED,
)


@router.get("/triage")
async def get_triage(
    kind: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """Intake rows, ranking inputs, and the strip. Polled.

    Reads the tables directly. ``_get_orchestrator()`` is a second process
    whose queue is never this one.
    """
    return triage_payload(kind=kind or None, source=source or None, state=state or None)
