# The frozen case-metric reads: by-priority, by-status, mttr, mttd and the
# summary reshape behind /api/v1/cases/metrics, plus the derived-timing SQL
# they (and the beta analyst rollup) share. They lived in the versioned router
# and moved here so the MCP tool wraps the same functions instead of a second
# copy of the queries -- one definition is why the surfaces cannot disagree.
# Breached cases are a CaseSLAService read and need no SQL here.

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Float, and_
from sqlalchemy import case as sql_case
from sqlalchemy import cast, func, literal_column, select, true
from sqlalchemy.sql.elements import ColumnElement

from core.cases.case_metrics_service import CaseMetricsService
from core.storage.models import Case, CaseClosureInfo

# --- Derived timings ---------------------------------------------------------
# MTTR, MTTD and per-analyst resolution time are computed in SQL from columns
# every case path writes, not read from ``case_metrics``: nothing populates that
# table in normal operation (#1435), so reading it reported 0 for every
# deployment. The definitions are the ones ``CaseMetricsService`` uses to fill
# ``case_metrics``, so the two agree wherever both exist.

_CLOSED_STATUSES = ("resolved", "closed")

# A first-activity timestamp is only cast when it looks like an ISO-8601 date
# and time and Postgres accepts it as a ``timestamp`` (``pg_input_is_valid``,
# PG16+, which every shipped Postgres is), so one malformed entry -- "Feb 30",
# trailing junk -- cannot fail the whole aggregate. Writers store naive UTC,
# some with a trailing "Z"; a cast to ``timestamp`` ignores the zone suffix,
# which is what lines them up with the naive ``created_at``.
_ISO_DATETIME = (
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])[T ]([01]\d|2[0-3]):[0-5]\d"
)


def _closed_at() -> ColumnElement:
    """When a resolved or closed case was closed.

    ``case_closure_info.closed_at`` is stamped by ``close_case``, which every
    close path goes through, and it does not move when the case is edited
    afterwards. A ``resolved`` case has no closure row (and a reopened one may
    keep a stale one), so those fall back to ``cases.updated_at`` -- the source
    ``CaseMetricsService`` uses for ``time_to_resolve``.
    """
    return sql_case(
        (
            Case.status == "closed",
            func.coalesce(CaseClosureInfo.closed_at, Case.updated_at),
        ),
        else_=Case.updated_at,
    )


def _first_activity_at() -> ColumnElement:
    """The earliest timestamp in ``cases.activities``, or NULL if none."""
    activities = sql_case(
        (func.jsonb_typeof(Case.activities) == "array", Case.activities),
        else_=literal_column("'[]'::jsonb"),
    )
    entry = func.jsonb_array_elements(activities).table_valued("value")
    stamp = entry.c.value.op("->>")("timestamp")
    return (
        select(func.min(cast(stamp, Case.created_at.type)))
        .select_from(entry)
        .where(
            stamp.op("~")(_ISO_DATETIME),
            func.pg_input_is_valid(stamp, "timestamp"),
        )
        .scalar_subquery()
    )


def _seconds_since_created(moment: ColumnElement) -> ColumnElement:
    return cast(func.extract("epoch", moment - Case.created_at), Float)


def _created_window(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> List[ColumnElement]:
    filters: List[ColumnElement] = [true()]
    if start_date:
        filters.append(Case.created_at >= start_date)
    if end_date:
        filters.append(Case.created_at <= end_date)
    return filters


def _mean(sums: Dict[Any, List[float]], key: Any) -> Optional[float]:
    total, count = sums.get(key, (0.0, 0))
    return total / count if count else None


def _add(sums: Dict[Any, List[float]], key: Any, total: Any, count: int) -> None:
    pair = sums.setdefault(key, [0.0, 0])
    pair[0] += total or 0.0
    pair[1] += count


def mttr(
    session: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Mean Time To Resolve, by priority and by day, for closed cases."""
    resolve = _seconds_since_created(_closed_at())
    respond = _seconds_since_created(_first_activity_at())
    day = func.to_char(Case.created_at, "YYYY-MM-DD")

    filters = _created_window(start_date, end_date)
    filters.append(Case.status.in_(_CLOSED_STATUSES))
    if priority:
        filters.append(Case.priority == priority)

    # One grouped query. The overall, per-priority and per-day means are folded
    # from its sums and counts, so the query count does not grow with cases.
    rows = (
        session.query(
            Case.priority,
            day,
            func.count(),
            func.sum(resolve),
            func.count(resolve),
            func.sum(respond),
            func.count(respond),
        )
        .outerjoin(CaseClosureInfo, CaseClosureInfo.case_id == Case.case_id)
        .filter(and_(*filters))
        .group_by(Case.priority, day)
        .all()
    )

    total_cases = 0
    overall: Dict[Any, List[float]] = {}
    by_priority: Dict[Any, List[float]] = {}
    by_day_mttr: Dict[Any, List[float]] = {}
    by_day_mttd: Dict[Any, List[float]] = {}
    for pri, date_key, count, r_sum, r_count, d_sum, d_count in rows:
        total_cases += count
        if not r_count:
            continue
        _add(overall, None, r_sum, r_count)
        _add(by_priority, pri, r_sum, r_count)
        _add(by_day_mttr, date_key, r_sum, r_count)
        _add(by_day_mttd, date_key, d_sum, d_count)

    trend_data = []
    for date_key in sorted(by_day_mttr):
        day_mttr = _mean(by_day_mttr, date_key)
        day_mttd = _mean(by_day_mttd, date_key)
        trend_data.append(
            {
                "date": date_key,
                "mttd": day_mttd / 3600 if day_mttd is not None else 0,
                "mttr": day_mttr / 3600 if day_mttr is not None else 0,
            }
        )

    # Null, not 0, when no case in the window has a measured value: the
    # response model allows it, and 0 reads as "resolved instantly".
    avg_mttr = _mean(overall, None)
    return {
        "average_mttr_seconds": avg_mttr,
        "average_mttr_hours": avg_mttr / 3600 if avg_mttr is not None else None,
        "mttr_by_priority": {
            pri: total / count / 3600 for pri, (total, count) in by_priority.items()
        },
        "trend_data": trend_data,
        "total_cases": total_cases,
    }


def mttd(
    session: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Mean Time To Detect, by priority: creation to first recorded activity."""
    respond = _seconds_since_created(_first_activity_at())

    filters = _created_window(start_date, end_date)
    if priority:
        filters.append(Case.priority == priority)

    rows = (
        session.query(
            Case.priority, func.count(), func.sum(respond), func.count(respond)
        )
        .filter(and_(*filters))
        .group_by(Case.priority)
        .all()
    )

    total_cases = 0
    overall: Dict[Any, List[float]] = {}
    by_priority: Dict[Any, List[float]] = {}
    for pri, count, d_sum, d_count in rows:
        total_cases += count
        if d_count:
            _add(overall, None, d_sum, d_count)
            _add(by_priority, pri, d_sum, d_count)

    avg_mttd = _mean(overall, None)
    return {
        "average_mttd_seconds": avg_mttd,
        "average_mttd_hours": avg_mttd / 3600 if avg_mttd is not None else None,
        "mttd_by_priority": {
            pri: total / count / 3600 for pri, (total, count) in by_priority.items()
        },
        "total_cases": total_cases,
    }


def by_priority(
    session: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Case counts by priority, closed counts alongside."""
    # One grouped query: count rows per priority in SQL rather than loading
    # every case (and its selectin findings) just to tally them.
    priority = func.coalesce(func.nullif(Case.priority, ""), "unknown")
    rows = (
        session.query(
            priority,
            func.count(),
            func.count(sql_case((Case.status.in_(_CLOSED_STATUSES), 1))),
        )
        .filter(and_(*_created_window(start_date, end_date)))
        .group_by(priority)
        .order_by(priority)
        .all()
    )

    # Sort by priority order
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    priority_breakdown = sorted(
        (
            {"priority": name, "count": count, "closed_count": closed}
            for name, count, closed in rows
        ),
        key=lambda x: priority_order.get(x["priority"], 99),
    )

    return {"priority_breakdown": priority_breakdown}


def by_status(
    session: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Case counts by status."""
    status = func.coalesce(func.nullif(Case.status, ""), "unknown")
    rows = (
        session.query(status, func.count())
        .filter(and_(*_created_window(start_date, end_date)))
        .group_by(status)
        .order_by(status)
        .all()
    )

    status_breakdown = [{"status": name, "count": count} for name, count in rows]

    return {"status_breakdown": status_breakdown}


def summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """The dashboard numbers, reshaped the way the summary endpoint reports them."""
    metrics = CaseMetricsService().get_dashboard_metrics(start_date, end_date)
    return {
        "total_cases": metrics.get("total_cases", 0),
        "open_cases": metrics.get("open_cases_count", 0),
        "resolved_cases": metrics.get("resolved_cases_count", 0),
        "critical_cases": metrics.get("priority_breakdown", {}).get("critical", 0),
        "status_breakdown": metrics.get("status_breakdown", {}),
        "priority_breakdown": metrics.get("priority_breakdown", {}),
    }
