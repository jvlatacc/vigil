"""JIT linking: bind a verified upstream identity to a ``users`` row.

The IdP vouches for a person; Vigil still needs a local row to attach a
role and a session to. Linking is by email first, then by username — and
a username that belongs to an account with a different email is refused,
not merged: at the IdP anyone can claim any username, so a collision is
an account-takeover attempt until proven otherwise.

The role is the directory's call, made fresh at every federated login:
the intersection of the identity's groups with the ``role_group_mappings``
rows (highest priority wins). No match means the unmapped role — a
session that can see the console and do nothing, per the deny-by-default
decision the plan locks in.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from core.auth.auth_service import AuthService
from core.auth.federation.provider import AuthenticatedIdentity
from core.auth.group_mapping import UNMAPPED_ROLE_ID, resolve_role_for_groups
from core.storage.models import User
from core.storage.unit_of_work import unit_of_work

logger = logging.getLogger(__name__)


class UnlinkableIdentityError(Exception):
    """The verified identity cannot be bound safely; no session results."""


def link_federated_user(
    identity: AuthenticatedIdentity, session: Optional[Session] = None
) -> User:
    """The ``users`` row for this verified identity, linked or created.

    Raises ``UnlinkableIdentityError`` when binding would mean merging two
    different people, the account is disabled, or a brand-new identity
    arrives with no email to file it under.
    """
    with unit_of_work(session) as s:
        role = resolve_role_for_groups(identity.groups, s)
        role_id = role.role_id if role else UNMAPPED_ROLE_ID

        user = None
        if identity.email:
            user = s.query(User).filter(User.email == identity.email).first()
        if user is None:
            candidate = s.query(User).filter(User.username == identity.username).first()
            if candidate is not None and _emails_conflict(candidate, identity):
                logger.error(
                    "Federated sign-in refused: IdP username %r collides with a "
                    "different local account",
                    identity.username,
                )
                raise UnlinkableIdentityError(
                    "username is claimed by an account with a different email"
                )
            user = candidate

        if user is None:
            user = _create_federated_user(s, identity, role_id)
            logger.info(
                "Federated sign-in provisioned user %s (role %s, provider %s)",
                user.username,
                role_id,
                identity.provider,
            )
            return user

        if not user.is_active:
            logger.warning(
                "Federated sign-in refused: account %s is disabled", user.username
            )
            raise UnlinkableIdentityError("account is disabled")

        # The directory decides at federated login — including deciding
        # "nothing". A locally-granted role does not survive an IdP whose
        # groups no longer vouch for it.
        if user.role_id != role_id:
            logger.info(
                "Federated sign-in moves %s from role %s to %s (directory groups)",
                user.username,
                user.role_id,
                role_id,
            )
            user.role_id = role_id

        s.flush()
        return user


def _emails_conflict(user: User, identity: AuthenticatedIdentity) -> bool:
    """Whether the IdP's email and the account's disagree about who this is.

    An absent claim on either side cannot conflict — a deployment whose
    IdP omits email still links by exact username, which is the case the
    fallback mode depends on.
    """
    if not identity.email or not user.email:
        return False
    return identity.email.strip().lower() != user.email.strip().lower()


def _create_federated_user(
    s: Session, identity: AuthenticatedIdentity, role_id: str
) -> User:
    """Provision the row a first-time federated identity needs.

    The password hash is bcrypt of a secret that is discarded the moment
    it is hashed: the column is NOT NULL and the local path must never
    authenticate this row, so the hash must be real and unguessable at
    once.
    """
    if not identity.email:
        raise UnlinkableIdentityError(
            "identity carries no email and matches no existing account"
        )
    user = User(
        user_id=f"user-{uuid.uuid4().hex[:12]}",
        username=identity.username,
        email=identity.email,
        password_hash=AuthService.hash_password(secrets.token_urlsafe(32)),
        full_name=identity.username,
        role_id=role_id,
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        login_count=0,
    )
    s.add(user)
    s.flush()
    return user
