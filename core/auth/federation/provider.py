"""The identity shape every sign-in produces, and the provider protocol.

A provider verifies credentials somewhere else — the local bcrypt
directory, or an OIDC broker fronting FreeIPA — and hands back one shape.
Everything downstream (linking, role assignment, session minting)
consumes that shape and never learns which provider produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

#: The ``provider`` field's values. Module constants rather than a bare
#: string so a typo is a NameError, not a third, unknown provider.
LOCAL = "local"
OIDC = "oidc"


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """A sign-in the platform believes, because it just verified it.

    ``username`` names the ``users`` row this identity binds to; the OIDC
    path resolves it through JIT linking before the identity reaches
    anyone. ``idp_subject`` is the issuer's stable ``sub`` claim — the one
    identifier that survives a rename — or, for a local sign-in, a
    ``local:`` prefixed user id, since no upstream issuer exists.
    ``groups`` are the raw directory groups; what they authorize is
    ``core.auth.group_mapping``'s decision, made later.
    """

    username: str
    idp_subject: str
    email: Optional[str]
    groups: tuple[str, ...]
    provider: str


@dataclass(frozen=True)
class LocalCredentials:
    """What the local provider verifies: a username-or-email and a password."""

    username_or_email: str
    password: str


class AuthenticationProvider(Protocol):
    """The fallback-mode interface: verify credentials, name the person.

    The OIDC flow does not fit this signature — its verification is a
    redirect dance, not one call — so :class:`OidcProvider` does not
    implement it. The protocol types the local (and future direct-LDAPS)
    mode: the shape a sign-in must produce, whichever directory vouched.
    """

    def authenticate(
        self, credentials: LocalCredentials
    ) -> Optional[AuthenticatedIdentity]:
        """The identity for these credentials, or None to refuse them.

        Raising ``AccountLockedError`` is how a lockout surfaces; None
        means the credentials are simply wrong.
        """
        ...
