"""Federated sign-in for Vigil: the upstream IdP as the front door.

The seam is small on purpose. A provider verifies credentials somewhere
else — the local bcrypt directory, or an OIDC broker fronting FreeIPA —
and hands back one shape, :class:`AuthenticatedIdentity`. Everything
downstream of "who signed in" (linking to a ``users`` row, resolving the
role from directory groups, minting the session JWT) consumes that shape
and never learns which provider produced it.

Modules:

- ``provider``   — the identity shape and the protocol.
- ``local``      — today's local login behind that interface (fallback mode).
- ``oidc``       — the OIDC broker provider: discovery, PKCE, id_token
  verification against cached JWKS.
- ``state_store``— the one-time, short-lived state of an authorization-code
  dance (state, nonce, PKCE verifier) — single-use, fail-closed.
- ``config``     — env + SystemConfig wiring; disabled until configured.
- ``linking``    — binds a verified identity to a ``users`` row and assigns
  the role its directory groups map onto (deny-by-default).
"""

from core.auth.federation.errors import (
    IdTokenRejected,
    OidcError,
    OidcUnavailableError,
    TokenExchangeError,
)
from core.auth.federation.local import LocalAuthenticationProvider
from core.auth.federation.oidc import OidcProvider
from core.auth.federation.provider import (
    LOCAL,
    OIDC,
    AuthenticatedIdentity,
    AuthenticationProvider,
    LocalCredentials,
)

__all__ = [
    "LOCAL",
    "OIDC",
    "AuthenticatedIdentity",
    "AuthenticationProvider",
    "IdTokenRejected",
    "LocalAuthenticationProvider",
    "LocalCredentials",
    "OidcError",
    "OidcProvider",
    "OidcUnavailableError",
    "TokenExchangeError",
]
