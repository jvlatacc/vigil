"""Unit tests for the MCP OAuth identity layer (core/integrations/mcp/identity.py).

The stub authorization server runs under respx (identity.py rides plain
httpx) and mints real HS256 JWTs whose ``aud`` is the ``resource`` parameter
the request carried — so every audience-binding assertion below checks the
token a connector would actually receive, not a Vigil-invented claim.
"""

import base64
import hashlib
import time

import jwt
import pytest
import respx
from httpx import Response

from core.integrations.mcp.identity import (
    AuthorizationRequired,
    CachedToken,
    InMemoryAuthorizationStateStore,
    ServerOAuthClient,
    TokenPassthroughRefused,
    TokenStore,
    canonical_resource,
    make_pkce,
)

AS_ISSUER = "https://as.example.com"
AS_SECRET = "test-as-secret"
CONNECTOR_URL = "https://connector.example/mcp"
RESOURCE = canonical_resource(CONNECTOR_URL)


_MINT_SEQ = iter(range(1, 1_000_000))


def mint(resource: str, username: str = "analyst", ttl: int = 300) -> str:
    """A real access token the stub AS would hand out, aud-bound to resource."""
    now = int(time.time())
    return jwt.encode(
        {
            "iss": AS_ISSUER,
            "aud": resource,
            "sub": username,
            "iat": now,
            "exp": now + ttl,
            "jti": str(next(_MINT_SEQ)),
        },
        AS_SECRET,
        algorithm="HS256",
    )


def make_client(
    store: TokenStore | None = None,
    http_url: str = CONNECTOR_URL,
) -> ServerOAuthClient:
    return ServerOAuthClient(
        server_name="connector",
        http_url=http_url,
        client_id="vigil-mcp",
        scopes=("mcp:tools",),
        store=store if store is not None else TokenStore(),
        state_store=InMemoryAuthorizationStateStore(),
    )


def seed_token(
    store: TokenStore,
    username: str,
    resource: str,
    *,
    refresh_token: str | None = "rt-1",
    expires_in: float = 300,
) -> CachedToken:
    token = CachedToken(
        access_token=mint(resource, username),
        expires_at=time.time() + expires_in,
        refresh_token=refresh_token,
        resource=resource,
        username=username,
    )
    store.put(token)
    return token


# --------------------------------------------------------------------- #
# canonical_resource — the one spelling every audience check compares
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://connector.example/mcp", "https://connector.example/mcp"),
        ("https://connector.example/mcp/", "https://connector.example/mcp"),
        (
            "HTTPS://Connector.Example:443/mcp",
            "https://connector.example/mcp",
        ),
        (
            "https://connector.example:8443/mcp",
            "https://connector.example:8443/mcp",
        ),
        ("http://connector.example:80/mcp", "http://connector.example/mcp"),
    ],
)
def test_canonical_resource_normalizes(url, expected):
    assert canonical_resource(url) == expected


def test_canonical_resource_rejects_non_http():
    with pytest.raises(ValueError):
        canonical_resource("ftp://connector.example/mcp")


# --------------------------------------------------------------------- #
# PKCE
# --------------------------------------------------------------------- #


def test_pkce_verifier_and_challenge_shape():
    verifier, challenge = make_pkce()
    assert 43 <= len(verifier) <= 128
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert challenge == expected
    # A fresh draw never repeats — S256 challenges are single-use.
    assert make_pkce()[0] != verifier


# --------------------------------------------------------------------- #
# TokenStore — keyed by (user, resource), guarded against a corrupted read
# --------------------------------------------------------------------- #


def test_store_is_keyed_by_user_and_resource():
    store = TokenStore()
    seed_token(store, "analyst", RESOURCE)
    assert store.get("analyst", RESOURCE) is not None
    assert store.get("other-user", RESOURCE) is None


def test_store_refuses_cross_resource_read():
    """Defense in depth: even a store whose keying is corrupted — server B's
    key holding server A's token — must refuse the read rather than release
    the token (token passthrough is prohibited, in code not just in docs)."""
    store = TokenStore()
    token = seed_token(store, "analyst", RESOURCE)
    store._tokens[("analyst", "https://other.example/mcp")] = token
    with pytest.raises(TokenPassthroughRefused):
        store.get("analyst", "https://other.example/mcp")


def test_store_keeps_expired_token_for_refresh_salvage():
    """get() returns expired tokens untouched: the refresh grant is worth
    exactly one silent renewal, and a read that discarded it would turn
    every expiry into a re-authorization prompt."""
    store = TokenStore()
    seed_token(store, "analyst", RESOURCE, expires_in=-10)
    expired = store.get("analyst", RESOURCE)
    assert expired is not None and expired.refresh_token == "rt-1"


# --------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------- #


@respx.mock
@pytest.mark.asyncio
async def test_discover_protected_resource():
    respx.get(
        "https://connector.example/.well-known/oauth-protected-resource/mcp"
    ).mock(
        return_value=Response(
            200,
            json={
                "resource": RESOURCE,
                "authorization_servers": [AS_ISSUER],
                "scopes_supported": ["mcp:tools"],
            },
        )
    )
    respx.get("https://as.example.com/.well-known/oauth-authorization-server").mock(
        return_value=Response(
            200,
            json={
                "issuer": AS_ISSUER,
                "authorization_endpoint": f"{AS_ISSUER}/authorize",
                "token_endpoint": f"{AS_ISSUER}/token",
            },
        )
    )
    client = make_client()
    prm = await client.protected_resource()
    assert prm.resource == RESOURCE
    assert prm.authorization_servers == (AS_ISSUER,)


@respx.mock
@pytest.mark.asyncio
async def test_discover_authorization_server_rejects_issuer_mismatch():
    """Metadata that names another issuer is a spoofing attempt."""
    respx.get("https://as.example.com/.well-known/oauth-authorization-server").mock(
        return_value=Response(
            200,
            json={
                "issuer": "https://evil.example",
                "authorization_endpoint": f"{AS_ISSUER}/authorize",
                "token_endpoint": f"{AS_ISSUER}/token",
            },
        )
    )
    respx.get(
        "https://connector.example/.well-known/oauth-protected-resource/mcp"
    ).mock(
        return_value=Response(
            200,
            json={"resource": RESOURCE, "authorization_servers": [AS_ISSUER]},
        )
    )
    client = make_client()
    with pytest.raises(Exception) as excinfo:
        await client.authorization_server()
    assert "authorization-server metadata" in str(excinfo.value)


# --------------------------------------------------------------------- #
# The token endpoint — RFC 8707 resource on every grant
# --------------------------------------------------------------------- #


def _route_token_endpoint(recorded):
    def handler(request):
        form = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
        from urllib.parse import unquote_plus

        form = {k: unquote_plus(v) for k, v in form.items()}
        recorded.append(form)
        resource = form.get("resource")
        return Response(
            200,
            json={
                "access_token": mint(resource),
                "token_type": "Bearer",
                "expires_in": 300,
                "refresh_token": f"rt-{len(recorded)}",
            },
        )

    respx.post(f"{AS_ISSUER}/token").mock(side_effect=handler)


def _route_discovery():
    """Both well-known documents: any token request runs full discovery."""
    respx.get(
        "https://connector.example/.well-known/oauth-protected-resource/mcp"
    ).mock(
        return_value=Response(
            200,
            json={"resource": RESOURCE, "authorization_servers": [AS_ISSUER]},
        )
    )
    respx.get("https://as.example.com/.well-known/oauth-authorization-server").mock(
        return_value=Response(
            200,
            json={
                "issuer": AS_ISSUER,
                "authorization_endpoint": f"{AS_ISSUER}/authorize",
                "token_endpoint": f"{AS_ISSUER}/token",
            },
        )
    )


@respx.mock
@pytest.mark.asyncio
async def test_consent_exchange_carries_resource_and_caches_bound_token():
    recorded = []
    _route_token_endpoint(recorded)
    _route_discovery()
    client = make_client()
    start = await client.begin_authorization("analyst", "https://vigil.local/callback")
    # RFC 8707 §2: the resource parameter rides the authorization request,
    # so the issued code is already scoped to this connector.
    from urllib.parse import parse_qs, urlsplit

    authorize_params = parse_qs(urlsplit(start.authorization_url).query)
    assert authorize_params["resource"] == [RESOURCE]
    assert authorize_params["code_challenge_method"] == ["S256"]
    assert authorize_params["response_type"] == ["code"]

    token = await client.complete_authorization(
        "analyst", code="stub-code", state=start.state
    )
    assert token.resource == RESOURCE and token.username == "analyst"

    exchange = recorded[0]
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["resource"] == RESOURCE
    assert exchange["client_id"] == "vigil-mcp"
    # PKCE completed: the verifier the flow started with came back.
    assert 43 <= len(exchange["code_verifier"]) <= 128


@respx.mock
@pytest.mark.asyncio
async def test_refresh_grant_carries_resource_and_renews_cache():
    recorded = []
    _route_token_endpoint(recorded)
    _route_discovery()
    store = TokenStore()
    client = make_client(store=store)
    expired = seed_token(store, "analyst", RESOURCE, expires_in=-10)
    old_access = expired.access_token

    refreshed = await client.refresh("analyst")
    assert refreshed is not None and refreshed != old_access

    grant = recorded[0]
    assert grant["grant_type"] == "refresh_token"
    assert grant["refresh_token"] == "rt-1"
    assert grant["resource"] == RESOURCE
    # The new token is in the cache, bound to the same resource.
    assert store.get("analyst", RESOURCE).access_token == refreshed


@respx.mock
@pytest.mark.asyncio
async def test_refresh_without_refresh_token_returns_none():
    store = TokenStore()
    client = make_client(store=store)
    assert await client.refresh("analyst") is None

    seed_token(store, "analyst", RESOURCE, refresh_token=None)
    assert await client.refresh("analyst") is None


# --------------------------------------------------------------------- #
# bearer_token — the dispatch read path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_bearer_token_refuses_when_never_authorized():
    """A headless dispatch cannot pop a browser: no token, a refusal —
    never a static or borrowed credential."""
    client = make_client()
    with pytest.raises(AuthorizationRequired):
        await client.bearer_token("analyst")


@respx.mock
@pytest.mark.asyncio
async def test_bearer_token_renews_expired_before_request():
    """An expired-but-refreshable token renews pre-flight, so a doomed
    request is never sent."""
    recorded = []
    _route_token_endpoint(recorded)
    _route_discovery()
    store = TokenStore()
    client = make_client(store=store)
    seed_token(store, "analyst", RESOURCE, expires_in=-10)

    token = await client.bearer_token("analyst")
    assert recorded[0]["grant_type"] == "refresh_token"
    claims = jwt.decode(token, AS_SECRET, algorithms=["HS256"], audience=RESOURCE)
    assert claims["aud"] == RESOURCE
