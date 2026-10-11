"""The OIDC broker provider: how a federated sign-in is verified.

Talks to a broker (Keycloak in the recommendation, anything OIDC-conformant
in principle) that fronts FreeIPA. Three exchanges, each fail-closed:

1. *begin* — fetch discovery (cached), mint state/nonce/PKCE verifier,
   build the authorize URL the browser is redirected to.
2. *exchange* — swap the authorization code for tokens at the token
   endpoint, carrying the PKCE verifier.
3. *verify* — check the id_token's signature against the issuer's JWKS
   (cached, refreshed on key rotation), then issuer, audience, expiry and
   nonce. Anything unexpected raises :class:`IdTokenRejected` and no
   session is minted.

The client secret is never fetched in here — callers resolve it through
``get_secret`` and hand it to the constructor, keeping credentials inside
the one credential-read channel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

import httpx
import jwt

from core.auth.federation.errors import (
    IdTokenRejected,
    OidcUnavailableError,
    TokenExchangeError,
)
from core.auth.federation.provider import OIDC, AuthenticatedIdentity
from core.auth.federation.state_store import PendingLogin

logger = logging.getLogger(__name__)

#: Signing algorithms an id_token may carry. The allowlist exists so an
#: attacker cannot pick the weakest algorithm the library happens to
#: support; Keycloak's default (RS256) heads the list.
ALLOWED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})

#: What an id_token must claim, beyond what PyJWT verifies structurally.
REQUIRED_CLAIMS = ("exp", "iat", "iss", "sub", "aud")


@dataclass(frozen=True)
class DiscoveredEndpoints:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class OidcProvider:
    """Verify sign-ins against an OIDC broker fronting the directory."""

    def __init__(
        self,
        *,
        issuer_url: str,
        client_id: str,
        scopes: Tuple[str, ...] = ("openid", "profile", "email"),
        groups_claim: str = "groups",
        client_secret: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        leeway_seconds: int = 30,
        cache_ttl_seconds: int = 300,
    ):
        # Trailing-slash tolerance here, once: issuers are compared exact
        # after this normalization, on both the discovery document and the
        # token's iss claim.
        self._issuer = issuer_url.rstrip("/")
        self._client_id = client_id
        self._scopes = tuple(scopes)
        self._groups_claim = groups_claim
        self._client_secret = client_secret
        self._leeway = leeway_seconds
        self._cache_ttl = cache_ttl_seconds
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=10.0)
        self._discovery: Optional[Tuple[float, DiscoveredEndpoints]] = None
        self._jwks: dict[str, Tuple[jwt.PyJWK, float]] = {}
        self._jwks_fetched_at = 0.0

    # -- begin ----------------------------------------------------------

    async def begin(self, redirect_uri: str) -> Tuple[PendingLogin, str]:
        """Mint one attempt's secrets and the authorize URL to redirect to.

        The caller persists the :class:`PendingLogin` before sending the
        browser anywhere; the URL is worthless without the stored state,
        which is exactly the way round.
        """
        endpoints = await self.discovery()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        # token_urlsafe's alphabet is unreserved per RFC 7636, and 86
        # characters sits inside the 43-128 verifier window.
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        url = str(
            httpx.Request(
                "GET",
                endpoints.authorization_endpoint,
                params={
                    "response_type": "code",
                    "client_id": self._client_id,
                    "redirect_uri": redirect_uri,
                    "scope": " ".join(self._scopes),
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                },
            ).url
        )
        return (
            PendingLogin(
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            ),
            url,
        )

    # -- exchange -------------------------------------------------------

    async def exchange(self, code: str, pending: PendingLogin) -> Mapping[str, Any]:
        """Swap the authorization code for tokens, PKCE verifier attached.

        On refusal the status is logged and raised — never the body,
        which may echo token material.
        """
        endpoints = await self.discovery()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending.redirect_uri,
            "client_id": self._client_id,
            "code_verifier": pending.code_verifier,
        }
        if self._client_secret:
            form["client_secret"] = self._client_secret
        try:
            response = await self._http.post(endpoints.token_endpoint, data=form)
        except httpx.HTTPError as exc:
            raise OidcUnavailableError(f"token endpoint unreachable: {exc}") from exc
        if response.status_code != 200:
            logger.error(
                "OIDC token endpoint refused the exchange (HTTP %d)",
                response.status_code,
            )
            raise TokenExchangeError(
                f"token endpoint returned HTTP {response.status_code}"
            )
        try:
            tokens = response.json()
        except ValueError as exc:
            raise OidcUnavailableError("token endpoint sent a non-JSON body") from exc
        if not tokens.get("id_token"):
            raise TokenExchangeError("token response carried no id_token")
        return tokens

    # -- verification ---------------------------------------------------

    async def verify_id_token(self, id_token: str, nonce: str) -> Mapping[str, Any]:
        """Verify the id_token end to end and return its claims.

        Signature (via cached JWKS), issuer, audience, expiry and nonce
        must all hold, or :class:`IdTokenRejected` — there is no partial
        credit in identity.
        """
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise IdTokenRejected(f"unreadable token header: {exc}") from exc

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise IdTokenRejected(f"signing algorithm {algorithm!r} is not allowed")
        kid = header.get("kid")
        if not kid:
            raise IdTokenRejected("token names no signing key")

        key = await self._signing_key(kid)
        try:
            claims = jwt.decode(
                id_token,
                key=key.key,
                algorithms=[algorithm],
                audience=self._client_id,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as exc:
            raise IdTokenRejected(str(exc)) from exc

        # OIDC: several audiences make azp mandatory, and it must be us.
        aud = claims.get("aud")
        if (
            isinstance(aud, list)
            and len(aud) > 1
            and claims.get("azp") != self._client_id
        ):
            raise IdTokenRejected("authorized party is not this client")

        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise IdTokenRejected("nonce did not match the sign-in attempt")

        return claims

    def groups_from(self, claims: Mapping[str, Any]) -> tuple[str, ...]:
        """The directory groups named by the configured claim path.

        A dot path (``groups``, or ``resource_access.vigil.roles`` for a
        Keycloak client-role layout) resolves through nested objects; a
        missing claim resolves to no groups, which downstream means
        deny-by-default.
        """
        value: Any = claims
        for part in self._groups_claim.split("."):
            if not isinstance(value, Mapping):
                return ()
            value = value.get(part)
            if value is None:
                return ()
        if isinstance(value, str):
            return (value,) if value else ()
        if isinstance(value, (list, tuple)):
            return tuple(str(group) for group in value if group)
        return ()

    def identity_from(self, claims: Mapping[str, Any]) -> AuthenticatedIdentity:
        """The identity a verified set of claims describes."""
        return AuthenticatedIdentity(
            username=str(claims.get("preferred_username") or ""),
            idp_subject=str(claims["sub"]),
            email=claims.get("email") or None,
            groups=self.groups_from(claims),
            provider=OIDC,
        )

    # -- plumbing -------------------------------------------------------

    async def discovery(self) -> DiscoveredEndpoints:
        """The IdP's endpoints, fetched once and cached for a while."""
        if self._discovery and time.monotonic() - self._discovery[0] < self._cache_ttl:
            return self._discovery[1]

        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise OidcUnavailableError(f"discovery unreachable: {exc}") from exc
        if response.status_code != 200:
            raise OidcUnavailableError(
                f"discovery returned HTTP {response.status_code}"
            )
        try:
            document = response.json()
        except ValueError as exc:
            raise OidcUnavailableError("discovery sent a non-JSON body") from exc

        # A discovery document for some other issuer is a misconfigured
        # issuer URL, and trusting its endpoints would send codes elsewhere.
        if str(document.get("issuer", "")).rstrip("/") != self._issuer:
            raise OidcUnavailableError(
                "discovery document is not for the configured issuer"
            )
        try:
            endpoints = DiscoveredEndpoints(
                authorization_endpoint=document["authorization_endpoint"],
                token_endpoint=document["token_endpoint"],
                jwks_uri=document["jwks_uri"],
            )
        except KeyError as exc:
            raise OidcUnavailableError(
                f"discovery document is missing {exc.args[0]!r}"
            ) from exc

        self._discovery = (time.monotonic(), endpoints)
        return endpoints

    async def _signing_key(self, kid: str) -> jwt.PyJWK:
        """The cached key named ``kid``, refetched on rotation or staleness."""
        now = time.monotonic()
        cached = self._jwks.get(kid)
        if cached:
            key, stored_at = cached
            if now - stored_at < self._cache_ttl:
                return key
        if self._jwks_fetched_at and now - self._jwks_fetched_at < self._cache_ttl:
            # The key set is fresh, so the token names a key the issuer
            # does not publish — reject rather than hammer the IdP.
            raise IdTokenRejected("no signing key matches the token's key id")
        await self._refresh_jwks()
        fresh = self._jwks.get(kid)
        if not fresh:
            raise IdTokenRejected("no signing key matches the token's key id")
        return fresh[0]

    async def _refresh_jwks(self) -> None:
        jwks_uri = (await self.discovery()).jwks_uri
        try:
            response = await self._http.get(jwks_uri)
        except httpx.HTTPError as exc:
            raise OidcUnavailableError(f"JWKS unreachable: {exc}") from exc
        if response.status_code != 200:
            raise OidcUnavailableError(f"JWKS returned HTTP {response.status_code}")
        try:
            document = response.json()
        except ValueError as exc:
            raise OidcUnavailableError("JWKS sent a non-JSON body") from exc

        now = time.monotonic()
        for jwk in document.get("keys", []):
            if not jwk.get("kid"):
                continue
            try:
                self._jwks[jwk["kid"]] = (jwt.PyJWK.from_dict(jwk), now)
            except jwt.PyJWKError:
                # A key type we cannot use (octet keys, certificates we
                # do not speak) is skipped, not fatal — the issuer may
                # publish several.
                logger.debug("Skipping unusable JWKS entry kid=%s", jwk["kid"])
        self._jwks_fetched_at = now

    async def aclose(self) -> None:
        """Release the HTTP client — only the one this provider created."""
        if self._owns_client:
            await self._http.aclose()
