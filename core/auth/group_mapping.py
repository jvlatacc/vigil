"""Directory-group → role resolution for federated logins.

The upstream IdP speaks in directory groups; Vigil authorizes in roles. The
``role_group_mappings`` rows — written only through the admin router — are the
association between the two. Resolution is deny-by-default: groups that match
no mapping resolve to no role, and the caller signs the user in with the
unmapped role (``UNMAPPED_ROLE_ID``), whose permission map grants nothing.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from core.storage.models import Role, RoleGroupMapping
from core.storage.unit_of_work import unit_of_work

#: The system role a signed-in-but-unmapped user holds. An empty permission
#: map: every check reads ``permissions.get(key, False)``, so it grants
#: nothing — including permission keys that did not exist when the role was
#: seeded.
UNMAPPED_ROLE_ID = "role-unmapped"


def resolve_role_for_groups(
    groups: Iterable[str], session: Optional[Session] = None
) -> Optional[Role]:
    """The role the directory ``groups`` map onto, highest priority wins.

    The intersection of the user's groups with the mapping rows decides; a
    tie on priority resolves to the earliest-created row so resolution is
    deterministic. No match ⇒ ``None`` — the caller assigns the unmapped
    role rather than inventing a default.
    """
    named = [group for group in groups if group]
    if not named:
        return None

    with unit_of_work(session) as s:
        mapping = (
            s.query(RoleGroupMapping)
            .filter(RoleGroupMapping.idp_group.in_(named))
            .order_by(RoleGroupMapping.priority.desc(), RoleGroupMapping.id.asc())
            .first()
        )
        if mapping is None:
            return None
        # ON DELETE CASCADE keeps every mapping pointed at a live role, so a
        # missing role row here is a race, not a state; reading it as "no
        # role" degrades to deny-by-default, which is the safe direction.
        return s.query(Role).filter(Role.role_id == mapping.role_id).first()
