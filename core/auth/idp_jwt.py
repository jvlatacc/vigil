"""Verifying the identity provider's tokens on Vigil's own MCP surface.

A minted ``vgl_mcp_`` credential says an operator gave a program standing
access. A token from the deployment's identity provider says a person signed
in there, and Vigil's job is only to check the signature and find the account
an administrator mapped the token's subject to. The two are different claims,
so they are checked separately -- and both end in the same place: a user, or a
refusal that says nothing about which way the credential failed.

There is no trust attached to the issuer's opinions about roles. What a person
may do is what their Vigil roles permit, wherever they signed in.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import jwt
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.storage.models import User
from core.storage.unit_of_work import unit_of_work

logger = logging.getLogger(__name__)

# The one signing algorithm accepted. The issuer signs with RS256; anything
# else a token claims -- HS256 with a key from this key set, "none" -- is not
# a token this deployment issued, and the list is pinned so a future PyJWT
# default cannot widen it silently.
_ALGORITHMS = ["RS256"]

# The claims every token must carry: the four the check below is a check OF.
_REQUIRED_CLAIMS = ["exp", "iss", "aud", "sub"]

# One client per JWKS URL, built on first use and kept: PyJWT caches the key
# set on the client and refetches when a token presents a kid it has not
# seen. An issuer URL does not vary within a process, so neither does the
# client that answers for it.
_jwks_clients: Dict[str, jwt.PyJWKClient] = {}


def idp_jwt_active(settings: Optional[Settings] = None) -> bool:
    """Whether the surface accepts IdP-issued tokens at all.

    The three settings name the issuer, the audience tokens must carry, and
    the key set signatures are checked against: all three or nothing, because
    a verifier with any one missing cannot answer and must not pretend to.
    The tri-state ``VIGIL_MCP_OIDC_ENABLED`` is an operator's veto -- unset
    means "configured is on", so filling in the settings is the whole
    ceremony; an explicit false keeps the verifier off even when they are
    present, for an issuer outage, a migration, a rollback.
    """
    settings = settings if settings is not None else get_settings()
    if settings.vigil_mcp_oidc_enabled is False:
        return False
    return all(
        (
            settings.vigil_mcp_oidc_issuer,
            settings.vigil_mcp_oidc_audience,
            settings.vigil_mcp_oidc_jwks_url,
        )
    )


def verify_idp_token(token: str, settings: Optional[Settings] = None) -> Optional[str]:
    """The subject a token from the identity provider carries, or None.

    None covers every way this can fail -- unconfigured, unverifiable
    signature, wrong issuer, wrong audience, expired, a required claim
    missing -- because a caller holding a token that does not work learns
    nothing useful from which, and an attacker probing would learn plenty.
    The token itself is never logged.
    """
    settings = settings if settings is not None else get_settings()
    if not idp_jwt_active(settings):
        return None

    try:
        signing_key = _jwks_client(
            settings.vigil_mcp_oidc_jwks_url
        ).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            issuer=settings.vigil_mcp_oidc_issuer,
            audience=settings.vigil_mcp_oidc_audience,
            options={"require": _REQUIRED_CLAIMS},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        # A key set that cannot be fetched reads as a refusal, not a 500: the
        # verifier has not authenticated anybody, and the surface's one 401
        # answer is already what the caller should see.
        logger.warning("Refusing an IdP token on the MCP surface: %s", exc)
        return None
    return claims["sub"]


def _jwks_client(url: str) -> jwt.PyJWKClient:
    client = _jwks_clients.get(url)
    if client is None:
        client = jwt.PyJWKClient(url)
        _jwks_clients[url] = client
    return client


def idp_user(token: str, session: Optional[Session] = None) -> Optional[User]:
    """The user an IdP-issued token stands for, or None.

    The mapping is the account whose ``external_subject`` an administrator
    set to this token's subject. No account named, or an inactive one, is a
    refusal: identity provisioning is an administrator's act, and a token
    cannot create an account by naming a subject nothing holds.
    """
    subject = verify_idp_token(token)
    if subject is None:
        return None

    try:
        with unit_of_work(session) as session:
            user = session.query(User).filter(User.external_subject == subject).first()
            if user is None:
                logger.warning(
                    "An IdP token named a subject no Vigil account holds; "
                    "refusing it. Map the subject through the users API: %s",
                    subject,
                )
                return None
            if not user.is_active:
                logger.warning(
                    "An IdP token mapped to a deactivated account; refusing it: %s",
                    user.username,
                )
                return None
            return user
    except Exception:  # noqa: BLE001 - a database that cannot answer is not a yes
        # A store this cannot read has not authenticated anybody. Saying so is
        # a refusal, not an error: the caller is told it is not authenticated,
        # which is true, rather than being handed a 500 that says the surface
        # is broken and invites a retry.
        logger.exception("Could not check an IdP token's subject; refusing the caller")
        return None
