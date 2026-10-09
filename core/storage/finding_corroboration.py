"""Repository for corroboration reads behind the origin floor.

Answers one question for ``core.response.origin``: what do OTHER findings,
inside a bounded past, say about the same containment target? Operates on a
caller-provided ``Session`` (the protected_target_repository pattern) — the
response layer owns the fail-closed decision; storage only reports what it
saw. Storage may not import a capability domain, so the result shape lives
here and ``core.response.origin`` imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.storage.models import Finding
from core.storage.origin_trust import tier_rank


@dataclass(frozen=True)
class Corroboration:
    """What other findings say about the same containment target.

    ``best_other_rank`` is the strongest tier any other finding carried
    (``None`` when none of them stamped a known tier); ``distinct_sources``
    counts distinct ``data_source`` values. The motivating finding itself is
    excluded — a claim cannot corroborate itself.
    """

    distinct_sources: int
    best_other_rank: Optional[int]


def corroborating_sources(
    session: Session,
    probe: Dict[str, Any],
    window_start: datetime,
    exclude_finding_id: Optional[str] = None,
) -> Corroboration:
    """Distinct sources naming the probe's target within the window.

    The probe is a JSONB containment fragment (``{"src_ips": [ip]}`` or
    ``{"hostnames": [host]}``); the GIN index on ``entity_context`` backs it.
    """
    stmt = (
        select(Finding.data_source, Finding.origin_trust)
        .where(Finding.entity_context.contains(probe))
        .where(Finding.created_at >= window_start)
    )
    if exclude_finding_id:
        stmt = stmt.where(Finding.finding_id != exclude_finding_id)
    pairs = session.execute(stmt).all()

    sources = {data_source for data_source, _tier in pairs}
    ranks = [tier_rank(tier) for _data_source, tier in pairs]
    ranked = [rank for rank in ranks if rank is not None]
    return Corroboration(
        distinct_sources=len(sources),
        best_other_rank=max(ranked) if ranked else None,
    )
