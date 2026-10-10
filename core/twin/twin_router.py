"""Digital-twin console API.

A console surface, not a contract: the graph shape will churn as the twin
matures, so the router lives outside the frozen ``/api/v1`` tree (see
``core/api/v1/README.md``'s tie-breaker for unversioned surfaces).
``services/api/discovery.py`` mounts it from ``ROUTER_META`` — no edit to
``services/api/main.py``.
"""

from typing import Dict, List

from fastapi import APIRouter, Query
from sqlalchemy import select

from core.findings.exclusions import current_active_ips
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import Finding, case_findings
from core.storage.schemas.twin import TwinGraphSchema
from core.twin.graph import build_graph

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/twin",
    tags=["twin"],
    auth=Auth.REQUIRED,
)


@router.get("/graph", response_model=TwinGraphSchema)
def get_twin_graph(
    session: UnitOfWorkSession,
    apply_exclusions: bool = Query(
        True,
        description=(
            "Leave analyst-excluded IPs off the map. Findings left with no "
            "other entity move to Unattributed; the findings list's own "
            "exclusion view is untouched."
        ),
    ),
) -> TwinGraphSchema:
    """The network as findings see it: entities, relationships, pinned findings.

    Read like the findings list — same auth posture, no row cap, exclusions
    honoured by default.
    """
    rows = session.execute(
        select(
            Finding.finding_id,
            Finding.entity_context,
            Finding.severity,
        ).order_by(Finding.finding_id)
    ).all()
    findings = [
        {
            "finding_id": row.finding_id,
            "entity_context": row.entity_context,
            "severity": row.severity,
        }
        for row in rows
    ]
    excluded = current_active_ips() if apply_exclusions else frozenset()
    return build_graph(findings, _case_ids_by_finding(session), excluded)


def _case_ids_by_finding(session) -> Dict[str, List[str]]:
    """finding_id -> sorted case ids, from the case_findings M2M in one query."""
    rows = session.execute(
        select(case_findings.c.finding_id, case_findings.c.case_id)
    ).all()
    grouped: Dict[str, List[str]] = {}
    for finding_id, case_id in rows:
        grouped.setdefault(finding_id, []).append(case_id)
    return {finding_id: sorted(ids) for finding_id, ids in grouped.items()}
