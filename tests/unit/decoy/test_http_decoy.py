"""HTTP decoy behavior: canary-only login, per-client capture, error
resilience (the server outlives any bad request), and session-window
emission. Uses aiohttp's test server against the real app builder."""

import hashlib

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from services.decoy.http_decoy import DECOY_SERVICE_NAME, HttpDecoy
from services.decoy.session import DecoySession

pytestmark = pytest.mark.unit


def _decoy(config, canary, emitter) -> HttpDecoy:
    return HttpDecoy(config=config, canary=canary, emitter=emitter)


async def _client(decoy: HttpDecoy) -> TestClient:
    server = TestServer(decoy.build_app())
    client = TestClient(server)
    await client.start_server()
    return client


# --- canary-only login ------------------------------------------------------


async def test_canary_login_succeeds_and_is_recorded(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    client = await _client(decoy)
    try:
        response = await client.post(
            "/login",
            data={"username": "admin", "password": canary.value},
            allow_redirects=False,
        )
        assert response.status == 303
        assert response.headers["Location"] == "/dashboard"
        session = decoy._session_for("127.0.0.1")
        assert session.build_payload()["auth_attempts"] == [
            {"user": "admin", "result": "success", "credential": "canary"}
        ]
    finally:
        await client.close()


async def test_failed_login_is_401_recorded_and_never_locks_out(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    client = await _client(decoy)
    try:
        for _ in range(3):
            response = await client.post(
                "/login", data={"username": "admin", "password": "wrong"}
            )
            assert response.status == 401
        # The fourth attempt — even the canary — still gets a real answer.
        response = await client.post(
            "/login",
            data={"username": "admin", "password": canary.value},
            allow_redirects=False,
        )
        assert response.status == 303
        attempts = decoy._session_for("127.0.0.1").build_payload()["auth_attempts"]
        assert [a["result"] for a in attempts] == [
            "failure",
            "failure",
            "failure",
            "success",
        ]
    finally:
        await client.close()


# --- capture ----------------------------------------------------------------


async def test_browsing_is_captured_per_contract_shape(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    client = await _client(decoy)
    try:
        await client.get("/")
        await client.get("/admin")
        await client.get("/definitely/not/here")
        payload = decoy._session_for("127.0.0.1").build_payload()
        assert payload["decoy_service"] == DECOY_SERVICE_NAME == "http-decoy"
        assert payload["commands"] == ["GET /", "GET /admin", "GET /definitely/not/here"]
        assert payload["attacker_entity_key"] == "ip:127.0.0.1"
        assert payload["data_source"] == "vigil-decoy"
    finally:
        await client.close()


async def test_upload_body_is_hashed_and_recorded(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    client = await _client(decoy)
    try:
        response = await client.post("/upload", data=b"attacker-payload-bytes")
        assert response.status == 200
        (dropped,) = decoy._session_for("127.0.0.1").build_payload()["files_dropped"]
        assert dropped["name"] == "request-body.bin"
        assert dropped["source"] == "request-body"
        assert dropped["simulated"] is True
        assert dropped["sha256"] == hashlib.sha256(b"attacker-payload-bytes").hexdigest()
    finally:
        await client.close()


def test_sessions_are_per_remote_ip(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    first = decoy._session_for("203.0.113.7")
    second = decoy._session_for("203.0.113.8")
    assert decoy._session_for("203.0.113.7") is first
    assert first is not second
    assert isinstance(first, DecoySession)


# --- error resilience -------------------------------------------------------


async def test_handler_error_is_500_and_server_survives(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)

    # Force a handler to explode — patched BEFORE the app is built, since
    # the router captures the bound method. The middleware answers 500 and
    # the next request is served normally: no process death, no lockup.
    async def exploding(request):
        raise RuntimeError("boom")

    decoy.handle_index = exploding
    client = await _client(decoy)
    try:
        response = await client.get("/")
        assert response.status == 500
        response = await client.get("/health")
        assert response.status == 200
        assert await response.json() == {"status": "healthy"}
    finally:
        await client.close()


# --- session-window emission ------------------------------------------------


async def test_sweep_emits_only_expired_sessions(config, canary, emitter):
    from datetime import datetime, timedelta, timezone

    decoy = _decoy(config, canary, emitter)
    fresh = decoy._session_for("203.0.113.7")
    stale = decoy._session_for("203.0.113.8")
    stale.started = datetime.now(timezone.utc) - timedelta(seconds=3601)
    stale.last_activity = stale.started
    emitted = await decoy.sweep_expired()
    assert emitted == 1
    assert emitter.emitted == 1
    assert emitter.payloads[0]["attacker_entity_key"] == "ip:203.0.113.8"
    assert "203.0.113.8" not in decoy._sessions
    assert "203.0.113.7" in decoy._sessions


async def test_flush_all_emits_every_outstanding_session(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    decoy._session_for("203.0.113.7")
    decoy._session_for("203.0.113.8")
    decoy._session_for("203.0.113.9")
    await decoy.flush_all()
    assert emitter.emitted == 3
    assert decoy._sessions == {}


async def test_flushed_payload_matches_the_contract(config, canary, emitter):
    decoy = _decoy(config, canary, emitter)
    decoy._session_for("203.0.113.7").record_command("GET /")
    await decoy.flush_all()
    (payload,) = emitter.payloads
    assert payload["decoy_service"] == "http-decoy"
    assert payload["attacker_entity_key"] == "ip:203.0.113.7"
    assert payload["commands"] == ["GET /"]
    assert payload["routing_action_id"] is None
