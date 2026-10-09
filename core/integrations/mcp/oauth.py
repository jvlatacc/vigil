"""OAuth 2.1 token provider for remote MCP servers — the MCP authorization profile.

Vigil is the OAuth client toward URL-based MCP servers. One provider per
server: discovery follows the server's own 401 challenge (RFC 9728 Protected
Resource Metadata) or a configured issuer, every token request carries the
server's RFC 8707 ``resource`` so tokens are audience-bound to that server
and nothing else, and refresh is serialized per server with rotation and
reuse detection. No vendor SDK: any issuer that serves RFC 8414 / OIDC
metadata works (Okta, Entra ID, Keycloak, Auth0).

Grants:
  * ``client_credentials`` — machine-to-machine servers; token + expiry
    cached in memory, re-acquired on expiry.
  * ``authorization_code`` + PKCE(S256) — user-delegated servers; one
    interactive consent (``start_authorization`` / ``complete_authorization``),
    then the refresh grant with rotation.

Storage rules, never violated in this module:
  * access tokens live in memory only,
  * refresh tokens and client secrets live only in the encrypted secrets
    store (``core.secrets``),
  * nothing token-shaped is ever logged — the aad_token.py precedent sets
    the bar.
"""

import asyncio
import base64
import enum
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from core.secrets import get_secret, set_secret

logger = logging.getLogger(__name__)

#: Treat a token as expired this many seconds before its real ``exp`` so a
#: call never ships a token that dies mid-flight.
EXPIRY_SKEW_S = 30.0

_TOKEN_TIMEOUT_S = 30.0

_GRANTS = ("client_credentials", "authorization_code")


class TokenError(Exception):
    """An OAuth flow failed; ``str()`` is safe to show to a tool caller."""


class MissingCredentials(TokenError):
    """A secret the flow needs (a client secret) is not in the store."""


class GrantRejected(TokenError):
    """The issuer refused the grant (``invalid_grant``, ``invalid_client``…)."""

    def __init__(self, error: str, description: str):
        super().__init__(f"{error}: {description}" if description else error)
        self.oauth_error = error


class NeedsReauth(TokenError):
    """The grant cannot be repaired without fresh interactive consent."""


class ProviderState(str, enum.Enum):
    """Connection state the provider reports.

    ``pending`` (no acquisition attempted yet) maps onto the operator's
    dormant display; ``needs_consent``, ``connected`` and ``error`` are the
    blueprint's own states.
    """

    PENDING = "pending"
    CONNECTED = "connected"
    NEEDS_CONSENT = "needs_consent"
    ERROR = "error"


@dataclass(frozen=True)
class ServerAuthConfig:
    """A server's ``auth`` block, resolved and validated.

    Secret *values* never ride config: ``client_secret_key`` names an entry
    in the encrypted secrets store, read at acquire time.
    """

    server_name: str
    server_url: str
    grant: str
    client_id: str
    client_secret_key: Optional[str] = None
    issuer_url: Optional[str] = None
    scopes: Tuple[str, ...] = ()
    resource: Optional[str] = None
    refresh_token_key: Optional[str] = None

    def __post_init__(self) -> None:
        if self.grant not in _GRANTS:
            raise TokenError(
                f"MCP server {self.server_name!r}: unsupported OAuth grant {self.grant!r}"
            )
        if self.grant == "client_credentials" and not self.client_secret_key:
            raise TokenError(
                f"MCP server {self.server_name!r}: the client_credentials grant "
                "needs a client_secret_key"
            )
        if not self.server_url:
            raise TokenError(
                f"MCP server {self.server_name!r}: the auth block needs a server URL"
            )

    @property
    def resource_url(self) -> str:
        # RFC 8707: the resource indicator defaults to the server's own URL.
        return self.resource or self.server_url

    @property
    def refresh_key(self) -> str:
        """Secrets-store key holding this server's refresh token."""
        if self.refresh_token_key:
            return self.refresh_token_key
        return "MCP_OAUTH_REFRESH_" + re.sub(
            r"[^A-Z0-9]", "_", self.server_name.upper()
        )

    @classmethod
    def from_server_entry(
        cls, server_name: str, auth: Mapping[str, Any]
    ) -> "ServerAuthConfig":
        """Parse the ``auth`` block of an mcp-config.json server entry."""
        if not isinstance(auth, Mapping):
            raise TokenError(
                f"MCP server {server_name!r}: the auth block must be an object"
            )
        grant = str(auth.get("grant", "client_credentials"))
        if str(auth.get("type", "oauth2")) != "oauth2":
            raise TokenError(
                f"MCP server {server_name!r}: only type=oauth2 is supported"
            )
        scopes = auth.get("scopes") or ()
        return cls(
            server_name=server_name,
            server_url=str(auth.get("server_url") or auth.get("url") or ""),
            grant=grant,
            client_id=str(auth.get("client_id", "")),
            client_secret_key=auth.get("client_secret_key"),
            issuer_url=auth.get("issuer_url"),
            scopes=tuple(str(scope) for scope in scopes),
            resource=auth.get("resource"),
            refresh_token_key=auth.get("refresh_token_key"),
        )


def parse_www_authenticate_challenge(value: str) -> Dict[str, str]:
    """Parse a ``WWW-Authenticate`` header into scheme + parameter map.

    Tolerates quoted values and commas inside them; returns ``{"scheme":
    "bearer", ...}`` — the ``resource_metadata`` parameter is what discovery
    follows (RFC 6750 framing, RFC 9728 semantics). Unparseable → ``{}``.
    """
    params: Dict[str, str] = {}
    value = value.strip()
    if not value:
        return params
    # RFC 6750 framing: one whitespace after the scheme, then comma-separated
    # params (which may themselves carry quoted, comma-bearing values).
    scheme, _, rest = value.partition(" ")
    params["scheme"] = scheme.strip().lower()
    rest = rest.strip()
    if not rest:
        return params
    for part in _split_challenge(rest):
        key, sep, val = part.partition("=")
        if not sep:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] == '"':
            val = val[1:-1]
        params[key.strip().lower()] = val
    return params


def _split_challenge(value: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    in_quotes = False
    for char in value:
        if char == '"':
            in_quotes = not in_quotes
            buf.append(char)
        elif char == "," and not in_quotes:
            if buf:
                parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    if buf and "".join(buf).strip():
        parts.append("".join(buf).strip())
    return [part for part in parts if part]


def well_known_metadata_urls(issuer: str) -> List[str]:
    """Discovery URLs for an issuer — RFC 8414 first, then OIDC.

    Each spec inserts its well-known path by its own rule (RFC 8414 §3.1
    between host and path; OIDC appends), so path-bearing issuers such as
    Entra's ``https://login.microsoftonline.com/{tenant}/v2.0`` resolve
    under both orderings.
    """
    issuer = issuer.rstrip("/")
    parsed = urlparse(issuer)
    if not parsed.scheme or not parsed.netloc:
        return []
    root = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path
    return [
        f"{root}/.well-known/oauth-authorization-server{path}",
        f"{issuer}/.well-known/openid-configuration",
    ]


def pkce_pair() -> Tuple[str, str]:
    """``(code_verifier, code_challenge)`` — S256, RFC 7636 §4.2."""
    verifier = token_urlsafe(64)  # 86 unreserved chars, inside the 43..128 band
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthTokenProvider:
    """Per-server token provider.

    Token cache, consent state, and the refresh lock live here, so every
    surface that calls a server's tools (chat, ``/mcp``,
    ``/internal/tools/invoke``, the HTTP transport) shares one token
    lifecycle for that server.
    """

    #: Issuer sent no ``expires_in``: assume five minutes rather than trust
    #: a token forever.
    _DEFAULT_EXPIRES_IN_S = 300.0

    def __init__(
        self,
        config: ServerAuthConfig,
        *,
        clock: Optional[Callable[[], float]] = None,
        http: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.config = config
        self._clock = clock or time.time
        self._http = http
        self._owned_http: Optional[httpx.AsyncClient] = None
        self._refresh_lock = asyncio.Lock()
        self._access_token: Optional[str] = None
        self._expires_at = 0.0
        self._metadata: Optional[Dict[str, Any]] = None
        self._rotated_out: Optional[str] = None
        self._pending: Optional[Dict[str, str]] = (
            None  # {verifier, state, redirect_uri}
        )
        self.state = (
            ProviderState.NEEDS_CONSENT
            if config.grant == "authorization_code"
            else ProviderState.PENDING
        )
        self.last_error: Optional[str] = None

    # -- public surface ---------------------------------------------------

    async def bearer(self) -> str:
        """A valid access token bound to this server's resource; acquires or
        refreshes as needed. Concurrent callers share one refresh."""
        async with self._refresh_lock:
            if self._access_token and self._clock() < self._expires_at:
                return self._access_token
            return await self._acquire()

    async def on_unauthorized(self) -> str:
        """The server answered 401 / ``insufficient_scope``: force one
        refresh so the caller can retry the original request exactly once."""
        async with self._refresh_lock:
            self._access_token = None
            self._expires_at = 0.0
            return await self._acquire()

    @property
    def access_token_expires_at(self) -> Optional[float]:
        """Wall-clock expiry of the cached token, for operator display."""
        return self._expires_at if self._access_token else None

    async def aclose(self) -> None:
        if self._owned_http is not None:
            await self._owned_http.aclose()
            self._owned_http = None

    # -- acquisition ------------------------------------------------------

    async def _acquire(self) -> str:
        try:
            if self.config.grant == "client_credentials":
                doc = await self._token_request({"grant_type": "client_credentials"})
            else:
                doc = await self._refresh_grant()
        except NeedsReauth as exc:
            self.state = ProviderState.NEEDS_CONSENT
            self.last_error = str(exc)
            raise
        except TokenError as exc:
            self.state = ProviderState.ERROR
            self.last_error = str(exc)
            raise
        self._absorb(doc)
        self.state = ProviderState.CONNECTED
        self.last_error = None
        return str(doc["access_token"])

    async def _refresh_grant(self) -> Dict[str, Any]:
        stored = get_secret(self.config.refresh_key)
        if not stored:
            raise NeedsReauth("no refresh token on file — consent required")
        try:
            doc = await self._token_request(
                {"grant_type": "refresh_token", "refresh_token": stored}
            )
        except GrantRejected as exc:
            if exc.oauth_error != "invalid_grant":
                raise
            if stored == self._rotated_out:
                # A token we ourselves rotated away came back: it was already
                # spent, so a second consumer is replaying it. Security event,
                # not a hiccup — the connection drops to needs_reauth either
                # way, but the operator should know which kind of refusal
                # this was.
                logger.warning(
                    "MCP OAuth (%s): refresh-token reuse detected — a rotated "
                    "token was presented; requiring re-authentication",
                    self.config.server_name,
                )
            raise NeedsReauth(
                "refresh token rejected — re-authentication required"
            ) from exc
        rotated = doc.get("refresh_token")
        if rotated and rotated != stored:
            self._rotated_out = stored
            if not set_secret(self.config.refresh_key, str(rotated)):
                # The rotated token now exists only in memory; losing it
                # strands the connection on the next refresh — fail loudly
                # rather than quietly keeping the stale one.
                raise TokenError("could not persist the rotated refresh token")
        return doc

    def _absorb(self, doc: Mapping[str, Any]) -> None:
        """Cache the access token in memory (never anywhere else)."""
        self._access_token = str(doc["access_token"])
        try:
            expires_in = float(doc.get("expires_in"))
        except (TypeError, ValueError):
            expires_in = self._DEFAULT_EXPIRES_IN_S
        self._expires_at = self._clock() + max(expires_in - EXPIRY_SKEW_S, 1.0)

    async def _token_request(self, form: Dict[str, str]) -> Dict[str, Any]:
        """POST one token-endpoint request.

        Every request carries the RFC 8707 ``resource`` — tokens are
        audience-bound to this MCP server and nothing else.
        """
        metadata = await self._authorization_server_metadata()
        endpoint = metadata.get("token_endpoint")
        if not endpoint:
            raise TokenError("authorization-server metadata carries no token_endpoint")
        payload: Dict[str, str] = {"client_id": self.config.client_id, **form}
        payload["resource"] = self.config.resource_url
        if self.config.scopes:
            payload["scope"] = " ".join(self.config.scopes)
        if self.config.client_secret_key:
            secret = get_secret(self.config.client_secret_key)
            if not secret:
                raise MissingCredentials(
                    f"OAuth client secret {self.config.client_secret_key} is not set"
                )
            payload["client_secret"] = secret
        try:
            resp = await self._client().post(
                str(endpoint), data=payload, headers={"Accept": "application/json"}
            )
        except httpx.HTTPError as exc:
            logger.error(
                "MCP OAuth (%s): token request failed: %s",
                self.config.server_name,
                type(exc).__name__,
            )
            raise TokenError(
                f"token request to the authorization server failed "
                f"({type(exc).__name__})"
            ) from exc
        return self._parse_token_response(resp)

    def _parse_token_response(self, resp: httpx.Response) -> Dict[str, Any]:
        try:
            doc = resp.json()
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            doc = {}
        if resp.status_code >= 400:
            error = str(doc.get("error") or "")
            description = str(doc.get("error_description") or "")
            # aad_token.py precedent: log status + issuer error text, never
            # request or token material.
            logger.error(
                "MCP OAuth (%s): token request returned HTTP %s (%s) %s",
                self.config.server_name,
                resp.status_code,
                error or "<no error code>",
                description[:300],
            )
            if error:
                raise GrantRejected(error, description)
            raise TokenError(f"token request failed (HTTP {resp.status_code})")
        if not doc.get("access_token"):
            raise TokenError("token response carried no access_token")
        return doc

    # -- discovery --------------------------------------------------------

    async def _authorization_server_metadata(self) -> Dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        issuer = await self._resolve_issuer()
        for url in well_known_metadata_urls(issuer):
            try:
                resp = await self._client().get(
                    url, headers={"Accept": "application/json"}
                )
            except httpx.HTTPError as exc:
                logger.info(
                    "MCP OAuth (%s): metadata fetch from %s failed: %s",
                    self.config.server_name,
                    url,
                    type(exc).__name__,
                )
                continue
            if resp.status_code != 200:
                continue
            try:
                doc = resp.json()
            except ValueError:
                continue
            if not isinstance(doc, dict) or not doc.get("token_endpoint"):
                continue
            doc_issuer = doc.get("issuer")
            if doc_issuer and str(doc_issuer).rstrip("/") != issuer.rstrip("/"):
                # RFC 8414 §2: metadata that names another issuer is not this
                # issuer's — keep looking rather than trust a lookalike.
                logger.info(
                    "MCP OAuth (%s): metadata at %s names a different issuer; skipping",
                    self.config.server_name,
                    url,
                )
                continue
            self._metadata = doc
            return doc
        raise TokenError(f"could not discover OAuth metadata for issuer {issuer!r}")

    async def _resolve_issuer(self) -> str:
        """A configured issuer wins; otherwise one is discovered from the
        server's own 401 challenge — the MCP authorization profile's entry
        point (RFC 9728): the challenge names the protected-resource
        metadata document, which names the authorization servers."""
        if self.config.issuer_url:
            return self.config.issuer_url
        try:
            probe = await self._client().get(
                self.config.server_url, headers={"Accept": "application/json"}
            )
        except httpx.HTTPError as exc:
            raise TokenError(
                f"could not reach {self.config.server_url} to read its OAuth "
                f"challenge ({type(exc).__name__})"
            ) from exc
        if probe.status_code != 401:
            raise TokenError(
                f"{self.config.server_url} answered HTTP {probe.status_code} "
                "instead of a 401 OAuth challenge"
            )
        params = parse_www_authenticate_challenge(
            probe.headers.get("WWW-Authenticate", "")
        )
        if params.get("scheme") != "bearer":
            raise TokenError("server challenge is not a Bearer challenge")
        prm_url = params.get("resource_metadata") or urljoin(
            self.config.server_url, "/.well-known/oauth-protected-resource"
        )
        issuer = await self._protected_resource_issuer(prm_url)
        if not issuer:
            raise TokenError(
                "protected-resource metadata named no authorization server"
            )
        return issuer

    async def _protected_resource_issuer(self, prm_url: str) -> Optional[str]:
        try:
            resp = await self._client().get(
                prm_url, headers={"Accept": "application/json"}
            )
        except httpx.HTTPError as exc:
            raise TokenError(
                f"protected-resource metadata could not be fetched ({type(exc).__name__})"
            ) from exc
        if resp.status_code != 200:
            raise TokenError(
                f"protected-resource metadata returned HTTP {resp.status_code}"
            )
        try:
            doc = resp.json()
        except ValueError as exc:
            raise TokenError("protected-resource metadata is not JSON") from exc
        servers = doc.get("authorization_servers") if isinstance(doc, dict) else None
        if isinstance(servers, list) and servers:
            return str(servers[0])
        return None

    # -- consent flow (authorization_code + PKCE) --------------------------

    async def start_authorization(self, *, redirect_uri: str) -> Dict[str, str]:
        """Begin the one interactive consent: build the authorization URL
        with PKCE S256. Returns ``{authorization_url, state}``; the caller
        opens the URL in a browser and completes via
        ``complete_authorization``."""
        if self.config.grant != "authorization_code":
            raise TokenError(
                "start_authorization applies to the authorization_code grant only"
            )
        metadata = await self._authorization_server_metadata()
        authorize = metadata.get("authorization_endpoint")
        if not authorize:
            raise TokenError(
                "authorization-server metadata carries no authorization_endpoint"
            )
        verifier, challenge = pkce_pair()
        state = token_urlsafe(24)
        self._pending = {
            "verifier": verifier,
            "state": state,
            "redirect_uri": redirect_uri,
        }
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            # RFC 8707 on the front channel too, so the issuer binds the
            # code to this resource before the token exchange restates it.
            "resource": self.config.resource_url,
        }
        if self.config.scopes:
            params["scope"] = " ".join(self.config.scopes)
        return {
            "authorization_url": f"{authorize}?{urlencode(params)}",
            "state": state,
        }

    async def complete_authorization(self, *, code: str, state: str) -> None:
        """Finish the consent flow: exchange the authorization code with the
        stored verifier, persist the refresh token, and mark connected."""
        pending = self._pending
        if not pending or not state or state != pending["state"]:
            self._pending = None
            raise TokenError("authorization state mismatch — restart consent")
        if not code:
            raise TokenError("authorization callback carried no code")
        doc = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": pending["verifier"],
                "redirect_uri": pending["redirect_uri"],
            }
        )
        refresh = doc.get("refresh_token")
        if not refresh:
            # Without a refresh token every later call would need fresh
            # consent — refuse the half-connected state rather than mint one
            # that dies with the access token.
            raise TokenError(
                "issuer returned no refresh token; cannot complete connection"
            )
        if not set_secret(self.config.refresh_key, str(refresh)):
            raise TokenError("could not persist the refresh token")
        self._absorb(doc)
        self._pending = None
        self.state = ProviderState.CONNECTED
        self.last_error = None

    # -- plumbing ---------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        if self._owned_http is None:
            self._owned_http = httpx.AsyncClient(timeout=_TOKEN_TIMEOUT_S)
        return self._owned_http


class TokenProviderRegistry:
    """The server-keyed TokenProvider surface.

    ``bearer(server)`` / ``on_unauthorized(server)`` are what the transport
    calls; one provider per configured MCP server keeps each server's token
    lifecycle in exactly one place.
    """

    def __init__(
        self,
        provider_factory: Optional[
            Callable[[ServerAuthConfig], OAuthTokenProvider]
        ] = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._providers: Dict[str, OAuthTokenProvider] = {}

    def configure(self, config: ServerAuthConfig) -> OAuthTokenProvider:
        provider = (
            self._provider_factory(config)
            if self._provider_factory
            else OAuthTokenProvider(config)
        )
        self._providers[config.server_name] = provider
        return provider

    def provider_for(self, server_name: str) -> Optional[OAuthTokenProvider]:
        return self._providers.get(server_name)

    def forget(self, server_name: str) -> None:
        self._providers.pop(server_name, None)

    async def bearer(self, server: str) -> str:
        provider = self._providers.get(server)
        if provider is None:
            raise TokenError(
                f"no OAuth configuration is registered for MCP server {server!r}"
            )
        return await provider.bearer()

    async def on_unauthorized(self, server: str) -> str:
        provider = self._providers.get(server)
        if provider is None:
            raise TokenError(
                f"no OAuth configuration is registered for MCP server {server!r}"
            )
        return await provider.on_unauthorized()

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()


_registry: Optional[TokenProviderRegistry] = None


# Deliberate process-wide singleton. The registry is a cross-request,
# server-keyed token cache — one provider per configured MCP server, with
# serialized refresh — so per-caller instances would re-authenticate every
# request and race refreshes. Secrets never live here: providers read
# credentials from the encrypted secrets store; the registry holds only live
# tokens. The DI refactor is deferred mid-wave — threading an instance through
# every transport call site would ripple into open PR #67.
def token_providers() -> TokenProviderRegistry:
    """Process-wide registry; the transport resolves tokens through here."""
    global _registry
    if _registry is None:
        _registry = TokenProviderRegistry()
    return _registry


def reset_token_providers() -> None:
    """Tests reset the registry so suites never share provider state."""
    global _registry
    _registry = None
