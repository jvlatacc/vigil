"""The local provider: today's bcrypt directory behind the new seam.

This is the fallback mode, and its whole contract is to change nothing:
the same ``AuthService.authenticate_user`` call the ``/login`` route has
always made, wrapped so the federation mode and the local mode speak one
interface. A deployment that vetoes the broker keeps this path untouched.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.auth.auth_service import AuthService
from core.auth.federation.provider import (
    LOCAL,
    AuthenticatedIdentity,
    LocalCredentials,
)


class LocalAuthenticationProvider:
    """Verify credentials against Vigil's own ``users`` table.

    Lockouts and failed-attempt accounting stay inside
    ``authenticate_user`` — including the rule that a lockout is
    authoritative even over a correct password. This wrapper adds an
    identity shape and nothing else.
    """

    def authenticate(
        self, credentials: LocalCredentials, session: Optional[Session] = None
    ) -> Optional[AuthenticatedIdentity]:
        user = AuthService.authenticate_user(
            credentials.username_or_email, credentials.password, session
        )
        if user is None:
            return None
        return AuthenticatedIdentity(
            username=user.username,
            # No upstream issuer exists for a local account; the user id is
            # the stable identifier this deployment has always had.
            idp_subject=f"local:{user.user_id}",
            email=user.email,
            groups=(),
            provider=LOCAL,
        )
