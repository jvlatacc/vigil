"""End-to-end bearer-required streamable-HTTP MCP server.

The acceptance core for the native transport: Vigil's MCPClient connects to
a real streamable-HTTP MCP server (uvicorn on loopback) that refuses every
request without a valid bearer token. Unsigned calls fail and nothing
unsigned is ever retried; token-bound calls drive the handshake through
tools/call; an expired token is refreshed inside the next call; a server-
side revocation triggers exactly one serialized refresh and exactly one
retry; and an issuer outage is a typed error, never an unsigned fallback.

The issuer is a mock behind httpx.MockTransport (the token provider's HTTP
leg never leaves the process); the MCP server is the real SDK served
statelessly with JSON responses. Secrets resolve through an in-memory
stand-in for the encrypted store, patched at the same seams the production
code reads.
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import httpx
import pytest
import uvicorn

from core.integrations.mcp import connection_state, oauth
from core.integrations.mcp.client import MCPClient
from core.integrations.mcp.service import MCPService, MCPServer

pytestmark = pytest.mark.unit

ISSUER_URL = "https://idp.e2e.test/v2.0"


class _Issuer:
    """A minimal client-credentials issuer behind httpx.MockTransport.

    Answers RFC 8414 metadata discovery with a token endpoint, mints
    ``at-1, at-2, …`` per token request, and records every request body for
    the assertions on grant type and resource binding. ``fail`` simulates an
    issuer outage; ``revoked`` makes the MCP server refuse a token it was
    shown before.
    """

    def __init__(self) -> None:
        self.token_requests: List[Dict[str, List[str]]] = []
        self.tokens_issued: List[str] = []
        self.revoked: set = set()
        self.fail = False
        self._counter = 0

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            body = request.read().decode()
            self.token_requests.append(
                {key: values for key, values in parse_qs(body).items()}
            )
            if self.fail:
                return httpx.Response(
                    500, json={"error": "temporarily_unavailable"}
                )
            self._counter += 1
            token = f"at-{self._counter}"
            self.tokens_issued.append(token)
            return httpx.Response(
                200,
                json={
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            )
        # Discovery: any well-known path answers with the one thing the
        # provider reads off it — the token endpoint.
        return httpx.Response(
            200, json={"issuer": ISSUER_URL, "token_endpoint": f"{ISSUER_URL}/token"}
        )


class _AuthedMCPServer:
    """A real streamable-HTTP MCP server behind a bearer gate.

    Every http request is logged with the bearer it carried (None when
    unsigned) and refused with a 401 + RFC 9728 challenge unless the token
    is one the issuer issued and has not revoked. Accepted requests reach a
    real MCP server (an ``echo`` tool) served statelessly with JSON
    responses.
    """

    def __init__(self, issuer: _Issuer) -> None:
        from mcp.server.mcpserver import MCPServer as SdkServer

        self.issuer = issuer
        self.requests: List[Optional[str]] = []

        mcp = SdkServer("e2e")

        @mcp.tool()
        def echo(text: str) -> str:
            return f"echo: {text}"

        self._app = mcp.streamable_http_app(json_response=True, stateless_http=True)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        authorization = headers.get(b"authorization")
        bearer = (
            authorization.decode().removeprefix("Bearer ").strip()
            if authorization
            else None
        )
        self.requests.append(bearer)
        if bearer not in self.issuer.tokens_issued or bearer in self.issuer.revoked:
            payload = b'{"error": "invalid_token"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                        (
                            b"www-authenticate",
                            b'Bearer resource_metadata="https://sentinel.e2e.test/.well-known/oauth-protected-resource"',
                        ),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return
        await self._app(scope, receive, send)


class _ServerThread:
    """uvicorn in a daemon thread, bound to an ephemeral loopback port."""

    def __init__(self, app) -> None:
        self.app = app
        config = uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="error", lifespan="on"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "_ServerThread":
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("test MCP server did not start")
            time.sleep(0.05)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        return self

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)


class _Clock:
    """A test clock the provider's expiry math reads."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _configured_provider(monkeypatch, issuer: _Issuer, server_url: str):
    """A provider wired to the mock issuer and a test clock, registered
    under the e2e server's name in the process-wide registry the transport
    reads."""
    clock = _Clock()
    real = oauth.OAuthTokenProvider
    http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handle))

    def factory(config):
        return real(config, clock=clock, http=http)

    monkeypatch.setattr(oauth, "OAuthTokenProvider", factory)
    config = oauth.ServerAuthConfig(
        server_name="e2e",
        server_url=server_url,
        grant="client_credentials",
        client_id="vigil-e2e",
        client_secret_key="MCP_E2E_CLIENT_SECRET",
        issuer_url=ISSUER_URL,
    )
    oauth.token_providers().configure(config)
    return clock


def _e2e_server(url: str) -> MCPServer:
    """The e2e server entry as mcp-config.json parsing would produce it."""
    return MCPServer(
        name="e2e",
        command="",
        args=[],
        cwd="",
        env={},
        required_env_vars=[],
        auth={
            "type": "oauth2",
            "grant": "client_credentials",
            "issuer_url": ISSUER_URL,
            "client_id": "vigil-e2e",
            "client_secret_key": "MCP_E2E_CLIENT_SECRET",
            "server_url": url,
        },
        transport="streamable-http",
        url=url,
    )


class _StubService:
    """What MCPClient needs of MCPService for a single server."""

    def __init__(self, server: MCPServer) -> None:
        self.servers = {server.name: server}

    def is_server_enabled(self, name: str) -> bool:
        return True

    def list_servers(self) -> List[str]:
        return list(self.servers)


@pytest.fixture
def issuer() -> _Issuer:
    return _Issuer()


@pytest.fixture
def secrets_store(monkeypatch):
    """The encrypted-secrets-store seam, in memory: what the auth block's
    ``*_key`` fields name. Patched at the module seams the production code
    reads (oauth at acquire time, connection_state for dormancy)."""
    saved: Dict[str, str] = {"MCP_E2E_CLIENT_SECRET": "shh-e2e"}
    monkeypatch.setattr(
        oauth, "get_secret", lambda key, default=None: saved.get(key, default)
    )
    monkeypatch.setattr(
        oauth,
        "set_secret",
        lambda key, value: saved.__setitem__(key, value),
    )
    monkeypatch.setattr(
        connection_state,
        "get_secret",
        lambda key, default=None: saved.get(key, default),
    )
    return saved


@pytest.fixture(autouse=True)
def fresh_providers():
    oauth.reset_token_providers()
    yield
    oauth.reset_token_providers()


async def test_unsigned_request_is_refused_by_the_server(issuer, secrets_store):
    """The server's gate, probed raw: a request with no bearer gets the 401
    + challenge, and nothing else."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                f"http://127.0.0.1:{srv.port}/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
    assert response.status_code == 401
    assert "Bearer" in response.headers["www-authenticate"]
    assert issuer.tokens_issued == []


async def test_token_bound_calls_drive_the_handshake(issuer, secrets_store, monkeypatch):
    """Connect lists tools through the bearer gate and a tool call executes
    end to end."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        url = f"http://127.0.0.1:{srv.port}/mcp"
        _configured_provider(monkeypatch, issuer, url)
        client = MCPClient(_StubService(_e2e_server(url)))

        assert await client.connect_to_server("e2e", skip_enabled_check=True)
        assert [tool["name"] for tool in client.tools_cache["e2e"]] == ["echo"]

        result = await client.call_tool("e2e", "echo", {"text": "hello"})
        assert result["content"][0]["text"] == "echo: hello"
        # One token request; every request the server saw carried a bearer.
        assert len(issuer.token_requests) == 1
        assert issuer.token_requests[0]["grant_type"] == ["client_credentials"]
        assert all(bearer is not None for bearer in srv.app.requests)


async def test_expired_token_is_refreshed_inside_the_next_call(
    issuer, secrets_store, monkeypatch
):
    """An access token that expires between calls is refreshed from the
    issuer by the next call, without operator action and without surfacing
    an error."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        url = f"http://127.0.0.1:{srv.port}/mcp"
        clock = _configured_provider(monkeypatch, issuer, url)
        client = MCPClient(_StubService(_e2e_server(url)))
        assert await client.connect_to_server("e2e", skip_enabled_check=True)

        clock.now += 400  # past the 300 s expiry of at-1
        result = await client.call_tool("e2e", "echo", {"text": "again"})
        assert result["content"][0]["text"] == "echo: again"
        assert len(issuer.token_requests) == 2
        # The call that landed carried the fresh token.
        assert srv.app.requests[-1] == "at-2"


async def test_server_revocation_gets_one_refresh_and_one_retry(
    issuer, secrets_store, monkeypatch
):
    """A 401 for a token the client still believes in forces one serialized
    refresh and exactly one retry of the original request."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        url = f"http://127.0.0.1:{srv.port}/mcp"
        _configured_provider(monkeypatch, issuer, url)
        client = MCPClient(_StubService(_e2e_server(url)))
        assert await client.connect_to_server("e2e", skip_enabled_check=True)

        issuer.revoked.add("at-1")
        result = await client.call_tool("e2e", "echo", {"text": "once"})
        assert result["content"][0]["text"] == "echo: once"
        # The server saw the revoked token refused, then the refreshed one
        # accepted — two attempts, and the issuer saw exactly one refresh.
        assert srv.app.requests[-2:] == ["at-1", "at-2"]
        assert len(issuer.token_requests) == 2


async def test_issuer_outage_is_typed_and_never_unsigned(
    issuer, secrets_store, monkeypatch
):
    """When the issuer will not answer, an expired-token call fails with the
    typed OAuth error and the MCP server sees nothing at all — no unsigned
    fallback. Recovery is the next call once the issuer is back."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        url = f"http://127.0.0.1:{srv.port}/mcp"
        clock = _configured_provider(monkeypatch, issuer, url)
        client = MCPClient(_StubService(_e2e_server(url)))
        assert await client.connect_to_server("e2e", skip_enabled_check=True)

        issuer.fail = True
        clock.now += 400
        reached_before = len(srv.app.requests)  # the connect handshake
        result = await client.call_tool("e2e", "echo", {"text": "denied"})
        assert result["error"] is True
        # The issuer's error code is what survives into the tool caller's
        # message — never token material.
        assert "temporarily_unavailable" in result["content"][0]["text"]
        # The failed call never reached the MCP server.
        assert len(srv.app.requests) == reached_before

        issuer.fail = False
        result = await client.call_tool("e2e", "echo", {"text": "back"})
        assert result["content"][0]["text"] == "echo: back"
        # The recovered call is exactly one more request, carrying the
        # refreshed token.
        assert len(srv.app.requests) == reached_before + 1
        assert srv.app.requests[-1] == "at-2"


def _write_config(
    tmp_path, monkeypatch, servers: Dict[str, Any], env: Dict[str, str]
) -> MCPService:
    """mcp-config.json served from a temp project root, with the env vars
    its ${VAR} placeholders name."""
    config_path = tmp_path / "mcp-config.json"
    config_path.write_text(
        json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8"
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return MCPService(project_root=tmp_path)


def test_streamable_http_entry_parses_url_transport_and_auth(tmp_path, monkeypatch):
    """A streamable-http entry resolves its placeholders, injects the
    endpoint into the auth block, and leaves the store-key field alone."""
    service = _write_config(
        tmp_path,
        monkeypatch,
        {
            "e2e": {
                "url": "https://${TENANT}.sentinel.example.corp/mcp",
                "transport": "streamable-http",
                "auth": {
                    "type": "oauth2",
                    "grant": "client_credentials",
                    "issuer_url": "https://login.example.corp/${TENANT}/v2.0",
                    "client_id": "${CLIENT_ID}",
                    "client_secret_key": "STORE_KEY_LITERAL",
                    "resource": "https://${TENANT}.sentinel.example.corp",
                },
            }
        },
        env={"TENANT": "acme", "CLIENT_ID": "vigil"},
    )
    server = service.servers["e2e"]
    assert server.transport == "streamable-http"
    assert server.url == "https://acme.sentinel.example.corp/mcp"
    assert server.auth["server_url"] == server.url
    assert server.auth["issuer_url"] == "https://login.example.corp/acme/v2.0"
    assert server.auth["client_id"] == "vigil"
    # The store-key field names a key, never a value: it passes through
    # substitution untouched.
    assert server.auth["client_secret_key"] == "STORE_KEY_LITERAL"
    # A URL server spawns no child process.
    assert server.command == ""
    assert server.required_env_vars == []


def test_stdio_entries_keep_their_shape(tmp_path, monkeypatch):
    """A command-style entry parses exactly as before the transport field
    existed: the stdio path is untouched."""
    service = _write_config(
        tmp_path,
        monkeypatch,
        {
            "legacy": {
                "command": "npx",
                "args": ["-y", "some-server@1.2.3", "--port", "${PORT}"],
                "env": {"TOKEN": "${TOKEN}"},
            }
        },
        env={"PORT": "9999", "TOKEN": "t"},
    )
    server = service.servers["legacy"]
    assert server.transport == "stdio"
    assert server.url is None
    assert server.command.startswith("/") or server.command == "npx"
    # Existing behavior: placeholders in args are scanned as credentials too.
    assert sorted(server.required_env_vars) == ["PORT", "TOKEN"]
    assert server.args == ["-y", "some-server@1.2.3", "--port", "9999"]


async def test_transport_without_url_is_a_typed_config_error(
    issuer, secrets_store, monkeypatch
):
    """A streamable-http entry with no url never reaches a transport — the
    failure is reported on last_errors, naming the config problem."""
    server = _e2e_server("")
    server.url = None
    client = MCPClient(_StubService(server))
    assert not await client.connect_to_server("e2e", skip_enabled_check=True)
    assert "url" in client.last_errors["e2e"].lower()


async def test_missing_oauth_secret_is_dormant(issuer, secrets_store, monkeypatch):
    """An auth block whose client secret does not resolve reads as dormancy
    ("awaiting credentials"), not a connect failure — the same contract as
    the env-var gate — and no transport is opened."""
    with _ServerThread(_AuthedMCPServer(issuer)) as srv:
        url = f"http://127.0.0.1:{srv.port}/mcp"
        server = _e2e_server(url)
        server.auth["client_secret_key"] = "MCP_NEVER_SET"
        client = MCPClient(_StubService(server))
        assert not await client.connect_to_server("e2e", skip_enabled_check=True)
        assert "MCP_NEVER_SET" in client.last_missing_credentials["e2e"]
        # Nothing reached the MCP server and nothing reached the issuer.
        assert srv.app.requests == []
        assert issuer.token_requests == []
