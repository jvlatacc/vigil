"""Case metrics — versioned contract surface (``/api/v1/cases/metrics``).

Reporting numbers about cases (MTTR, MTTD, breach counts, breakdowns). Six are
frozen; six composite/rollup reads are marked beta via ``openapi_extra`` and are
excluded from the contract snapshot — their shape may change while the feature
matures. Beta still ships and returns data; it is a "do not rely on this yet"
label, not a hidden route.

Frozen: by-priority, by-status, breached, mttr, mttd, summary.
Beta:   dashboard, sla-compliance, velocity, analyst/{id}, analyst-performance,
        calculate/{id} (a recompute action, not a read).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy import case as sql_case
from sqlalchemy import func

from core.auth.permissions import permission_gate
from core.cases import case_metrics_queries
from core.cases.case_metrics_queries import (
    _CLOSED_STATUSES,
    _closed_at,
    _created_window,
    _seconds_since_created,
)
from core.cases.case_metrics_service import CaseMetricsService
from core.cases.case_sla_service import CaseSLAService
from core.routing import Auth, RouterMeta, UnitOfWorkSession
from core.storage.models import Case, CaseClosureInfo
from core.storage.schemas import CaseMetricsSchema

router = APIRouter()

ROUTER_META = RouterMeta(
    prefix="/api/v1/cases/metrics",
    tags=["case-metrics"],
    auth=Auth.REQUIRED,
    legacy_prefixes=("/api/cases/metrics",),
)

# Routes marked with this are in the versioned tree but NOT part of the frozen
# contract: composite rollups whose shape will change as reporting matures. The
# /api/v1/** contract snapshot excludes any operation carrying x-vigil-beta.
_BETA = {"openapi_extra": {"x-vigil-beta": True}}

# --- Derived timings ---------------------------------------------------------
# MTTR, MTTD and per-analyst resolution time are computed in SQL from columns
# every case path writes, not read from ``case_metrics``: nothing populates that
# table in normal operation (#1435), so reading it reported 0 for every
# deployment. The definitions -- and the four frozen reads that use them --
# live in core.cases.case_metrics_queries, shared with the MCP tool; the
# names imported above are the pieces the beta analyst rollup still needs.


# --- Frozen response models -------------------------------------------------
# These six reads are the frozen contract, so their response shapes are pinned
# by the snapshot. Inner value types are kept permissive where the underlying
# service returns open maps; the envelope keys are the promise.


class MttrResponse(BaseModel):
    average_mttr_seconds: Optional[float] = None
    average_mttr_hours: Optional[float] = None
    mttr_by_priority: Dict[str, Optional[float]] = Field(default_factory=dict)
    trend_data: List[Dict[str, Any]] = Field(default_factory=list)
    total_cases: int


class MttdResponse(BaseModel):
    average_mttd_seconds: Optional[float] = None
    average_mttd_hours: Optional[float] = None
    mttd_by_priority: Dict[str, Optional[float]] = Field(default_factory=dict)
    total_cases: int


class CaseMetricsSummaryResponse(BaseModel):
    total_cases: int
    open_cases: int
    resolved_cases: int
    critical_cases: int
    status_breakdown: Dict[str, int] = Field(default_factory=dict)
    priority_breakdown: Dict[str, int] = Field(default_factory=dict)


class BreachedCasesResponse(BaseModel):
    breached_cases: List[Dict[str, Any]] = Field(default_factory=list)


class PriorityBreakdownRow(BaseModel):
    priority: str
    count: int
    closed_count: int


class StatusBreakdownRow(BaseModel):
    status: str
    count: int


class ByPriorityResponse(BaseModel):
    priority_breakdown: List[PriorityBreakdownRow] = Field(default_factory=list)


class ByStatusResponse(BaseModel):
    status_breakdown: List[StatusBreakdownRow] = Field(default_factory=list)


metrics_service = CaseMetricsService()


@router.get("/dashboard", **_BETA)
def get_dashboard(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
):
    """
    Get dashboard metrics.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Dashboard metrics
    """
    metrics = metrics_service.get_dashboard_metrics(start_date, end_date)
    return metrics


@router.get("/sla-compliance", **_BETA)
def get_sla_compliance(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
):
    """
    Get SLA compliance report.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        SLA compliance statistics
    """
    sla_service = CaseSLAService()
    report = sla_service.get_sla_compliance_report(start_date, end_date)
    return report


@router.get("/analyst/{analyst_id}", **_BETA)
def get_analyst_performance(
    analyst_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Get analyst performance metrics.

    Args:
        analyst_id: Analyst user ID
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Analyst performance metrics
    """
    metrics = metrics_service.get_analyst_performance(analyst_id, start_date, end_date)
    return metrics


@router.get("/mttr", response_model=MttrResponse)
def get_mttr(
    session: UnitOfWorkSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    priority: Optional[str] = None,
):
    """
    Get Mean Time To Resolve metrics.

    Args:
        start_date: Start date filter
        end_date: End date filter
        priority: Filter by priority

    Returns:
        MTTR metrics by priority and trend data
    """
    return case_metrics_queries.mttr(session, start_date, end_date, priority)


@router.get("/velocity", **_BETA)
def get_velocity(days: int = 30):
    """
    Get case velocity (opened vs closed).

    Args:
        days: Number of days to analyze

    Returns:
        Velocity data
    """
    velocity = metrics_service.get_case_velocity(days)
    return velocity


@router.post(
    "/calculate/{case_id}", dependencies=[permission_gate("cases.write")], **_BETA
)
def calculate_case_metrics(case_id: str):
    """
    Calculate/update metrics for a case.

    Args:
        case_id: Case ID

    Returns:
        Calculated metrics
    """
    metrics = metrics_service.calculate_case_metrics(case_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseMetricsSchema.dump(metrics)


@router.get("/breached", response_model=BreachedCasesResponse)
def get_breached_cases():
    """
    Get all cases with SLA breaches.

    Returns:
        List of breached cases
    """
    sla_service = CaseSLAService()
    breached = sla_service.get_breached_cases()
    return {"breached_cases": breached}


@router.get("/summary", response_model=CaseMetricsSummaryResponse)
def get_summary(
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
):
    """
    Get summary metrics for cases.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Summary metrics including total cases, open cases, etc.
    """
    return case_metrics_queries.summary(start_date, end_date)


@router.get("/mttd", response_model=MttdResponse)
def get_mttd(
    session: UnitOfWorkSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    priority: Optional[str] = None,
):
    """
    Get Mean Time To Detect metrics.

    Args:
        start_date: Start date filter
        end_date: End date filter
        priority: Filter by priority

    Returns:
        MTTD metrics by priority
    """
    return case_metrics_queries.mttd(session, start_date, end_date, priority)


@router.get("/by-priority", response_model=ByPriorityResponse)
def get_by_priority(
    session: UnitOfWorkSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Get case counts by priority.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Case counts broken down by priority
    """
    return case_metrics_queries.by_priority(session, start_date, end_date)


@router.get("/by-status", response_model=ByStatusResponse)
def get_by_status(
    session: UnitOfWorkSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Get case counts by status.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Case counts broken down by status
    """
    return case_metrics_queries.by_status(session, start_date, end_date)


@router.get("/analyst-performance", **_BETA)
def get_all_analyst_performance(
    session: UnitOfWorkSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """
    Get performance metrics for all analysts.

    Args:
        start_date: Start date filter
        end_date: End date filter

    Returns:
        Performance metrics for all analysts
    """
    analyst = func.coalesce(func.nullif(Case.assignee, ""), "unassigned")
    is_closed = Case.status.in_(_CLOSED_STATUSES)
    resolve = sql_case((is_closed, _seconds_since_created(_closed_at())))

    rows = (
        session.query(
            analyst,
            func.count(),
            func.count(sql_case((is_closed, 1))),
            func.avg(resolve),
        )
        .outerjoin(CaseClosureInfo, CaseClosureInfo.case_id == Case.case_id)
        .filter(and_(*_created_window(start_date, end_date)))
        .group_by(analyst)
        .order_by(func.count().desc(), analyst)
        .all()
    )

    # avg_resolution_time stays 0 rather than null for an analyst with nothing
    # resolved: this beta route has no response model and the console types the
    # field as a number.
    analyst_performance = [
        {
            "analyst_id": name,
            "analyst_name": name,
            "cases_assigned": assigned,
            "cases_resolved": resolved,
            "avg_resolution_time": avg / 3600 if avg is not None else 0,
        }
        for name, assigned, resolved, avg in rows
    ]

    return {"analyst_performance": analyst_performance}
