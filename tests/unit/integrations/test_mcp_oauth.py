"""Mock-issuer suite for the MCP OAuth token provider.

Acceptance core for the token-provider work: discovery from the server's
401 challenge (RFC 9728 PRM → RFC 8414/OIDC metadata), RFC 8707 resource
binding on every token request, client-credentials and authorization-code
+PKCE grants, refresh on expiry, rotation with reuse detection, serialized
refresh, and retry-once semantics after a 401 — all against a stateful
in-process issuer (``httpx.MockTransport``), never a live IdP.
"""

import asyncio
import base64
import hashlib
import logging
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from core.integrations.mcp import oauth
from core.integrations.mcp.oauth import (
    GrantRejected,
    NeedsReauth,
    OAuthTokenProvider,
    ProviderState,
    ServerAuthConfig,
    TokenError,
    parse_www_authenticate_challenge,
    pkce_pair,
    well_known_metadata_urls,
)

ISSUER = "https://idp.example"
RESOURCE_SERVER = "https://sentinel.example.corp"
PRM_URL = RESOURCE_SERVER + "/.well-known/oauth-protected-resource"
REDIRECT_URI = "https://vigil.local/oauth/callback"


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class MockIssuer:
    """Stateful in-process IdP + resource server behind one MockTransport.

    Enforces the parts of the profile a real issuer would: the resource
    indicator on every token request, one-time authorization codes bound to
    a PKCE challenge, and refresh tokens that stop working the moment they
    are rotated. Records every request for assertions.
    """

    def __init__(
        self,
        *,
        expires_in: int = 300,
        rotate_on_refresh: bool = True,
        challenge_status: int = 401,
        omit_metadata_param: bool = False,
        reject_client: bool = False,
    ) -> None:
        self.expires_in = expires_in
        self.rotate_on_refresh = rotate_on_refresh
        self.challenge_status = challenge_status
        self.omit_metadata_param = omit_metadata_param
        self.reject_client = reject_client
        self.requests: List[Dict[str, Any]] = []
        self.token_requests: List[Dict[str, str]] = []
        self.active_refresh_tokens: set = set()
        self.retired_refresh_tokens: List[str] = []
        self.access_tokens: List[str] = []
        self.codes: Dict[str, str] = {}  # code → the challenge it was minted for
        self._n = 0
        self._rt_n = 0

    # -- request plumbing -------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append({"method": request.method, "url": url})
        form: Dict[str, str] = {}
        if request.content:
            form = {
                key: values[0]
                for key, values in parse_qs(request.content.decode("utf-8")).items()
            }
        path = urlparse(url).path
        if path == "/token":
            return self._token(form)
        if path == "/.well-known/oauth-protected-resource":
            return httpx.Response(
                200,
                json={
                    "resource": RESOURCE_SERVER,
                    "authorization_servers": [ISSUER],
                },
            )
        if "/.well-known/" in path:
            return httpx.Response(200, json=self._metadata())
        if url.startswith(RESOURCE_SERVER):
            # The resource server's own 401 challenge — RFC 9728's entry point.
            challenge = "Bearer"
            if not self.omit_metadata_param:
                challenge = f'Bearer resource_metadata="{PRM_URL}"'
            return httpx.Response(
                self.challenge_status, headers={"WWW-Authenticate": challenge}
            )
        return httpx.Response(404)

    # -- issuer behavior ---------------------------------------------------

    def _token(self, form: Dict[str, str]) -> httpx.Response:
        self.token_requests.append(dict(form))
        if self.reject_client:
            return httpx.Response(
                400,
                json={
                    "error": "invalid_client",
                    "error_description": "client authentication failed",
                },
            )
        if "resource" not in form:
            # RFC 8707: an issuer bound to a resource refuses token requests
            # that do not name it.
            return httpx.Response(
                400,
                json={
                    "error": "invalid_target",
                    "error_description": "the resource indicator is required",
                },
            )
        grant = form.get("grant_type")
        if grant == "client_credentials":
            return httpx.Response(200, json=self._grant_response())
        if grant == "refresh_token":
            presented = form.get("refresh_token", "")
            if presented not in self.active_refresh_tokens:
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "refresh token is invalid, expired, or rotated",
                    },
                )
            self.retired_refresh_tokens.append(presented)
            self.active_refresh_tokens.discard(presented)
            body = self._grant_response()
            if self.rotate_on_refresh:
                self._rt_n += 1
                body["refresh_token"] = f"rt-{self._rt_n}"
                self.active_refresh_tokens.add(body["refresh_token"])
            return httpx.Response(200, json=body)
        if grant == "authorization_code":
            challenge = self.codes.pop(form.get("code", ""), None)
            if challenge is None or _s256(form.get("code_verifier", "")) != challenge:
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "code or verifier mismatch",
                    },
                )
            self._rt_n += 1
            body = self._grant_response()
            body["refresh_token"] = f"rt-{self._rt_n}"
            self.active_refresh_tokens.add(body["refresh_token"])
            return httpx.Response(200, json=body)
        return httpx.Response(
            400, json={"error": "unsupported_grant_type", "error_description": ""}
        )

    def _grant_response(self) -> Dict[str, Any]:
        self._n += 1
        access = f"at-{self._n}"
        self.access_tokens.append(access)
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "scope": "api://sentinel-mcp/tool.invoke",
        }

    def issue_code(self, challenge: str) -> str:
        code = f"code-{len(self.codes) + 1}"
        self.codes[code] = challenge
        return code

    def _metadata(self) -> Dict[str, Any]:
        return {
            "issuer": ISSUER,
            "token_endpoint": ISSUER + "/token",
            "authorization_endpoint": ISSUER + "/authorize",
            "grant_types_supported": [
                "client_credentials",
                "authorization_code",
                "refresh_token",
            ],
            "code_challenge_methods_supported": ["S256"],
        }


# -- fixtures and helpers -------------------------------------------------


@pytest.fixture
def store(monkeypatch) -> Dict[str, str]:
    """In-memory stand-in for the encrypted secrets store; the provider
    reads and writes secrets only through the two patched names."""
    saved: Dict[str, str] = {"MCP_SENTINEL_CLIENT_SECRET": "shh"}
    monkeypatch.setattr(
        oauth, "get_secret", lambda key, default=None: saved.get(key, default)
    )

    def _set(key: str, value: str) -> bool:
        saved[key] = value
        return True

    monkeypatch.setattr(oauth, "set_secret", _set)
    return saved


@pytest.fixture
def clock():
    class _Clock:
        def __init__(self) -> None:
            self.now = 1_000_000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    return _Clock()


def build_config(**overrides: Any) -> ServerAuthConfig:
    fields: Dict[str, Any] = {
        "server_name": "azure-sentinel",
        "server_url": RESOURCE_SERVER + "/mcp",
        "grant": "client_credentials",
        "client_id": "vigil-mcp",
        "client_secret_key": "MCP_SENTINEL_CLIENT_SECRET",
        "issuer_url": ISSUER,
        "scopes": ("api://sentinel-mcp/tool.invoke",),
        "resource": RESOURCE_SERVER,
    }
    fields.update(overrides)
    return ServerAuthConfig(**fields)


def make_provider(issuer: MockIssuer, clock, **overrides: Any) -> OAuthTokenProvider:
    config = build_config(**overrides)
    http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handler))
    return OAuthTokenProvider(config, clock=clock, http=http)


async def _consented_provider(
    issuer: MockIssuer, clock, store: Dict[str, str]
) -> OAuthTokenProvider:
    """An authorization_code provider past its one interactive consent."""
    provider = make_provider(issuer, clock, grant="authorization_code")
    started = await provider.start_authorization(redirect_uri=REDIRECT_URI)
    query = parse_qs(urlparse(started["authorization_url"]).query)
    code = issuer.issue_code(query["code_challenge"][0])
    await provider.complete_authorization(code=code, state=started["state"])
    return provider


# -- pure helpers ----------------------------------------------------------


class TestPureHelpers:
    def test_parse_challenge_quoted_param(self):
        params = parse_www_authenticate_challenge(
            'Bearer realm="x", resource_metadata="https://a.test/.well-known/x"'
        )
        assert params == {
            "scheme": "bearer",
            "realm": "x",
            "resource_metadata": "https://a.test/.well-known/x",
        }

    def test_parse_challenge_bare_and_case_insensitive(self):
        params = parse_www_authenticate_challenge("BEARER error=insufficient_scope")
        assert params == {"scheme": "bearer", "error": "insufficient_scope"}

    def test_parse_challenge_empty(self):
        assert parse_www_authenticate_challenge("") == {}

    def test_well_known_urls_rfc8414_first(self):
        assert well_known_metadata_urls("https://idp.test") == [
            "https://idp.test/.well-known/oauth-authorization-server",
            "https://idp.test/.well-known/openid-configuration",
        ]

    def test_well_known_urls_path_preserving(self):
        urls = well_known_metadata_urls("https://login.microsoftonline.com/tenant/v2.0")
        assert urls[0] == (
            "https://login.microsoftonline.com"
            "/.well-known/oauth-authorization-server/tenant/v2.0"
        )
        assert urls[1] == (
            "https://login.microsoftonline.com/tenant/v2.0"
            "/.well-known/openid-configuration"
        )

    def test_pkce_pair_is_s256(self):
        verifier, challenge = pkce_pair()
        assert 43 <= len(verifier) <= 128
        assert _s256(verifier) == challenge


class TestServerAuthConfig:
    def test_from_server_entry_parses_auth_block(self):
        config = ServerAuthConfig.from_server_entry(
            "azure-sentinel",
            {
                "type": "oauth2",
                "grant": "client_credentials",
                "issuer_url": "https://login.microsoftonline.com/tenant/v2.0",
                "client_id": "vigil-mcp",
                "client_secret_key": "MCP_SENTINEL_CLIENT_SECRET",
                "server_url": RESOURCE_SERVER + "/mcp",
                "scopes": ["api://sentinel-mcp/tool.invoke"],
                "resource": RESOURCE_SERVER,
            },
        )
        assert config.grant == "client_credentials"
        assert config.scopes == ("api://sentinel-mcp/tool.invoke",)
        assert config.resource_url == RESOURCE_SERVER
        assert config.refresh_key == "MCP_OAUTH_REFRESH_AZURE_SENTINEL"

    def test_client_credentials_requires_secret_key(self):
        with pytest.raises(TokenError, match="client_secret_key"):
            ServerAuthConfig(
                server_name="x",
                server_url=RESOURCE_SERVER,
                grant="client_credentials",
                client_id="c",
            )

    def test_unsupported_grant_refused(self):
        with pytest.raises(TokenError, match="unsupported OAuth grant"):
            ServerAuthConfig.from_server_entry(
                "x",
                {
                    "server_url": RESOURCE_SERVER,
                    "grant": "password",
                    "client_id": "c",
                    "client_secret_key": "K",
                },
            )

    def test_unknown_type_refused(self):
        with pytest.raises(TokenError, match="oauth2"):
            ServerAuthConfig.from_server_entry(
                "x", {"server_url": RESOURCE_SERVER, "type": "mtls", "client_id": "c"}
            )


# -- discovery -------------------------------------------------------------


class TestDiscovery:
    async def test_challenge_driven_discovery_end_to_end(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock, issuer_url=None)
        token = await provider.bearer()
        assert token == "at-1"
        visited = [r["url"] for r in issuer.requests]
        assert visited[0] == RESOURCE_SERVER + "/mcp"  # the 401 probe
        assert PRM_URL in visited  # the RFC 9728 document
        assert ISSUER + "/.well-known/oauth-authorization-server" in visited
        assert provider.state is ProviderState.CONNECTED

    async def test_metadata_cached_across_calls(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock)
        await provider.bearer()
        await provider.bearer()
        metadata_fetches = [r for r in issuer.requests if "/.well-known/" in r["url"]]
        assert len(metadata_fetches) == 1

    async def test_server_not_challenging_is_an_error(self, store, clock):
        issuer = MockIssuer(challenge_status=200)
        provider = make_provider(issuer, clock, issuer_url=None)
        with pytest.raises(TokenError, match="401"):
            await provider.bearer()
        assert provider.state is ProviderState.ERROR

    async def test_prm_default_location_fallback(self, store, clock):
        # A challenge with no resource_metadata param falls back to RFC 9728's
        # default location on the resource server.
        issuer = MockIssuer(omit_metadata_param=True)
        provider = make_provider(issuer, clock, issuer_url=None)
        assert await provider.bearer() == "at-1"
        assert PRM_URL in [r["url"] for r in issuer.requests]


# -- client_credentials ----------------------------------------------------


class TestClientCredentials:
    async def test_bearer_acquires_and_binds_resource(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock)
        token = await provider.bearer()
        assert token == "at-1"
        sent = issuer.token_requests[0]
        assert sent["grant_type"] == "client_credentials"
        assert sent["client_id"] == "vigil-mcp"
        assert sent["client_secret"] == "shh"
        assert sent["resource"] == RESOURCE_SERVER  # RFC 8707
        assert sent["scope"] == "api://sentinel-mcp/tool.invoke"
        # A configured issuer skips the challenge probe entirely.
        assert all(r["url"].startswith(ISSUER) for r in issuer.requests)

    async def test_cached_token_not_reacquired(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock)
        assert await provider.bearer() == await provider.bearer()
        assert len(issuer.token_requests) == 1

    async def test_missing_client_secret_names_key_and_stays_safe(self, store, clock):
        issuer = MockIssuer()
        store.pop("MCP_SENTINEL_CLIENT_SECRET")
        provider = make_provider(issuer, clock)
        with pytest.raises(TokenError, match="MCP_SENTINEL_CLIENT_SECRET"):
            await provider.bearer()
        assert provider.state is ProviderState.ERROR
        # The error names the key, never a value.
        assert "shh" not in str(provider.last_error)

    async def test_invalid_client_is_not_reauth(self, store, clock):
        issuer = MockIssuer(reject_client=True)
        provider = make_provider(issuer, clock)
        with pytest.raises(TokenError) as excinfo:
            await provider.bearer()
        assert not isinstance(excinfo.value, NeedsReauth)
        assert isinstance(excinfo.value, GrantRejected)
        assert excinfo.value.oauth_error == "invalid_client"
        assert provider.state is ProviderState.ERROR


# -- authorization_code + PKCE ---------------------------------------------


class TestAuthorizationCode:
    async def test_consent_flow_binds_pkce_and_resource(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock, grant="authorization_code")
        assert provider.state is ProviderState.NEEDS_CONSENT
        started = await provider.start_authorization(redirect_uri=REDIRECT_URI)
        query = parse_qs(urlparse(started["authorization_url"]).query)
        assert query["response_type"] == ["code"]
        assert query["client_id"] == ["vigil-mcp"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["resource"] == [RESOURCE_SERVER]  # RFC 8707, front channel
        challenge = query["code_challenge"][0]
        code = issuer.issue_code(challenge)
        await provider.complete_authorization(code=code, state=started["state"])
        exchange = issuer.token_requests[0]
        assert exchange["grant_type"] == "authorization_code"
        assert exchange["resource"] == RESOURCE_SERVER
        assert _s256(exchange["code_verifier"]) == challenge  # PKCE, verified
        assert store[provider.config.refresh_key].startswith("rt-")
        assert provider.state is ProviderState.CONNECTED

    async def test_state_mismatch_refuses_exchange(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock, grant="authorization_code")
        await provider.start_authorization(redirect_uri=REDIRECT_URI)
        with pytest.raises(TokenError, match="state mismatch"):
            await provider.complete_authorization(code="code-1", state="forged")
        assert issuer.token_requests == []

    async def test_refresh_without_consent_asks_for_it(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock, grant="authorization_code")
        with pytest.raises(NeedsReauth, match="consent"):
            await provider.bearer()
        assert provider.state is ProviderState.NEEDS_CONSENT


# -- refresh, rotation, reuse ----------------------------------------------


class TestRefreshAndRotation:
    async def test_refresh_on_expiry(self, store, clock):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        first = await provider.bearer()
        clock.advance(400)  # past expires_in minus the skew
        second = await provider.bearer()
        assert second != first
        sent = issuer.token_requests[-1]
        assert sent["grant_type"] == "refresh_token"
        assert sent["resource"] == RESOURCE_SERVER

    async def test_rotated_refresh_token_replaces_stored_one(self, store, clock):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        key = provider.config.refresh_key
        original = store[key]
        clock.advance(400)
        await provider.bearer()
        rotated = store[key]
        assert rotated != original
        assert rotated in issuer.active_refresh_tokens
        assert original in issuer.retired_refresh_tokens
        assert provider._rotated_out == original

    async def test_reused_refresh_token_is_reauth(self, store, clock, caplog):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        key = provider.config.refresh_key
        original = store[key]
        clock.advance(400)
        await provider.bearer()  # rotates: original is now spent
        store[key] = original  # a second consumer rewinds the store
        clock.advance(400)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(NeedsReauth):
                await provider.bearer()
        assert any("reuse" in record.message.lower() for record in caplog.records)
        assert provider.state is ProviderState.NEEDS_CONSENT

    async def test_expired_refresh_token_is_reauth_without_reuse_alarm(
        self, store, clock, caplog
    ):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        store[provider.config.refresh_key] = "rt-revoked-elsewhere"
        clock.advance(400)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(NeedsReauth):
                await provider.bearer()
        assert not any("reuse" in record.message.lower() for record in caplog.records)


# -- serialization and retry-once -------------------------------------------


class TestSerialization:
    async def test_concurrent_bearers_refresh_once(self, store, clock):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        clock.advance(400)
        results = await asyncio.gather(*[provider.bearer() for _ in range(10)])
        assert len(set(results)) == 1
        refreshes = [
            r for r in issuer.token_requests if r["grant_type"] == "refresh_token"
        ]
        assert len(refreshes) == 1

    async def test_on_unauthorized_forces_exactly_one_refresh(self, store, clock):
        issuer = MockIssuer()
        provider = make_provider(issuer, clock)
        stale = await provider.bearer()
        fresh = await provider.on_unauthorized()  # cached token was still fresh
        assert fresh != stale
        assert len(issuer.token_requests) == 2
        assert await provider.bearer() == fresh  # the retry carries the new one
        assert len(issuer.token_requests) == 2  # and no third request fired

    async def test_on_unauthorized_after_invalid_grant_raises_reauth(
        self, store, clock
    ):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        store[provider.config.refresh_key] = "rt-never-issued"
        with pytest.raises(NeedsReauth):
            await provider.on_unauthorized()
        assert provider.state is ProviderState.NEEDS_CONSENT


# -- hygiene -----------------------------------------------------------------


class TestLogHygiene:
    async def test_no_token_material_in_logs(self, store, clock, caplog):
        issuer = MockIssuer()
        provider = await _consented_provider(issuer, clock, store)
        clock.advance(400)
        await provider.bearer()
        store[provider.config.refresh_key] = "rt-revoked"
        clock.advance(400)
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(NeedsReauth):
                await provider.bearer()
        for token in issuer.access_tokens + issuer.retired_refresh_tokens:
            assert token not in caplog.text


# -- registry ----------------------------------------------------------------


class TestRegistry:
    async def test_registry_unknown_server(self):
        registry = oauth.TokenProviderRegistry()
        with pytest.raises(TokenError, match="no OAuth configuration"):
            await registry.bearer("nope")

    async def test_registry_bears_the_server_keyed_protocol(self, store, clock):
        issuer = MockIssuer()

        def factory(config: ServerAuthConfig) -> OAuthTokenProvider:
            http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handler))
            return OAuthTokenProvider(config, clock=clock, http=http)

        registry = oauth.TokenProviderRegistry(provider_factory=factory)
        registry.configure(build_config())
        assert await registry.bearer("azure-sentinel") == "at-1"
        assert await registry.on_unauthorized("azure-sentinel") == "at-2"
        assert registry.provider_for("azure-sentinel") is not None
        registry.forget("azure-sentinel")
        with pytest.raises(TokenError, match="no OAuth configuration"):
            await registry.bearer("azure-sentinel")
