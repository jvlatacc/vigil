"""Repository for ``protected_assets`` — the never-quarantine invariant rows
(#944).

Operates on a caller-provided ``Session``; it never opens, commits or closes
one — the same contract as ``ip_exclusion_repository``. Validation and the
matching rules live in ``core.response.protected_assets``; this module is only
rows and queries.
"""

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.storage.models import ProtectedAsset


def list_rows(
    session: Session, *, include_removed: bool = False
) -> List[ProtectedAsset]:
    """Every row, newest first; active-only unless ``include_removed``."""
    query = select(ProtectedAsset).order_by(ProtectedAsset.created_at.desc())
    if not include_removed:
        query = query.where(ProtectedAsset.removed_at.is_(None))
    return list(session.execute(query).scalars().all())


def active_rows(session: Session) -> List[ProtectedAsset]:
    return list(
        session.execute(
            select(ProtectedAsset).where(ProtectedAsset.removed_at.is_(None))
        ).scalars()
    )


def active_row_for(
    session: Session, match_kind: str, match_value: str
) -> Optional[ProtectedAsset]:
    """The live row for ``(match_kind, match_value)``, if any.

    Case-insensitive on the value — the same comparison the active-row unique
    index makes — so a hostname declared twice in different cases conflicts
    instead of silently protecting twice.
    """
    return session.execute(
        select(ProtectedAsset)
        .where(ProtectedAsset.match_kind == match_kind)
        .where(func.lower(ProtectedAsset.match_value) == match_value.lower())
        .where(ProtectedAsset.removed_at.is_(None))
        .limit(1)
    ).scalar_one_or_none()


def row_by_id(session: Session, asset_id) -> Optional[ProtectedAsset]:
    return session.get(ProtectedAsset, asset_id)
