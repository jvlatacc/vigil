"""The failure vocabulary of a federated sign-in.

Kept apart from the machinery that raises these so the pieces can import
each other without cycles — the state store, the provider, and the HTTP
surface all need the same family, and none of them needs the rest.

The distinction that matters to callers: ``OidcUnavailableError`` means a
dependency is down (the IdP, or Redis) and the sign-in fails closed with
a 502/503; every other member means the attempt itself is bad and fails
closed with a 401. Neither ever produces a session.
"""

from __future__ import annotations


class OidcError(Exception):
    """Base for everything that can go wrong in a federated sign-in."""


class OidcUnavailableError(OidcError):
    """The IdP could not be reached or spoke nonsense — retrying may help."""


class TokenExchangeError(OidcError):
    """The token endpoint refused the code. Logged, never echoed to the browser."""


class IdTokenRejected(OidcError):
    """The id_token failed verification — bad signature, audience, issuer,
    expiry or nonce. This is the fail-closed answer; no session results."""
