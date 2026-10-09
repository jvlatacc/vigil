"""The connection-state machine: resolution, sanitization, persistence.

What is under test is the rules -- which of the five operator states a
server is in given live provider knowledge, last-known storage, and the
auth block itself; that an error string entering ``oauth_connections``
cannot carry token material; and that a database which cannot answer never
breaks a status poll. SQLite, per the ``mcp_credentials`` precedent: the
rules are not dialect-specific.
"""

from typing import Dict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from core.integrations.mcp import connection_state as cs
from core.integrations.mcp import oauth
from core.integrations.mcp.connection_state import ConnectionState
from core.integrations.mcp.oauth import OAuthTokenProvider, ProviderState, ServerAuthConfig
from core.storage.models import OAuthConnection
from core.storage.models.mcp_oauth import VALID_CONNECTION_STATUSES


# `oauth_connections` carries a JSONB column SQLite cannot render. Registered
# for the SQLite dialect only, so nothing that speaks to Postgres is affected.
@compiles(JSONB, "sqlite")
def _jsonb_is_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


SENTINEL_AUTH = {
    "type": "oauth2",
    "grant": "authorization_code",
    "server_url": "https://sentinel.example.corp/mcp",
    "issuer_url": "https://idp.example",
    "client_id": "vigil-client",
}


@pytest.fixture(autouse=True)
def _fresh_provider_registry():
    """One test, one token-provider registry: suites never share providers."""
    oauth.reset_token_providers()
    yield
    oauth.reset_token_providers()


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    from core.storage.models.base import Base

    Base.metadata.create_all(engine, tables=[OAuthConnection.__table__])
    maker = sessionmaker(bind=engine)
    s = maker()
    yield s
    s.close()


# -- the vocabulary is one contract ------------------------------------------


def test_the_enum_and_the_stored_vocabulary_agree():
    assert {state.value for state in ConnectionState} == set(
        VALID_CONNECTION_STATUSES
    )


# -- sanitize_error: no token material survives ------------------------------


def test_a_jwt_in_an_error_is_redacted():
    message = (
        "token request failed: got eyJhbGciOiJSUzI1NiJ9."
        "eyJzdWIiOiJhIn0.sig_value_here as the answer"
    )
    cleaned = cs.sanitize_error(message)
    assert "eyJ" not in cleaned
    assert "<redacted>" in cleaned
    assert "token request failed" in cleaned


def test_a_bearer_header_is_redacted():
    cleaned = cs.sanitize_error(
        "upstream answered 401 for Bearer abcdefgh1234567890"
    )
    assert "abcdefgh1234567890" not in cleaned
    assert "Bearer <redacted>" in cleaned


def test_token_shaped_query_parameters_are_redacted():
    cleaned = cs.sanitize_error(
        "redirect https://ui/callback?code=abc123def456&state=ok-1"
    )
    assert "abc123def456" not in cleaned
    assert "state=ok-1" in cleaned  # an unnamed, harmless param stays


def test_plain_prose_survives_unchanged():
    text = "could not discover OAuth metadata for issuer 'https://idp.example'"
    assert cs.sanitize_error(text) == text


def test_an_error_is_capped():
    assert len(cs.sanitize_error("x" * 5000)) <= 504  # 500 + the ellipsis


# -- resolve_connection_state: the precedence is the point --------------------


def test_disabled_beats_everything():
    assert cs.resolve_connection_state(
        enabled=False,
        grant="client_credentials",
        provider_state=ProviderState.CONNECTED,
        stored_status="connected",
    ) is ConnectionState.DISABLED


def test_missing_secrets_are_dormant_over_a_live_provider():
    assert cs.resolve_connection_state(
        enabled=True,
        grant="client_credentials",
        missing_secrets=["MCP_SENTINEL_CLIENT_SECRET"],
        provider_state=ProviderState.CONNECTED,
    ) is ConnectionState.DORMANT


def test_a_live_error_is_the_freshest_truth():
    assert cs.resolve_connection_state(
        enabled=True,
        grant="client_credentials",
        provider_state=ProviderState.ERROR,
        stored_status="connected",
    ) is ConnectionState.ERROR


def test_needs_consent_from_the_provider():
    assert cs.resolve_connection_state(
        enabled=True,
        grant="authorization_code",
        provider_state=ProviderState.NEEDS_CONSENT,
    ) is ConnectionState.NEEDS_CONSENT


def test_a_stored_error_is_sticky_even_with_a_refresh_token():
    # The issuer refused the grant; a refresh token still in the store does
    # not make the connection refreshable. The issuer is the judge.
    assert cs.resolve_connection_state(
        enabled=True,
        grant="authorization_code",
        stored_status="error",
        refresh_token_present=True,
    ) is ConnectionState.ERROR


def test_a_refreshable_token_is_connected():
    assert cs.resolve_connection_state(
        enabled=True,
        grant="authorization_code",
        refresh_token_present=True,
    ) is ConnectionState.CONNECTED


def test_pending_defers_to_the_stored_row():
    # PENDING is "nothing attempted this process" -- a restart. The row is
    # what is known; the access token died with the old process.
    assert cs.resolve_connection_state(
        enabled=True,
        grant="client_credentials",
        provider_state=ProviderState.PENDING,
        stored_status="connected",
    ) is ConnectionState.CONNECTED


def test_an_unknown_stored_status_is_ignored():
    assert cs.resolve_connection_state(
        enabled=True,
        grant="client_credentials",
        stored_status="garbage",
    ) is ConnectionState.DORMANT


def test_fresh_code_grant_with_no_knowledge_needs_consent():
    assert cs.resolve_connection_state(
        enabled=True, grant="authorization_code"
    ) is ConnectionState.NEEDS_CONSENT


# -- sync: the row is the memory, and it costs nothing when nothing changed ---


def _config(grant: str = "authorization_code") -> ServerAuthConfig:
    auth = dict(SENTINEL_AUTH)
    auth["grant"] = grant
    if grant == "client_credentials":
        auth["client_secret_key"] = "MCP_SENTINEL_CLIENT_SECRET"
    return ServerAuthConfig.from_server_entry("sentinel", auth)


def _provider(config: ServerAuthConfig) -> OAuthTokenProvider:
    return oauth.token_providers().configure(config)


def test_first_sync_writes_the_row(session):
    provider = _provider(_config())
    state, last_error, fields = cs.sync_connection_state(
        _config(), enabled=True, provider=provider, session=session
    )

    assert state is ConnectionState.NEEDS_CONSENT
    assert last_error is None
    row = session.query(OAuthConnection).filter_by(server_name="sentinel").one()
    assert row.status == "needs_consent"
    assert row.grant == "authorization_code"
    assert row.client_id == "vigil-client"
    assert row.last_refreshed_at is None


def test_a_second_identical_sync_writes_nothing(session):
    config = _config()
    provider = _provider(config)
    cs.sync_connection_state(config, enabled=True, provider=provider, session=session)
    before = (
        session.query(OAuthConnection).filter_by(server_name="sentinel").one().updated_at
    )
    cs.sync_connection_state(config, enabled=True, provider=provider, session=session)
    after = (
        session.query(OAuthConnection).filter_by(server_name="sentinel").one().updated_at
    )
    assert before == after


def test_connecting_stamps_last_refreshed_and_clears_the_error(session):
    config = _config()
    provider = _provider(config)
    cs.sync_connection_state(
        config,
        enabled=True,
        provider=provider,
        fresh_error="earlier attempt failed",
        session=session,
    )
    provider.state = ProviderState.CONNECTED
    state, last_error, fields = cs.sync_connection_state(
        config, enabled=True, provider=provider, session=session
    )

    assert state is ConnectionState.CONNECTED
    assert last_error is None
    row = session.query(OAuthConnection).filter_by(server_name="sentinel").one()
    assert row.status == "connected"
    assert row.last_error is None
    assert row.last_refreshed_at is not None
    assert fields["last_refreshed_at"] is not None


def test_a_fresh_error_is_sanitized_on_the_way_in(session):
    config = _config()
    provider = _provider(config)
    provider.state = ProviderState.ERROR
    state, last_error, _fields = cs.sync_connection_state(
        config,
        enabled=True,
        provider=provider,
        fresh_error="got Bearer supersecrettokenvalue in the challenge",
        session=session,
    )

    assert state is ConnectionState.ERROR
    assert last_error == "got Bearer <redacted> in the challenge"
    row = session.query(OAuthConnection).filter_by(server_name="sentinel").one()
    assert row.last_error == "got Bearer <redacted> in the challenge"
    assert "supersecrettokenvalue" not in row.last_error


def test_a_stale_grant_row_is_overwritten_not_believed(session):
    # The server was reconfigured from authorization_code to client_credentials.
    config = _config(grant="client_credentials")
    provider = _provider(config)
    state, _last_error, _fields = cs.sync_connection_state(
        config, enabled=True, provider=provider, session=session
    )

    assert state is ConnectionState.DORMANT  # not the code grant's needs_consent
    row = session.query(OAuthConnection).filter_by(server_name="sentinel").one()
    assert row.grant == "client_credentials"
    assert row.status == "dormant"


def test_a_missing_client_secret_is_dormant_and_named(session):
    config = _config(grant="client_credentials")
    provider = _provider(config)
    state, _last_error, fields = cs.sync_connection_state(
        config,
        enabled=True,
        missing_secrets=["MCP_SENTINEL_CLIENT_SECRET"],
        provider=provider,
        session=session,
    )

    assert state is ConnectionState.DORMANT
    assert fields["missing_secrets"] == ["MCP_SENTINEL_CLIENT_SECRET"]


def test_a_database_that_cannot_answer_never_breaks_the_sync(monkeypatch):
    config = _config()
    provider = _provider(config)

    def _explode(*args, **kwargs):
        raise RuntimeError("no database")

    monkeypatch.setattr(cs, "unit_of_work", _explode)
    state, last_error, fields = cs.sync_connection_state(
        config, enabled=True, provider=provider
    )

    assert state is ConnectionState.NEEDS_CONSENT
    assert last_error is None
    assert fields["grant"] == "authorization_code"


# -- the glue: config parsing, provider identity, secrets ---------------------


def test_a_server_with_no_auth_block_is_not_oauth_managed():
    assert cs.auth_config_for("sentinel", None) == (None, None)
    assert cs.auth_config_for("sentinel", {}) == (None, None)


def test_an_unparseable_auth_block_is_a_safe_error():
    config, error = cs.auth_config_for(
        "sentinel",
        {"type": "oauth2", "grant": "device_flow", "server_url": "https://x"},
    )
    assert config is None
    assert error is not None
    assert "device_flow" in error


def test_ensure_provider_is_one_instance_per_config():
    config = _config()
    first = cs.ensure_provider(config)
    assert cs.ensure_provider(config) is first


def test_ensure_provider_reconfigures_when_the_auth_block_changes():
    first = cs.ensure_provider(_config())
    second = cs.ensure_provider(_config(grant="client_credentials"))
    assert second is not first
    assert oauth.token_providers().provider_for("sentinel") is second


def test_missing_auth_secrets_names_the_referenced_key(monkeypatch):
    saved: Dict[str, str] = {"MCP_SENTINEL_CLIENT_SECRET": "s3cret"}
    monkeypatch.setattr(
        cs, "get_secret", lambda key, default=None: saved.get(key, default)
    )
    config = _config(grant="client_credentials")
    assert cs.missing_auth_secrets(config) == []

    saved.clear()
    assert cs.missing_auth_secrets(config) == ["MCP_SENTINEL_CLIENT_SECRET"]


# -- status_fields: what a status row gets ------------------------------------


def test_status_fields_are_none_without_an_auth_block():
    assert cs.status_fields("sentinel", None, enabled=True) is None


def test_status_fields_report_an_unparseable_block_without_a_row(session):
    state, last_error, fields = cs.status_fields(
        "sentinel",
        {"type": "oauth2", "grant": "nope", "server_url": "https://x"},
        enabled=True,
        session=session,
    )
    assert state is ConnectionState.ERROR
    assert last_error
    assert fields == {}
    assert session.query(OAuthConnection).count() == 0


def test_status_fields_resolve_and_do_not_raise(session):
    config = _config()
    provider = cs.ensure_provider(config)
    provider.state = ProviderState.CONNECTED
    provider._access_token = "at"
    provider._expires_at = 4_000_000_000.0
    state, last_error, fields = cs.status_fields(
        "sentinel", SENTINEL_AUTH, enabled=True, session=session
    )

    assert state is ConnectionState.CONNECTED
    assert last_error is None
    assert fields["grant"] == "authorization_code"
    assert fields["resource"] == "https://sentinel.example.corp/mcp"
    assert fields["token_expires_at"] is not None
    assert fields["missing_secrets"] == []


def test_status_fields_survive_a_broken_database(session, monkeypatch):
    def _explode(*args, **kwargs):
        raise RuntimeError("no database")

    monkeypatch.setattr(cs, "unit_of_work", _explode)
    state, _last_error, fields = cs.status_fields(
        "sentinel", SENTINEL_AUTH, enabled=False
    )
    assert state is ConnectionState.DISABLED
    assert fields["grant"] == "authorization_code"


# -- housekeeping: rows do not outlive their servers --------------------------


def test_prune_drops_rows_for_servers_gone_from_the_catalog(session):
    session.add(
        OAuthConnection(
            server_name="gone", grant="client_credentials", status="dormant"
        )
    )
    session.add(
        OAuthConnection(
            server_name="sentinel", grant="authorization_code", status="connected"
        )
    )
    session.flush()

    assert cs.prune_connections(["sentinel"], session=session) == 1
    remaining = {row.server_name for row in session.query(OAuthConnection).all()}
    assert remaining == {"sentinel"}


def test_prune_tolerates_a_broken_database(monkeypatch):
    def _explode(*args, **kwargs):
        raise RuntimeError("no database")

    monkeypatch.setattr(cs, "unit_of_work", _explode)
    assert cs.prune_connections(["sentinel"]) == 0


# -- the model: what an operator may see --------------------------------------


def test_to_dict_exposes_metadata_and_no_secrets():
    row = OAuthConnection(
        server_name="sentinel",
        grant="authorization_code",
        issuer_url="https://idp.example",
        client_id="vigil-client",
        scopes=["read", "invoke"],
        resource="https://sentinel.example.corp",
        status="connected",
    )
    shown = row.to_dict()
    assert shown["scopes"] == ["read", "invoke"]
    assert shown["status"] == "connected"
    assert shown["last_error"] is None
