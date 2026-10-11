"""Per-user OAuth for HTTP-capable MCP connectors.

The MCP authorization model (spec 2025-06-18) makes an HTTP-transport MCP
server an OAuth 2.1 resource server: it publishes Protected Resource Metadata
(RFC 9728), points at its authorization server (RFC 8414), and refuses every
request whose Bearer token is not audience-bound to it (RFC 8707 ``resource``
indicators). Identity on the wire is the validated token — no Vigil-invented
header exists in the protocol.

What this module owns:

* discovery of the resource server's metadata and, through it, the
  authorization server's metadata — each fail-closed, issuer-checked;
* one authorization-code + PKCE flow per (user, server), with the ``resource``
  parameter carried in **both** the authorization and the token request, so
  every token Vigil receives is bound to the one server it may be sent to;
* a per-(user, resource) token cache with expiry, and the refresh grant for
  the 401 + ``WWW-Authenticate`` case;
* the passthrough guard: a token minted for one resource is refused, in code,
  when asked to authenticate another. Token passthrough is prohibited by the
  MCP spec; here that is an exception type, not a convention.

What this module deliberately does not own:

* the browser leg of the authorization-code flow. A headless backend cannot
  pop a browser: ``begin_authorization`` builds the URL the user completes in
  their browser (the console flow), and ``complete_authorization`` finishes
  the exchange when the code comes back. Until a user completes that flow for
  a connector, dispatch to it raises :class:`AuthorizationRequired` — the
  same dormancy-by-design the credential gate gives stdio servers.
* persistence of access tokens. They live in an in-memory :class:`TokenStore`
  owned by the process client; nothing tokens-at-rest survives a restart.
  Only the short-lived PKCE pending state rides Redis, single-use and
  TTL-bounded, exactly like the federated sign-in state.

stdio connectors are a different world: their sessions are persistent per
server, per-call identity cannot cross the pipe, and their accountability
surface is Vigil's own audit row plus the OTEL trace id. This module is never
consulted for them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple
from urllib.parse import urlsplit

import httpx
import jwt

from core.redis_client import get_async_redis

logger = logging.getLogger(__name__)

#: How long an attempted connector authorization may sit between the redirect
#: out and the callback back. Same bound as the federated sign-in state: a
#: slow human fits, a replayed one does not.
STATE_TTL_SECONDS = 600

#: How long a discovery document answers from cache before it is re-fetched.
#: Key rotation at the authorization server is picked up on this clock.
DISCOVERY_TTL_SECONDS = 300

#: Subtracted from ``expires_in`` so a token is never used in its final
#: seconds, when clock skew between Vigil and the issuer could leak one
#: already-expired request past the cache.
_TOKEN_EXPIRY_MARGIN_S = 30

_WELL_KNOWN_PRM = "/.well-known/oauth-protected-resource"
_WELL_KNOWN_AS = "/.well-known/oauth-authorization-server"


class IdentityError(Exception):
    """Base for the downstream-identity failures dispatch turns into errors."""


class DiscoveryFailed(IdentityError):
    """The resource or authorization server metadata could not be trusted."""


class AuthorizationRequired(IdentityError):
    """No usable token for this (user, server).

    A fresh user grant is the only way forward: either the connector was
    never authorized, or the cached token was refused and no refresh token
    could renew it. Dispatch turns this into a fail-closed error result.
    """


class TokenExchangeFailed(IdentityError):
    """The token endpoint refused an exchange, or answered something unusable."""


class TokenPassthroughRefused(IdentityError):
    """A token was offered to a server it was not minted for.

    The MCP spec prohibits token passthrough; this is the code-level guard.
    """


def canonical_resource(url: str) -> str:
    """The RFC 8707 resource indicator for an MCP server URL.

    Scheme and host lowercased, the default port dropped, userinfo dropped,
    query and fragment never carried (RFC 8707 §2), and a trailing slash
    collapsed so ``https://host/mcp`` and ``https://host/mcp/`` bind to one
    resource. Every audience check in this module compares through here, so
    one function owns the spelling.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) server URL: {url!r}")
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if ":" in host:  # IPv6 literal — restore the brackets
        host = f"[{host}]"
    port = parts.port
    default_port = {"http": 80, "https": 443}[scheme]
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parts.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def make_pkce() -> Tuple[str, str]:
    """A PKCE verifier and its S256 challenge.

    ``token_urlsafe``'s alphabet is unreserved per RFC 7636, and 86
    characters sits inside the 43–128 verifier window. Same construction the
    federated sign-in uses — one spelling of PKCE in this codebase.
    """
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


# --------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProtectedResourceMetadata:
    """RFC 9728: what the resource server says about itself."""

    resource: str
    authorization_servers: Tuple[str, ...]
    scopes_supported: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizationServerMetadata:
    """RFC 8414: the endpoints Vigil exchanges tokens at."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str


def _well_known_candidates(base_url: str, well_known: str) -> List[str]:
    """RFC 9728 §3.1 / RFC 8414 §3.1 candidate URLs, path-aware form first.

    For ``https://host/mcp`` the well-known URI is inserted between the host
    and the path before the origin-root form is tried.
    """
    parts = urlsplit(base_url)
    origin = f"{parts.scheme.lower()}://{parts.netloc}"
    path = parts.path.rstrip("/")
    candidates = []
    if path:
        candidates.append(f"{origin}{well_known}{path}")
    candidates.append(f"{origin}{well_known}")
    return candidates


def _http_or_injected(
    http_client: Optional[httpx.AsyncClient],
) -> Tuple[httpx.AsyncClient, bool]:
    """The client to use, and whether this scope owns closing it."""
    if http_client is not None:
        return http_client, False
    return httpx.AsyncClient(timeout=10.0), True


async def discover_protected_resource(
    server_url: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> ProtectedResourceMetadata:
    """Read the resource server's RFC 9728 document, fail-closed.

    A document that names no ``resource``, or no authorization server to
    talk to, is not metadata Vigil can bind a token with — it is a refusal.
    """
    client, owns = _http_or_injected(http_client)
    try:
        for candidate in _well_known_candidates(server_url, _WELL_KNOWN_PRM):
            try:
                response = await client.get(candidate)
            except httpx.HTTPError as exc:
                logger.debug("PRM probe %s failed: %s", candidate, exc)
                continue
            if response.status_code != 200:
                continue
            try:
                doc = response.json()
            except ValueError:
                continue
            resource = doc.get("resource")
            servers = doc.get("authorization_servers") or []
            if not resource or not servers:
                continue
            metadata = ProtectedResourceMetadata(
                resource=canonical_resource(str(resource)),
                authorization_servers=tuple(str(s) for s in servers),
                scopes_supported=tuple(
                    str(s) for s in doc.get("scopes_supported") or []
                ),
            )
            logger.debug(
                "PRM discovered for %s via %s",
                canonical_resource(server_url),
                candidate,
            )
            return metadata
        raise DiscoveryFailed(
            f"no usable Protected Resource Metadata at {canonical_resource(server_url)}"
        )
    finally:
        if owns:
            await client.aclose()


async def discover_authorization_server(
    as_url: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> AuthorizationServerMetadata:
    """Read the authorization server's RFC 8414 document, issuer-checked.

    The ``issuer`` claim must match the URL the document was discovered at
    (RFC 8414 §3.3, up to a trailing slash) — metadata that names another
    issuer is a spoofing attempt, not a shortcut.
    """
    client, owns = _http_or_injected(http_client)
    try:
        for candidate in _well_known_candidates(as_url, _WELL_KNOWN_AS):
            try:
                response = await client.get(candidate)
            except httpx.HTTPError as exc:
                logger.debug("AS metadata probe %s failed: %s", candidate, exc)
                continue
            if response.status_code != 200:
                continue
            try:
                doc = response.json()
            except ValueError:
                continue
            authorization_endpoint = doc.get("authorization_endpoint")
            token_endpoint = doc.get("token_endpoint")
            if not authorization_endpoint or not token_endpoint:
                continue
            derived_issuer = candidate.split(_WELL_KNOWN_AS, 1)[0].rstrip("/")
            if str(doc.get("issuer") or "").rstrip("/") != derived_issuer:
                logger.warning(
                    "AS metadata at %s claims issuer %s — refusing",
                    candidate,
                    doc.get("issuer"),
                )
                continue
            return AuthorizationServerMetadata(
                issuer=derived_issuer,
                authorization_endpoint=str(authorization_endpoint),
                token_endpoint=str(token_endpoint),
            )
        raise DiscoveryFailed(f"no usable authorization-server metadata at {as_url}")
    finally:
        if owns:
            await client.aclose()


# --------------------------------------------------------------------- #
# Tokens: the cache and the passthrough guard
# --------------------------------------------------------------------- #


@dataclass
class CachedToken:
    """One issued token, and the only server it may ever be sent to."""

    access_token: str
    expires_at: float
    refresh_token: Optional[str]
    resource: str
    username: str


def require_bound_token(token: CachedToken, resource: str) -> None:
    """The passthrough guard: refuse a token offered to another resource.

    Every read path in this module funnels through here — a cache keyed by
    resource is the first wall, and this is the second, so even a corrupted
    store or a future read path that forgets the key cannot hand server A's
    token to server B. When the access token is a decodable JWT, its own
    ``aud`` claim must agree with the resource it is offered to: the cache
    slot a token sits in is data, and the audience inside the token is what
    a resource server will actually enforce (RFC 8707). Opaque tokens —
    not decodable JWTs — fall back to the cached-resource check alone.
    """
    if token.resource != resource:
        raise TokenPassthroughRefused(
            "token minted for %s may not authenticate %s (token passthrough prohibited)"
            % (token.resource, resource)
        )
    token_aud = _token_audience(token.access_token)
    if token_aud is not None and token_aud != resource:
        raise TokenPassthroughRefused(
            "token audience %s may not authenticate %s (token passthrough prohibited)"
            % (token_aud, resource)
        )


def _token_audience(access_token: str) -> Optional[str]:
    """The aud claim of a JWT access token, read without verification.

    Signature verification belongs to the issuer that minted the token
    and the resource server that accepts it; here the claim is only read
    to decide whether this token may be PRESENTED at all. A non-JWT
    (opaque) token yields None.
    """
    try:
        claims = jwt.decode(access_token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    except Exception:  # malformed token shapes must never block a refusal
        return None
    aud = claims.get("aud")
    return aud if isinstance(aud, str) else None


class TokenStore:
    """Per-(user, resource) token cache, in memory, with expiry.

    Keyed by the resource the token was minted for — the user alone is not
    the key, because one user legitimately holds one token per connector and
    a lookup that ignores the resource is the passthrough bug this PR exists
    to close.
    """

    def __init__(self) -> None:
        self._tokens: Dict[Tuple[str, str], CachedToken] = {}

    def get(self, username: str, resource: str) -> Optional[CachedToken]:
        """The stored token for (user, resource), expired or not.

        Expiry is a caller decision, not a store decision — and the store
        never drops on read: an expired access token still carries a
        refresh grant worth exactly one silent renewal, and a read that
        discarded it would turn every expiry into a re-authorization
        prompt.
        """
        token = self._tokens.get((username, resource))
        if token is not None:
            require_bound_token(token, resource)
        return token

    def put(self, token: CachedToken) -> None:
        self._tokens[(token.username, token.resource)] = token

    def invalidate(self, username: str, resource: str) -> None:
        self._tokens.pop((username, resource), None)


# --------------------------------------------------------------------- #
# Pending authorization state (the browser leg)
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class PendingAuthorization:
    """What must survive between the redirect out and the callback back."""

    server_name: str
    username: str
    code_verifier: str
    resource: str
    redirect_uri: str


class AuthorizationStateStore(Protocol):
    """Single-use, short-lived holder for one attempted connector grant."""

    async def put(self, state: str, pending: PendingAuthorization) -> None:
        """Persist one attempt for ``STATE_TTL_SECONDS``."""
        ...

    async def pop(self, state: str) -> Optional[PendingAuthorization]:
        """Remove and return the attempt named ``state``, or None.

        Removal is the point: a replayed callback finds nothing.
        """
        ...


_STATE_KEY_PREFIX = "vigil:mcp:oauth:"


class RedisAuthorizationStateStore:
    """The Redis-backed store. Every failure mode is a refusal."""

    async def put(self, state: str, pending: PendingAuthorization) -> None:
        client = self._client("write")
        try:
            await client.set(
                _STATE_KEY_PREFIX + state,
                json.dumps(
                    {
                        "server_name": pending.server_name,
                        "username": pending.username,
                        "code_verifier": pending.code_verifier,
                        "resource": pending.resource,
                        "redirect_uri": pending.redirect_uri,
                    }
                ),
                ex=STATE_TTL_SECONDS,
            )
        except Exception as exc:
            raise IdentityError(f"could not store MCP OAuth state: {exc}") from exc

    async def pop(self, state: str) -> Optional[PendingAuthorization]:
        client = self._client("read")
        try:
            # GETDEL: one round trip, and the attempt is consumed whether or
            # not what follows succeeds.
            raw = await client.getdel(_STATE_KEY_PREFIX + state)
        except Exception as exc:
            raise IdentityError(f"could not read MCP OAuth state: {exc}") from exc
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return PendingAuthorization(
                server_name=data["server_name"],
                username=data["username"],
                code_verifier=data["code_verifier"],
                resource=data["resource"],
                redirect_uri=data["redirect_uri"],
            )
        except (KeyError, TypeError, ValueError):
            # Unparseable is worse than absent — treat as replay and die.
            logger.warning("Discarding unparseable MCP OAuth state %s", state[:8])
            return None

    @staticmethod
    def _client(purpose: str):
        client = get_async_redis(f"MCP OAuth state {purpose}")
        if client is None:
            raise IdentityError("Redis unavailable — cannot hold MCP OAuth state")
        return client


class InMemoryAuthorizationStateStore:
    """For deployments and tests that do not run Redis.

    Dev-only by nature: the callback has to land in the same process that
    began the flow, which a single-process install guarantees and a
    multi-worker deployment does not. Production uses the Redis store.
    """

    def __init__(self, ttl_seconds: int = STATE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._pending: Dict[str, Tuple[float, PendingAuthorization]] = {}

    async def put(self, state: str, pending: PendingAuthorization) -> None:
        self._pending[state] = (time.time() + self._ttl, pending)

    async def pop(self, state: str) -> Optional[PendingAuthorization]:
        entry = self._pending.pop(state, None)
        if entry is None:
            return None
        expires_at, pending = entry
        if expires_at <= time.time():
            return None
        return pending


# --------------------------------------------------------------------- #
# The per-server OAuth client
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class AuthorizationStart:
    """The URL the user completes in their browser, and the state to match."""

    state: str
    authorization_url: str


class ServerOAuthClient:
    """The OAuth client for one HTTP-capable MCP connector.

    One instance per server, owned by the process MCP client. It holds the
    connector's client registration (id, optional secret resolved by the
    caller through ``get_secret``), the discovery cache, and — through the
    shared :class:`TokenStore` — every user's audience-bound token for it.
    """

    def __init__(
        self,
        *,
        server_name: str,
        http_url: str,
        client_id: str,
        client_secret: Optional[str] = None,
        scopes: Tuple[str, ...] = (),
        store: Optional[TokenStore] = None,
        state_store: Optional[AuthorizationStateStore] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        now: Any = None,
    ) -> None:
        self._server_name = server_name
        self._http_url = http_url
        self._resource = canonical_resource(http_url)
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = tuple(scopes)
        self._store = store if store is not None else TokenStore()
        self._state_store = (
            state_store if state_store is not None else (RedisAuthorizationStateStore())
        )
        self._owns_http = http_client is None
        self._http = (
            http_client if http_client is not None else httpx.AsyncClient(timeout=10.0)
        )
        self._now = now if now is not None else time.time
        self._prm: Optional[ProtectedResourceMetadata] = None
        self._as_meta: Optional[AuthorizationServerMetadata] = None
        self._discovered_at = 0.0

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def resource(self) -> str:
        """The canonical URI every token for this connector is bound to."""
        return self._resource

    # -- discovery -------------------------------------------------------

    def _discovery_fresh(self) -> bool:
        return (
            self._prm is not None
            and self._as_meta is not None
            and self._now() - self._discovered_at < DISCOVERY_TTL_SECONDS
        )

    async def protected_resource(self) -> ProtectedResourceMetadata:
        if not self._discovery_fresh():
            await self._discover()
        assert self._prm is not None  # _discover fills both or raises
        return self._prm

    async def authorization_server(self) -> AuthorizationServerMetadata:
        if not self._discovery_fresh():
            await self._discover()
        assert self._as_meta is not None
        return self._as_meta

    async def _discover(self) -> None:
        prm = await discover_protected_resource(
            self._http_url, http_client=self._http if not self._owns_http else None
        )
        as_meta = await discover_authorization_server(
            prm.authorization_servers[0],
            http_client=self._http if not self._owns_http else None,
        )
        self._prm = prm
        self._as_meta = as_meta
        self._discovered_at = self._now()

    # -- the authorization-code flow -------------------------------------

    async def begin_authorization(
        self, username: str, redirect_uri: str
    ) -> AuthorizationStart:
        """Build the consent URL for one user's browser leg.

        The ``resource`` parameter rides the authorization request (RFC 8707
        §2) — binding happens at the front of the flow, not only at the token
        endpoint, so the issued code itself is already scoped to this server.
        A consent flow names the user it is for; a caller with no bound user
        has nothing to authorize and is refused here rather than minting a
        consent for nobody.
        """
        if not username or not username.strip():
            raise IdentityError(
                "a connector consent flow requires an authenticated user"
            )
        as_meta = await self.authorization_server()
        prm = await self.protected_resource()
        state = secrets.token_urlsafe(32)
        verifier, challenge = make_pkce()
        await self._state_store.put(
            state,
            PendingAuthorization(
                server_name=self._server_name,
                username=username,
                code_verifier=verifier,
                resource=self._resource,
                redirect_uri=redirect_uri,
            ),
        )
        scopes = self._scopes or prm.scopes_supported
        url = str(
            httpx.Request(
                "GET",
                as_meta.authorization_endpoint,
                params={
                    "response_type": "code",
                    "client_id": self._client_id,
                    "redirect_uri": redirect_uri,
                    "scope": " ".join(scopes),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "resource": self._resource,
                },
            ).url
        )
        return AuthorizationStart(state=state, authorization_url=url)

    async def complete_authorization(
        self, username: str, code: str, state: str
    ) -> CachedToken:
        """Swap the callback's code for this user's audience-bound token."""
        pending = await self._state_store.pop(state)
        if pending is None:
            raise TokenExchangeFailed("unknown or expired authorization state")
        if (
            pending.username != username
            or pending.server_name != self._server_name
            or pending.resource != self._resource
        ):
            # The state belongs to someone else's attempt, or to another
            # connector: a callback that cannot be matched to its flow is a
            # replay or a mix-up, and either way it completes nothing.
            raise TokenExchangeFailed(
                "authorization state does not match this user and connector"
            )
        data = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": pending.redirect_uri,
                "client_id": self._client_id,
                "code_verifier": pending.code_verifier,
                "resource": self._resource,
            }
        )
        return self._cache_token(data, username)

    # -- the dispatch read path -------------------------------------------

    def cached_token(self, username: str) -> Optional[CachedToken]:
        """The user's unexpired token for this connector, if any.

        A pure read: the expired entry stays put so ``refresh`` can still
        salvage its grant — dropping here would race the salvage away.
        """
        token = self.stored_token(username)
        if token is not None and token.expires_at > self._now():
            return token
        return None

    def stored_token(self, username: str) -> Optional[CachedToken]:
        """The cached token even when expired — the refresh grant may renew it."""
        token = self._store.get(username, self._resource)
        if token is not None:
            require_bound_token(token, self._resource)
        return token

    async def bearer_token(self, username: str) -> str:
        """The access token to present to this connector, or a refusal.

        An expired-but-refreshable token renews here, before a doomed
        request is ever sent. The refusal is the design: a headless
        dispatch cannot pop a browser, and forwarding some other token
        would be exactly the passthrough this module exists to prohibit.
        """
        token = self.cached_token(username)
        if token is not None:
            return token.access_token
        refreshed = await self.refresh(username)
        if refreshed is not None:
            return refreshed
        raise AuthorizationRequired(
            f"connector {self._server_name} is not authorized for {username} — "
            "complete the connector's consent flow in Settings"
        )

    def invalidate(self, username: str) -> None:
        self._store.invalidate(username, self._resource)

    async def refresh(self, username: str) -> Optional[str]:
        """One refresh-grant attempt; None when a re-authorization is needed."""
        token = self.stored_token(username)
        if token is None or not token.refresh_token:
            self.invalidate(username)
            return None
        try:
            data = await self._token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": self._client_id,
                    "resource": self._resource,
                }
            )
        except TokenExchangeFailed as exc:
            logger.info(
                "Refresh refused for %s/%s — re-authorization required: %s",
                self._server_name,
                username,
                exc,
            )
            self.invalidate(username)
            return None
        refreshed = self._cache_token(
            data, username, fallback_refresh_token=token.refresh_token
        )
        return refreshed.access_token

    # -- the token endpoint -----------------------------------------------

    async def _token_request(self, form: Dict[str, str]) -> Dict[str, Any]:
        as_meta = await self.authorization_server()
        # A confidential client authenticates with Basic (RFC 6749 §2.3.1);
        # a public client — the MCP norm — carries only its client_id.
        request_kwargs: Dict[str, Any] = {"data": form}
        if self._client_secret:
            request_kwargs["auth"] = (self._client_id, self._client_secret)
        try:
            response = await self._http.post(as_meta.token_endpoint, **request_kwargs)
        except httpx.HTTPError as exc:
            raise TokenExchangeFailed(f"token endpoint unreachable: {exc}") from exc
        if response.status_code != 200:
            raise TokenExchangeFailed(f"token endpoint returned {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise TokenExchangeFailed("token endpoint sent a non-JSON body") from exc
        if not data.get("access_token"):
            raise TokenExchangeFailed("token response carried no access_token")
        token_type = str(data.get("token_type") or "bearer").lower()
        if token_type != "bearer":
            raise TokenExchangeFailed(
                f"unsupported token type {token_type!r} — MCP uses Bearer"
            )
        return data

    def _cache_token(
        self,
        data: Dict[str, Any],
        username: str,
        fallback_refresh_token: Optional[str] = None,
    ) -> CachedToken:
        expires_in = int(data.get("expires_in") or 3600)
        ttl = max(expires_in - _TOKEN_EXPIRY_MARGIN_S, 1)
        token = CachedToken(
            access_token=str(data["access_token"]),
            expires_at=self._now() + ttl,
            refresh_token=(
                str(data["refresh_token"])
                if data.get("refresh_token")
                else fallback_refresh_token
            ),
            resource=self._resource,
            username=username,
        )
        self._store.put(token)
        return token
