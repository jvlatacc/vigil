"""Repository for the ``protected_targets`` never-quarantine store.

Operates on a caller-provided ``Session``; it never opens, commits or closes
one (the ip_exclusion_repository pattern). The rules about *when* a protected
target holds containment live in ``core.response.protected_targets``; storage
may not import a capability domain, so conversion to the response-layer
dataclass happens there too.
"""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.storage.models import ProtectedTarget
from core.time import utcnow


def active_rows(session: Session) -> List[ProtectedTarget]:
    """Every active row, newest first."""
    return list(
        session.execute(
            select(ProtectedTarget).order_by(
                ProtectedTarget.created_at.desc(), ProtectedTarget.target_id
            )
        )
        .scalars()
        .all()
    )


def active_row_for(
    session: Session, kind: str, value: str
) -> Optional[ProtectedTarget]:
    """The active row for ``(kind, value)``, or None."""
    return session.execute(
        select(ProtectedTarget).where(
            ProtectedTarget.kind == kind,
            ProtectedTarget.value == value,
            ProtectedTarget.removed_at.is_(None),
        )
    ).scalar_one_or_none()


def add_row(
    session: Session,
    *,
    kind: str,
    value: str,
    reason: str,
    created_by: str,
    origin: str = "operator",
) -> ProtectedTarget:
    """One active entry. Callers check active_row_for first: a duplicate
    raises the partial unique index."""
    row = ProtectedTarget(
        target_id=f"ptgt-{uuid.uuid4().hex[:16]}",
        kind=kind,
        value=value,
        reason=reason,
        origin=origin,
        created_by=created_by,
        created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def record_removal(
    session: Session,
    row: ProtectedTarget,
    *,
    removed_by: str,
    reason: Optional[str] = None,
) -> ProtectedTarget:
    """Record, not delete: the row keeps its history (ip_exclusions pattern)."""
    row.removed_at = utcnow()
    row.removed_by = removed_by
    row.removal_reason = reason
    session.flush()
    return row
