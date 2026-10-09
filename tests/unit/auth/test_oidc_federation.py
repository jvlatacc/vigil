"""A federated sign-in ends in the same session a local one mints — or in nothing at all.

The full authorization-code + PKCE dance runs against a stub issuer (test-signed
RSA keys served over a mock HTTP transport) while everything on the Vigil side
is real: the real app, the real session JWT machinery, the real Redis-shaped
state store over a fake client, and the same SQLite grounding
``test_group_mapping.py`` and ``test_token_type.py`` use.

The rejection matrix is the point: a badly-signed, wrongly-aimed, stale,
nonce-mismatched token or a replayed state each fails closed — no session, no
cookies, no partial user. And the two tripwires the plan names — local login
and first-admin bootstrap — stay green with federation enabled.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.auth import current_user as current_user_module
from core.auth.auth_cookies import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from core.auth.auth_service import JWT_SECRET_KEY, AuthService
from core.auth.federation import config as federation_config
from core.auth.federation import state_store as state_store_module
from core.auth.federation.errors import OidcUnavailableError, TokenExchangeError
from core.auth.federation.oidc import OidcProvider
from core.auth.federation.state_store import PendingLogin, RedisStateStore
from core.auth.group_mapping import UNMAPPED_ROLE_ID
from core.routing import request_unit_of_work
from core.storage.models import Role, RoleGroupMapping, User
from core.storage.models.base import Base
from services.api import main as backend_main
from services.api.middleware.rate_limit import limiter as shared_limiter
from services.api.routers import auth as auth_router

pytestmark = pytest.mark.unit

UA = "pytest-federation-agent/1"
STATE_KEY_PREFIX = "vigil:oidc:login:"

ANALYST_PERMS = {"findings.read": True, "cases.read": True, "ai_chat.use": True}
ADMIN_PERMS = {**ANALYST_PERMS, "users.write": True, "settings.write": True}


# `roles` and `users` carry JSONB columns SQLite cannot render at all, and
# BIGSERIAL ids SQLite cannot auto-increment. Same dialect shims as the other
# SQLite-grounded tests; registered for the SQLite dialect only.
@compiles(JSONB, "sqlite")
def _jsonb_is_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_is_integer_on_sqlite(type_, compiler, **kw):
    return "INTEGER"


def s256_b64url(plain: str) -> str:
    digest = hashlib.sha256(plain.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class StubIssuer:
    """A minimal OIDC provider: discovery, JWKS, and a PKCE-checking token endpoint.

    What it does faithfully: signs id_tokens with a real RSA key it publishes
    at its JWKS endpoint, binds every minted code to the ``code_challenge`` of
    the authorize request it is minted for, and checks ``client_id``,
    ``redirect_uri`` and the PKCE ``code_verifier`` at the token endpoint the
    way a broker does, single-use. What it does not do: the authorization-
    endpoint UX itself — tests mint codes directly, which is the piece a
    browser would drive.
    """

    ISSUER = "https://idp.stub"
    CLIENT_ID = "vigil-console"
    REDIRECT_URI = "http://testserver/api/auth/oidc/callback"

    def __init__(self):
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = "stub-key-1"
        self._codes: dict[str, dict] = {}

    # -- what a client discovers ------------------------------------------
    def discovery(self) -> dict:
        return {
            "issuer": self.ISSUER,
            "authorization_endpoint": f"{self.ISSUER}/authorize",
            "token_endpoint": f"{self.ISSUER}/token",
            "jwks_uri": f"{self.ISSUER}/jwks.json",
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    def jwks(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
        jwk.update({"kid": self._kid, "alg": "RS256", "use": "sig"})
        return {"keys": [jwk]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json=self.discovery())
        if request.url.path == "/jwks.json":
            return httpx.Response(200, json=self.jwks())
        if request.url.path == "/token":
            return self._token_endpoint(request)
        return httpx.Response(404)

    # -- what the tests drive ---------------------------------------------
    def mint_code(self, *, challenge: str, claims: dict, id_token: str = None) -> str:
        """Mint an authorization code the way the authorize step would have.

        ``id_token`` lets a test bind a token the issuer itself did not sign
        — the shape a forged or tampered token arrives in.
        """
        code = "code-" + uuid.uuid4().hex
        self._codes[code] = {
            "challenge": challenge,
            "claims": claims,
            "id_token": id_token,
        }
        return code

    def sign(self, claims: dict, key=None) -> str:
        signing_key = key or self._key
        pem = signing_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": self._kid})

    def second_key(self):
        """A key this issuer never published — for the bad-signature test."""
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # -- the token endpoint -------------------------------------------------
    def _token_endpoint(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        single = lambda name: (form.get(name) or [""])[0]  # noqa: E731
        code = single("code")
        record = self._codes.get(code)
        if record is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        if single("client_id") != self.CLIENT_ID:
            return httpx.Response(401, json={"error": "invalid_client"})
        if single("redirect_uri") != self.REDIRECT_URI:
            return httpx.Response(400, json={"error": "invalid_grant"})
        # PKCE, enforced: only the client holding the verifier that hashes
        # to the challenge bound at authorize time gets the code cashed.
        if s256_b64url(single("code_verifier")) != record["challenge"]:
            return httpx.Response(400, json={"error": "invalid_grant"})
        del self._codes[code]  # a code is spent by a successful exchange
        id_token = record["id_token"] or self.sign(record["claims"])
        return httpx.Response(
            200,
            json={
                "access_token": "stub-access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": id_token,
            },
        )


def id_token_claims(
    *,
    nonce: str,
    groups=("vigil-analysts",),
    username="ada",
    email="ada@example.com",
    sub="idp-sub-123",
    issuer=StubIssuer.ISSUER,
    client_id=StubIssuer.CLIENT_ID,
    at=None,
) -> dict:
    now = int(time.time()) if at is None else at
    return {
        "iss": issuer,
        "aud": client_id,
        "azp": client_id,
        "sub": sub,
        "exp": now + 300,
        "iat": now,
        "nonce": nonce,
        "preferred_username": username,
        "email": email,
        "groups": list(groups),
    }


@pytest.fixture
def stub():
    return StubIssuer()


class FakeAsyncRedis:
    """The two commands the state store issues."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def getdel(self, key):
        return self.data.pop(key, None)


@pytest.fixture
def state_redis(monkeypatch):
    fake = FakeAsyncRedis()
    monkeypatch.setattr(state_store_module, "get_async_redis", lambda feature: fake)
    return fake


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine, tables=[Role.__table__, User.__table__, RoleGroupMapping.__table__]
    )
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as s:
        s.add(
            Role(
                role_id=UNMAPPED_ROLE_ID,
                name="Unmapped",
                description="authenticated but directory-unmapped",
                permissions={},
                is_system_role=True,
            )
        )
        s.add(
            Role(
                role_id="r-analyst",
                name="Analyst",
                description="",
                permissions=dict(ANALYST_PERMS),
            )
        )
        s.add(
            Role(
                role_id="r-admin",
                name="Admin",
                description="",
                permissions=dict(ADMIN_PERMS),
                is_system_role=True,
            )
        )
        s.commit()
    return maker


def add_mapping(
    session_factory, role_id: str, idp_group: str, priority: int = 100
) -> None:
    """Insert a group→role mapping on the test's own SQLite database."""
    with session_factory() as s:
        s.add(RoleGroupMapping(role_id=role_id, idp_group=idp_group, priority=priority))
        s.commit()


def _enabled_config(**overrides) -> "federation_config.OidcConfig":
    values = dict(
        issuer_url=StubIssuer.ISSUER,
        client_id=StubIssuer.CLIENT_ID,
        scopes=("openid", "profile", "email"),
        groups_claim="groups",
        redirect_uri=StubIssuer.REDIRECT_URI,
        post_login_redirect="",
        enabled=True,
    )
    values.update(overrides)
    return federation_config.OidcConfig(**values)


@pytest.fixture
def client(monkeypatch, session_factory, stub, state_redis):
    """The real app with three substitutions: SQLite under the request unit of
    work, the config pointing at the stub, and the provider's HTTP transport
    serving the stub. Revocation lookup is patched off exactly as
    ``test_token_type.py`` patches it — minting is what is under test here."""

    async def _not_revoked(payload):
        return False

    monkeypatch.setattr(current_user_module, "DEV_MODE", False)
    monkeypatch.setattr(current_user_module, "is_token_revoked", _not_revoked)
    monkeypatch.setattr(auth_router, "is_token_revoked", _not_revoked)

    def _session():
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    backend_main.app.dependency_overrides[request_unit_of_work] = _session
    backend_main.app.dependency_overrides[auth_router.get_oidc_config] = (
        lambda: _enabled_config()
    )
    backend_main.app.dependency_overrides[auth_router.get_oidc_provider] = (
        lambda: OidcProvider(
            issuer_url=stub.ISSUER,
            client_id=stub.CLIENT_ID,
            scopes=("openid", "profile", "email"),
            groups_claim="groups",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(stub.handler)),
        )
    )
    # One 10/minute budget per route is shared by every test's client —
    # rate limiting is not what these tests are about — and the auth
    # cookies are Secure, which a plain-http cookie jar withholds (the
    # bootstrap suite's client pattern).
    was_enabled = shared_limiter.enabled
    shared_limiter.enabled = False
    try:
        yield TestClient(backend_main.app, base_url="https://testserver")
    finally:
        shared_limiter.enabled = was_enabled
        backend_main.app.dependency_overrides.clear()


def begin_sign_in(client, state_redis):
    """Drive the redirect out; return ``(state, code_challenge, nonce)``.

    Also proves the challenge Vigil sent is the hash of a verifier only
    Vigil's store holds — the test reads the verifier back and re-derives it.
    """
    started = client.get("/api/auth/oidc/login", follow_redirects=False)
    assert started.status_code == 302, started.text
    authorize_url = urlparse(started.headers["location"])
    query = parse_qs(authorize_url.query)
    state = query["state"][0]
    challenge = query["code_challenge"][0]
    assert query["code_challenge_method"][0] == "S256"
    pending = json.loads(state_redis.data[STATE_KEY_PREFIX + state])
    assert s256_b64url(pending["code_verifier"]) == challenge
    return state, challenge, pending["nonce"]


def drive_to_code(client, stub, state_redis, **claim_overrides):
    """A started sign-in carried to the point of holding a fresh code."""
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce, **claim_overrides)
    return stub.mint_code(challenge=challenge, claims=claims), state, claims


def redeem(client, code, state):
    return client.get(
        f"/api/auth/oidc/callback?code={code}&state={state}",
        follow_redirects=False,
        headers={"User-Agent": UA},
    )


def cookies_of(response) -> set:
    return {
        header.split("=", 1)[0] for header in response.headers.get_list("set-cookie")
    }


def decoded_access(response) -> dict:
    token = response.cookies[ACCESS_COOKIE_NAME]
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])


def _assert_closed(done):
    assert done.status_code in (400, 401), done.text
    assert not cookies_of(done), f"no session may survive a {done.status_code}"


def seed_local_user(
    session_factory, username: str, email: str, role_id: str, **extra
) -> None:
    """A local row with the columns the schema requires (full_name, email are
    NOT NULL); ``extra`` overrides defaults, per-test."""
    params = dict(
        user_id=f"user-local-{username}",
        username=username,
        email=email,
        password_hash=AuthService.hash_password("a-local-password-not-used"),
        full_name=username,
        role_id=role_id,
        is_active=True,
    )
    params.update(extra)
    with session_factory() as s:
        s.add(User(**params))
        s.commit()


# --- the happy path --------------------------------------------------------


def test_federated_login_mints_the_local_session_shape(
    client, stub, state_redis, session_factory
):
    add_mapping(session_factory, "r-analyst", "vigil-analysts")
    code, state, _ = drive_to_code(client, stub, state_redis)

    done = redeem(client, code, state)

    assert done.status_code == 302, done.text
    assert {ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME} <= cookies_of(done)
    claims = decoded_access(done)
    assert claims["username"] == "ada"
    assert claims["role_id"] == "r-analyst"
    assert claims["token_type"] == "access"
    # The local session's contract: identity, role, revocation handle and a
    # session fingerprint — all present, all the same machinery as login.
    assert claims["jti"]
    assert claims["sfp"]
    with session_factory() as s:
        user = s.query(User).filter(User.username == "ada").one()
        assert user.email == "ada@example.com"


def test_the_session_works_downstream(client, stub, state_redis, session_factory):
    """The cookie the callback sets is a real session, not a shaped lookalike."""
    add_mapping(session_factory, "r-analyst", "vigil-analysts")
    code, state, _ = drive_to_code(client, stub, state_redis)
    redeem(client, code, state)

    me = client.get("/api/auth/me", headers={"User-Agent": UA})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == "ada"


def test_role_comes_from_the_group_claim(client, stub, state_redis, session_factory):
    add_mapping(session_factory, "r-analyst", "vigil-analysts")
    code, state, _ = drive_to_code(
        client, stub, state_redis, groups=("vigil-analysts",)
    )
    redeem(client, code, state)
    with session_factory() as s:
        assert s.query(User).filter(User.username == "ada").one().role_id == "r-analyst"


def test_priority_wins_when_groups_map_to_several_roles(
    client, stub, state_redis, session_factory
):
    add_mapping(session_factory, "r-analyst", "vigil-analysts", priority=10)
    add_mapping(session_factory, "r-admin", "vigil-admins", priority=100)
    code, state, _ = drive_to_code(
        client, stub, state_redis, groups=("vigil-analysts", "vigil-admins")
    )
    redeem(client, code, state)
    with session_factory() as s:
        assert s.query(User).filter(User.username == "ada").one().role_id == "r-admin"


def test_unmapped_user_gets_the_deny_by_default_role(
    client, stub, state_redis, session_factory
):
    code, state, _ = drive_to_code(client, stub, state_redis, groups=("vigil-nobody",))
    done = redeem(client, code, state)

    assert done.status_code == 302
    assert "oidc_state=unmapped" in done.headers["location"]
    assert decoded_access(done)["role_id"] == UNMAPPED_ROLE_ID
    with session_factory() as s:
        assert (
            s.query(User).filter(User.username == "ada").one().role_id
            == UNMAPPED_ROLE_ID
        )


def test_the_directory_redecides_the_role_on_every_login(
    client, stub, state_redis, session_factory
):
    add_mapping(session_factory, "r-analyst", "vigil-analysts")
    code, state, _ = drive_to_code(client, stub, state_redis)
    redeem(client, code, state)

    # The directory moved the person; the mapping follows at next sign-in.
    with session_factory() as s:
        mapping = s.query(RoleGroupMapping).one()
        mapping.role_id = "r-admin"
        s.commit()

    code2, state2, _ = drive_to_code(client, stub, state_redis)
    redeem(client, code2, state2)
    with session_factory() as s:
        assert s.query(User).filter(User.username == "ada").one().role_id == "r-admin"


def test_existing_account_links_by_email(client, stub, state_redis, session_factory):
    """A local account the directory can vouch for is claimed, not duplicated."""
    seed_local_user(session_factory, "bob", "ada@example.com", "r-analyst")

    code, state, _ = drive_to_code(
        client, stub, state_redis, username="bob", email="ada@example.com"
    )
    redeem(client, code, state)

    with session_factory() as s:
        users = s.query(User).all()
        assert len(users) == 1, "no duplicate row for a linked account"
        assert users[0].username == "bob"


def test_existing_account_links_by_username_when_email_is_absent(
    client, stub, state_redis, session_factory
):
    """A deployment whose IdP omits the email claim still links — by exact
    username, leaving the local row's own email untouched."""
    seed_local_user(session_factory, "bob", "bob@local.test", "r-analyst")

    code, state, _ = drive_to_code(
        client, stub, state_redis, username="bob", email=None
    )
    done = redeem(client, code, state)
    assert done.status_code == 302
    with session_factory() as s:
        users = s.query(User).all()
        assert len(users) == 1
        assert users[0].email == "bob@local.test"


def test_username_collision_with_a_different_email_is_refused(
    client, stub, state_redis, session_factory
):
    """At the IdP anyone can claim any username; a collision is an account-
    takeover attempt until the email agrees it is not."""
    seed_local_user(session_factory, "bob", "bob@local.test", "r-admin")

    code, state, _ = drive_to_code(
        client, stub, state_redis, username="bob", email="attacker@idp.test"
    )
    done = redeem(client, code, state)

    _assert_closed(done)
    with session_factory() as s:
        user = s.query(User).one()
        assert user.email == "bob@local.test", "the local row is untouched"
        assert user.role_id == "r-admin", "the local role is untouched"


def test_disabled_account_cannot_sign_in_federated(
    client, stub, state_redis, session_factory
):
    seed_local_user(
        session_factory, "ada", "ada@example.com", "r-admin", is_active=False
    )

    code, state, _ = drive_to_code(client, stub, state_redis)
    _assert_closed(redeem(client, code, state))


def test_jit_provisioned_accounts_cannot_password_login(
    client, stub, state_redis, session_factory
):
    """The provisioned row's password hash guards nothing — bcrypt of a
    secret that was discarded the moment it was hashed."""
    code, state, _ = drive_to_code(client, stub, state_redis)
    redeem(client, code, state)

    with session_factory() as s:
        user = s.query(User).filter(User.username == "ada").one()
        assert user.password_hash.startswith("$2")
        assert not AuthService.verify_password(
            "anything-a-guesser-tries", user.password_hash
        )
        assert not user.mfa_enabled


# --- the rejection matrix: every failure is fail-closed --------------------


def test_bad_signature_rejected(client, stub, state_redis):
    """A token signed by a key the issuer never published verifies to nothing."""
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce)
    forged = stub.sign(claims, key=stub.second_key())
    code = stub.mint_code(challenge=challenge, claims=claims, id_token=forged)
    _assert_closed(redeem(client, code, state))


def test_wrong_audience_rejected(client, stub, state_redis):
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce, client_id="someone-else")
    code = stub.mint_code(challenge=challenge, claims=claims)
    _assert_closed(redeem(client, code, state))


def test_wrong_issuer_rejected(client, stub, state_redis):
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce, issuer="https://other-idp.stub")
    code = stub.mint_code(challenge=challenge, claims=claims)
    _assert_closed(redeem(client, code, state))


def test_expired_token_rejected(client, stub, state_redis):
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce, at=int(time.time()) - 600)
    claims["exp"] = int(time.time()) - 300  # beyond any leeway
    code = stub.mint_code(challenge=challenge, claims=claims)
    _assert_closed(redeem(client, code, state))


def test_nonce_mismatch_rejected(client, stub, state_redis):
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce="a-different-nonce")
    code = stub.mint_code(challenge=challenge, claims=claims)
    _assert_closed(redeem(client, code, state))


def test_replayed_state_rejected(client, stub, state_redis):
    """The same state answers once. A replaying callback finds nothing."""
    code, state, _ = drive_to_code(client, stub, state_redis)
    first = redeem(client, code, state)
    assert first.status_code == 302

    # A replay re-sends the *same* state (with a fresh code, as an attacker
    # replaying a captured callback would).
    _assert_closed(redeem(client, "code-replayed", state))


def test_replayed_code_rejected(client, stub, state_redis):
    """The issuer spends a code on first exchange; the second exchange fails."""
    code, state, _ = drive_to_code(client, stub, state_redis)
    first = redeem(client, code, state)
    assert first.status_code == 302
    # A fresh sign-in whose callback carries the spent code.
    begin_sign_in(client, state_redis)
    keys = [k for k in state_redis.data if k.startswith(STATE_KEY_PREFIX)]
    fresh_state = keys[-1].removeprefix(STATE_KEY_PREFIX)
    _assert_closed(redeem(client, code, fresh_state))


def test_missing_code_or_state_rejected(client, stub, state_redis):
    assert redeem(client, None, "some-state").status_code == 400
    assert redeem(client, "some-code", None).status_code == 400


def test_pkce_verifier_checked_at_the_token_endpoint(client, stub, state_redis):
    """The broker enforces PKCE: a client that lost the verifier cannot cash
    the code — the exchange itself refuses before any verification runs."""
    state, challenge, nonce = begin_sign_in(client, state_redis)
    claims = id_token_claims(nonce=nonce)
    code = stub.mint_code(challenge=challenge, claims=claims)

    provider = OidcProvider(
        issuer_url=stub.ISSUER,
        client_id=stub.CLIENT_ID,
        scopes=("openid",),
        groups_claim="groups",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(stub.handler)),
    )
    wrong = PendingLogin(
        state=state,
        nonce=nonce,
        code_verifier="wrong-verifier",
        redirect_uri=stub.REDIRECT_URI,
    )
    with pytest.raises(TokenExchangeError):
        asyncio.run(provider.exchange(code, wrong))


def test_a_second_id_token_verifies_from_the_cached_key_set(stub):
    """One JWKS fetch serves every token until rotation or staleness — a
    client that refetched per token would hammer the IdP on every sign-in."""
    jwks_hits = {"n": 0}

    def counting_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/jwks.json":
            jwks_hits["n"] += 1
        return stub.handler(request)

    provider = OidcProvider(
        issuer_url=stub.ISSUER,
        client_id=stub.CLIENT_ID,
        scopes=("openid",),
        groups_claim="groups",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(counting_handler)
        ),
    )
    for nonce in ("nonce-1", "nonce-2"):
        token = stub.sign(id_token_claims(nonce=nonce))
        payload = asyncio.run(provider.verify_id_token(token, nonce=nonce))
        assert payload["aud"] == stub.CLIENT_ID
    assert jwks_hits["n"] == 1, "the second verify must ride the cached key set"


# --- the doors that must stay open -----------------------------------------


def test_local_login_still_works(client, session_factory):
    """The tripwire: federation is on in this fixture, local login is unmoved."""
    seed_local_user(session_factory, "nora", "nora@example.com", "r-admin")

    done = client.post(
        "/api/auth/login",
        json={"username_or_email": "nora", "password": "a-local-password-not-used"},
        headers={"User-Agent": UA},
    )
    assert done.status_code == 200, done.text
    assert ACCESS_COOKIE_NAME in done.cookies


def test_first_admin_bootstrap_still_open_on_an_empty_install(client, session_factory):
    done = client.get("/api/auth/bootstrap")
    assert done.status_code == 200
    assert (
        done.json()["required"] is True
    ), "an empty install must still offer bootstrap"


# --- the off switch ---------------------------------------------------------


def test_routes_404_when_federation_is_disabled(client, monkeypatch):
    backend_main.app.dependency_overrides[auth_router.get_oidc_config] = (
        lambda: _enabled_config(enabled=False)
    )
    assert client.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404
    assert (
        client.get(
            "/api/auth/oidc/callback?code=x&state=y", follow_redirects=False
        ).status_code
        == 404
    )


# --- the config surface ------------------------------------------------------


def _clear_settings_cache():
    from core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def no_stored_config(monkeypatch):
    monkeypatch.setattr(federation_config, "_stored_config", lambda: {})
    _clear_settings_cache()
    yield
    _clear_settings_cache()


def test_disabled_by_default(no_stored_config):
    cfg = federation_config.load_oidc_config()
    assert cfg.enabled is False
    assert cfg.issuer_url == ""


def test_env_floor_enables(monkeypatch, no_stored_config):
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://idp.stub")
    monkeypatch.setenv("OIDC_CLIENT_ID", "vigil-console")
    cfg = federation_config.load_oidc_config()
    assert cfg.enabled is True
    assert cfg.scopes == ("openid", "profile", "email")


def test_system_config_is_a_kill_switch(monkeypatch, no_stored_config):
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://idp.stub")
    monkeypatch.setenv("OIDC_CLIENT_ID", "vigil-console")
    monkeypatch.setattr(federation_config, "_stored_config", lambda: {"enabled": False})
    assert federation_config.load_oidc_config().enabled is False


def test_stored_values_fill_env_gaps(monkeypatch, no_stored_config):
    monkeypatch.setattr(
        federation_config,
        "_stored_config",
        lambda: {"issuer_url": "https://stored.stub", "client_id": "cid"},
    )
    cfg = federation_config.load_oidc_config()
    assert cfg.enabled is True
    assert cfg.issuer_url == "https://stored.stub"


def test_env_floor_survives_an_unreadable_database(monkeypatch, no_stored_config):
    """The config service failing to read is not a yes and not a no — the env
    floor stands. Patched below the loader's catch, where the failure lives."""
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://idp.stub")
    monkeypatch.setenv("OIDC_CLIENT_ID", "vigil-console")

    import core.storage.config_service as config_service_module

    def _explode():
        raise RuntimeError("database down")

    monkeypatch.setattr(config_service_module, "get_config_service", _explode)
    assert federation_config.load_oidc_config().enabled is True


# --- the state store's own fail-closed posture -------------------------------


def test_state_store_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(state_store_module, "get_async_redis", lambda feature: None)
    store = RedisStateStore()
    pending = PendingLogin(state="s", nonce="n", code_verifier="v", redirect_uri="r")
    with pytest.raises(OidcUnavailableError):
        asyncio.run(store.put(pending))


def test_state_store_treats_unparseable_state_as_absent(state_redis):
    """A corrupted value is worse than a missing one — treat as absent."""
    state_redis.data[STATE_KEY_PREFIX + "corrupt"] = "{not json"
    assert asyncio.run(RedisStateStore().pop("corrupt")) is None


def test_state_store_answers_once_per_state(state_redis):
    """Single-use: the second pop of the same state is the replay answer."""
    store = RedisStateStore(ttl_seconds=600)
    pending = PendingLogin(state="s", nonce="n", code_verifier="v", redirect_uri="r")
    asyncio.run(store.put(pending))
    assert asyncio.run(store.pop("s")) is not None
    assert asyncio.run(store.pop("s")) is None


# --- the local provider ------------------------------------------------------


def test_local_provider_wraps_the_existing_authentication(session_factory):
    from core.auth.federation.local import LocalAuthenticationProvider
    from core.auth.federation.provider import LOCAL, LocalCredentials

    with session_factory() as s:
        s.add(
            User(
                user_id="user-local",
                username="nora",
                email="nora@example.com",
                password_hash=AuthService.hash_password("nora-local-password-01"),
                full_name="nora",
                role_id="r-admin",
                is_active=True,
            )
        )
        s.commit()

        provider = LocalAuthenticationProvider()
        identity = provider.authenticate(
            LocalCredentials(
                username_or_email="nora", password="nora-local-password-01"
            ),
            session=s,
        )
        assert identity is not None
        assert identity.provider == LOCAL
        assert identity.username == "nora"
        assert identity.idp_subject.startswith("local:")
        assert identity.groups == ()

        assert (
            provider.authenticate(
                LocalCredentials(username_or_email="nora", password="wrong"),
                session=s,
            )
            is None
        )
