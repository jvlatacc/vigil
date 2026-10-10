"""End-to-end: per-user OAuth dispatch to HTTP-capable MCP connectors.

Two halves, both stubbed at the protocol edge:

- A stub **authorization server** (respx over httpx, the identity client's
  stack) that mints aud-bound access tokens and records every token
  request's grant and resource parameter.
- A stub **MCP resource server** (httpx2.MockTransport, the SDK's
  transport) that refuses every token whose audience is not exactly its
  own canonical URI — the RFC 8707 binding, asserted where a real
  connector would assert it — and serves the Streamable HTTP handshake.

Through them: dispatch under a signed-in user presents a token minted
for that user and that server; a revoked token triggers one silent
refresh; a token minted for another server never leaves the building.
"""

import json
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx2
import jwt
import pytest
import respx
from httpx import Response

from core.integrations.mcp import client as client_module
from core.integrations.mcp.client import MCPClient
from core.integrations.mcp.identity import (
    IdentityError,
    InMemoryAuthorizationStateStore,
    ServerOAuthClient,
    TokenStore,
    canonical_resource,
)
from core.integrations.mcp.service import MCPServer, OAuthConnectorConfig
from core.integrations.mcp.surface import acting_as

AS_ISSUER = "https://as.example.com"
AS_SECRET = "test-as-secret-that-is-long-enough-32!"
URL_A = "https://connector-a.example/mcp"
URL_B = "https://connector-b.example/mcp"
CALLBACK = "https://vigil.local/oauth/callback"


def mint(resource: str, serial: int, ttl: int = 300) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": AS_ISSUER,
            "aud": resource,
            "sub": "analyst",
            "iat": now,
            "exp": now + ttl,
            "jti": str(serial),
        },
        AS_SECRET,
        algorithm="HS256",
    )


class StubAuthorizationServer:
    """RFC 8414/9728 documents plus a token endpoint that records grants."""

    def __init__(self):
        self.token_requests = []
        self._serial = 0

    def route(self):
        for url in (URL_A, URL_B):
            origin = urlsplit(url)
            respx.get(
                f"{origin.scheme}://{origin.netloc}/.well-known/oauth-protected-resource/mcp"
            ).mock(
                return_value=Response(
                    200,
                    json={
                        "resource": canonical_resource(url),
                        "authorization_servers": [AS_ISSUER],
                        "scopes_supported": ["mcp:tools"],
                    },
                )
            )
        respx.get(f"{AS_ISSUER}/.well-known/oauth-authorization-server").mock(
            return_value=Response(
                200,
                json={
                    "issuer": AS_ISSUER,
                    "authorization_endpoint": f"{AS_ISSUER}/authorize",
                    "token_endpoint": f"{AS_ISSUER}/token",
                },
            )
        )

        def token_handler(request):
            from urllib.parse import parse_qs

            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            self._serial += 1
            body = {
                "access_token": mint(form["resource"], self._serial),
                "token_type": "Bearer",
                "expires_in": 300,
            }
            if form["grant_type"] == "authorization_code":
                body["refresh_token"] = f"rt-{self._serial}"
            return Response(200, json=body)

        respx.post(f"{AS_ISSUER}/token").mock(side_effect=token_handler)


class StubResourceServer:
    """An MCP Streamable HTTP server that enforces the audience binding."""

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.resource = canonical_resource(url)
        self.requests = []  # (method, aud, serial, accepted)
        self.revoked = set()
        self._session = "sess-1"

    def _bearer(self, request):
        header = request.headers.get("authorization", "")
        return header[7:] if header.startswith("Bearer ") else None

    def _decide(self, request):
        token = self._bearer(request)
        if token is None:
            self.requests.append((request.method, None, None, False))
            return False
        try:
            claims = jwt.decode(
                token, AS_SECRET, algorithms=["HS256"], options={"verify_aud": False}
            )
        except jwt.PyJWTError:
            self.requests.append((request.method, None, None, False))
            return False
        serial = claims.get("jti")
        # The RFC 8707 check a real connector performs: this token was
        # minted for THIS resource, or it is not accepted here.
        accepted = claims.get("aud") == self.resource and token not in self.revoked
        self.requests.append((request.method, claims.get("aud"), serial, accepted))
        return accepted

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        if not self._decide(request):
            return httpx2.Response(
                401,
                headers={"WWW-Authenticate": 'Bearer resource_metadata="x"'},
            )
        body = json.loads(request.content)
        method = body.get("method", "")
        if method == "initialize":
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": "0.0.1"},
            }
            return httpx2.Response(
                200,
                json={"jsonrpc": "2.0", "id": body.get("id"), "result": result},
                headers={"Mcp-Session-Id": self._session},
            )
        if method.startswith("notifications/"):
            return httpx2.Response(202)
        if method == "tools/list":
            # The SDK's call_tool validates output schemas by listing tools
            # first; a real server answers with the tool catalog.
            return httpx2.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": f"{self.name}_query",
                                "description": f"{self.name} query tool",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                },
                            }
                        ]
                    },
                },
            )
        result = {
            "content": [{"type": "text", "text": f"ok from {self.name}"}],
            "isError": False,
        }
        return httpx2.Response(
            200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": result}
        )


def make_http_server(name: str, url: str) -> MCPServer:
    return MCPServer(
        name=name,
        command=None,  # unused on the http transport
        args=[],
        cwd="",
        env={},
        http_url=url,
        oauth=OAuthConnectorConfig(client_id="vigil-mcp"),
    )


def make_client(*servers: MCPServer) -> MCPClient:
    """A dispatchable MCPClient over stub service config."""
    directory = {s.name: s for s in servers}
    service = SimpleNamespace(
        servers=directory,
        is_server_enabled=lambda name: True,
        list_servers=lambda: list(directory),
    )
    return MCPClient(mcp_service=service)


def wire_transports(monkeypatch, *resource_servers):
    """Route OAuth to the stub AS and MCP to the stub resource servers."""
    as_stub = StubAuthorizationServer()
    as_stub.route()
    handlers = {rs.resource: rs for rs in resource_servers}

    def factory_for(resource):
        return lambda: httpx2.AsyncClient(
            transport=httpx2.MockTransport(handlers[resource].handler)
        )

    # The SDK's Streamable HTTP transport builds its httpx2 client through
    # the session's client_factory; bind each session to its own resource
    # server via the URL it was constructed with.
    original_init = client_module.HttpServerSession.__init__

    def patched_init(self, server_name, mcp_url, bearer_token, client_factory=None):
        resource = canonical_resource(mcp_url)
        original_init(
            self,
            server_name,
            mcp_url,
            bearer_token,
            client_factory=factory_for(resource),
        )

    monkeypatch.setattr(client_module.HttpServerSession, "__init__", patched_init)
    return as_stub


def use_memory_state(oauth: ServerOAuthClient) -> ServerOAuthClient:
    oauth._state_store = InMemoryAuthorizationStateStore()
    return oauth


async def consent(oauth: ServerOAuthClient, username: str = "analyst") -> None:
    start = await oauth.begin_authorization(username, CALLBACK)
    await oauth.complete_authorization(username, code="stub-code", state=start.state)


def oauth_for(client: MCPClient, server: MCPServer) -> ServerOAuthClient:
    """The client's per-server OAuth client, with in-memory state."""
    return use_memory_state(client._oauth_client_for(server))


# --------------------------------------------------------------------- #
# Dispatch: audience binding end to end
# --------------------------------------------------------------------- #


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_presents_a_token_minted_for_that_server(monkeypatch):
    rs = StubResourceServer("alpha", URL_A)
    server = make_http_server("alpha", URL_A)
    as_stub = wire_transports(monkeypatch, rs)
    client = make_client(server)
    oauth = oauth_for(client, server)
    await consent(oauth)

    with acting_as("analyst"):
        result = await client.call_tool("alpha", "alpha_query", {"q": "x"})

    assert not result.get("error")
    assert "ok from alpha" in result["content"][0]["text"]
    # The token endpoint saw an authorization-code grant bound to alpha.
    assert as_stub.token_requests[0]["grant_type"] == "authorization_code"
    assert as_stub.token_requests[0]["resource"] == canonical_resource(URL_A)
    # Every request the connector accepted carried alpha's own audience.
    assert rs.requests and all(
        aud == rs.resource for _, aud, _, ok in rs.requests if ok
    )
    assert all(ok for *_, ok in rs.requests)


@respx.mock
@pytest.mark.asyncio
async def test_401_at_connect_refreshes_once_then_reacquires(monkeypatch):
    rs = StubResourceServer("alpha", URL_A)
    server = make_http_server("alpha", URL_A)
    as_stub = wire_transports(monkeypatch, rs)
    client = make_client(server)
    oauth = oauth_for(client, server)
    await consent(oauth)
    first_token = oauth.cached_token("analyst").access_token
    rs.revoked.add(first_token)

    with acting_as("analyst"):
        result = await client.call_tool("alpha", "alpha_query", {})

    assert not result.get("error")
    grants = [f["grant_type"] for f in as_stub.token_requests]
    assert grants == ["authorization_code", "refresh_token"]
    assert as_stub.token_requests[1]["resource"] == canonical_resource(URL_A)
    assert as_stub.token_requests[1]["refresh_token"]
    # The refused first attempt is on the record, then only bound tokens.
    assert any(not ok for *_, ok in rs.requests)
    assert all(aud == rs.resource for _, aud, _, ok in rs.requests if ok)


@respx.mock
@pytest.mark.asyncio
async def test_mid_session_401_rebuilds_session_with_refreshed_token(monkeypatch):
    rs = StubResourceServer("alpha", URL_A)
    server = make_http_server("alpha", URL_A)
    as_stub = wire_transports(monkeypatch, rs)
    client = make_client(server)
    oauth = oauth_for(client, server)
    await consent(oauth)
    v1 = oauth.cached_token("analyst").access_token

    with acting_as("analyst"):
        first = await client.call_tool("alpha", "alpha_query", {})
    assert not first.get("error")

    # The connector revokes the token mid-session.
    rs.revoked.add(v1)
    with acting_as("analyst"):
        result = await client.call_tool("alpha", "alpha_query", {})

    assert not result.get("error")
    grants = [f["grant_type"] for f in as_stub.token_requests]
    assert grants == ["authorization_code", "refresh_token"]
    # The refused session was discarded; the live one is challenge-free.
    assert not client.http_sessions[("alpha", "analyst")].unauthorized


@respx.mock
@pytest.mark.asyncio
async def test_token_minted_for_server_a_is_never_sent_to_server_b(monkeypatch):
    rs_a = StubResourceServer("alpha", URL_A)
    rs_b = StubResourceServer("beta", URL_B)
    server_a = make_http_server("alpha", URL_A)
    server_b = make_http_server("beta", URL_B)
    wire_transports(monkeypatch, rs_a, rs_b)
    client = make_client(server_a, server_b)
    await consent(oauth_for(client, server_a))  # only alpha is authorized

    with acting_as("analyst"):
        refused = await client.call_tool("beta", "beta_query", {})

    # Fail closed: beta never saw a byte, and the error says why.
    assert refused.get("error") is True
    assert "not authorized" in refused["content"][0]["text"]
    assert rs_b.requests == []
    # And alpha's consented dispatches never carried a foreign audience.
    with acting_as("analyst"):
        first = await client.call_tool("alpha", "alpha_query", {})
    assert not first.get("error")
    assert all(aud == rs_a.resource for _, aud, _, _ in rs_a.requests)


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_without_a_signed_in_user_never_reaches_the_connector(
    monkeypatch,
):
    rs = StubResourceServer("alpha", URL_A)
    wire_transports(monkeypatch, rs)
    client = make_client(make_http_server("alpha", URL_A))

    result = await client.call_tool("alpha", "alpha_query", {})

    assert result.get("error") is True
    assert "signed-in user" in result["content"][0]["text"]
    assert rs.requests == []


@respx.mock
@pytest.mark.asyncio
async def test_consent_without_identity_is_refused(monkeypatch):
    rs = StubResourceServer("alpha", URL_A)
    wire_transports(monkeypatch, rs)
    server = make_http_server("alpha", URL_A)
    client = make_client(server)
    oauth = oauth_for(client, server)

    with pytest.raises(IdentityError, match="authenticated user"):
        await oauth.begin_authorization("", CALLBACK)


# --------------------------------------------------------------------- #
# The passthrough guard, at the store boundary
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_store_refuses_to_hand_a_token_to_another_server():
    """Unit-level: the guard refuses a token whose JWT audience names
    another resource, even when the cache slot agrees with the request —
    the slot is data, the audience inside the token is the contract."""
    store = TokenStore()
    client = ServerOAuthClient(
        server_name="beta",
        http_url=URL_B,
        client_id="vigil-mcp",
        store=store,
        state_store=InMemoryAuthorizationStateStore(),
    )
    from core.integrations.mcp.identity import CachedToken

    # Corruption simulation: alpha's token filed in beta's cache slot —
    # the resource FIELD names beta (so put() accepts it), the JWT inside
    # is minted for alpha (what a resource server would enforce).
    forged = CachedToken(
        access_token=mint(canonical_resource(URL_A), 99),
        expires_at=time.time() + 300,
        refresh_token="rt-x",
        resource=canonical_resource(URL_B),
        username="analyst",
    )
    store.put(forged)
    with pytest.raises(Exception, match="passthrough"):
        await client.bearer_token("analyst")


# --------------------------------------------------------------------- #
# Config parsing
# --------------------------------------------------------------------- #


def _service_for_config():
    from pathlib import Path

    from core.integrations.mcp.service import MCPService

    service = MCPService.__new__(MCPService)
    service.project_root = Path("/tmp/vigil-test")
    return service


def test_http_connector_config_parses_oauth_fields():
    svc = _service_for_config()
    cfg, reason = svc._http_server_config(
        "alpha",
        {
            "http": {
                "url": URL_A,
                "auth": {
                    "type": "oauth",
                    "client_id": "vigil-mcp",
                    "client_secret_env": "ALPHA_CLIENT_SECRET",
                    "scopes": ["mcp:tools"],
                },
            }
        },
    )
    assert reason is None
    assert cfg["http_url"] == URL_A
    assert cfg["oauth"].client_id == "vigil-mcp"
    assert cfg["oauth"].client_secret_env == "ALPHA_CLIENT_SECRET"
    assert cfg["oauth"].scopes == ("mcp:tools",)
    assert "ALPHA_CLIENT_SECRET" in cfg["required_env_vars"]


def test_http_connector_url_substitutes_env(monkeypatch):
    monkeypatch.setenv("TEST_CONNECTOR_URL", URL_A)
    svc = _service_for_config()
    cfg, reason = svc._http_server_config(
        "alpha",
        {
            "http": {
                "url": "${TEST_CONNECTOR_URL}",
                "auth": {"type": "oauth", "client_id": "c"},
            }
        },
    )
    assert reason is None
    assert cfg["http_url"] == URL_A


def test_malformed_http_entries_are_skipped_with_reason():
    svc = _service_for_config()
    bad_cases = {
        "no url": {"http": {"auth": {"type": "oauth", "client_id": "c"}}},
        "bad auth": {"http": {"url": URL_A, "auth": {"type": "api-key"}}},
        "no auth": {"http": {"url": URL_A}},
        "bad secret env": {
            "http": {
                "url": URL_A,
                "auth": {"type": "oauth", "client_id": "c", "client_secret_env": "A B"},
            }
        },
    }
    for label, entry in bad_cases.items():
        cfg, reason = svc._http_server_config("alpha", entry)
        assert cfg is None and reason, label


def test_stdio_entries_do_not_take_the_http_path():
    svc = _service_for_config()
    cfg, reason = svc._http_server_config(
        "alpha", {"command": "python", "args": ["-m", "x"]}
    )
    assert cfg is None and reason is None


def test_http_server_flag_reflects_transport():
    http_server = make_http_server("alpha", URL_A)
    assert http_server.is_http
    stdio_server = MCPServer(name="std", command="python", args=[], cwd="", env={})
    assert not stdio_server.is_http
