"""Emitter behavior: best-effort delivery to the daemon ingest — a failure
is counted and logged, never raised; capture continues when the SOC is
unreachable. The bearer token rides the shared daemon token channel."""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from services.decoy.emitter import INGEST_TOKEN_SECRET_KEY, SessionEventEmitter

pytestmark = pytest.mark.unit


def _payload():
    return {"finding_id": "decoy-x", "decoy_service": "http-decoy"}


async def _ingest_app(received, status=200):
    """A stand-in for the daemon webhook ingest."""

    async def handler(request):
        received.append(
            {
                "auth": request.headers.get("Authorization"),
                "payload": await request.json(),
            }
        )
        return web.json_response({"status": "ok"}, status=status)

    app = web.Application()
    app.router.add_post("/ingest", handler)
    return app


async def test_disabled_emitter_counts_and_never_raises():
    emitter = SessionEventEmitter(ingest_url="", token="t")
    assert emitter.enabled is False
    assert await emitter.emit(_payload()) is False
    assert emitter.dropped == 1
    assert emitter.emitted == 0


async def test_successful_post_returns_true_and_carries_bearer(monkeypatch):
    received = []

    class FakeResponse:
        status = 200

        async def text(self):
            return "{}"

    class FakePostContext:
        def __init__(self, result):
            self._result = result

        async def __aenter__(self):
            return self._result

        async def __aexit__(self, *exc):
            return False

    class FakeSession:
        def __init__(self, **kwargs):
            FakeSession.init = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            FakeSession.post_args = {"url": url, "json": json, "headers": headers}
            return FakePostContext(FakeResponse())

    monkeypatch.setattr(
        "services.decoy.emitter.aiohttp.ClientSession", FakeSession
    )
    emitter = SessionEventEmitter(ingest_url="http://daemon:8081/ingest", token="tok-1")
    assert await emitter.emit(_payload()) is True
    assert emitter.emitted == 1
    assert emitter.dropped == 0
    assert FakeSession.post_args["url"] == "http://daemon:8081/ingest"
    assert FakeSession.post_args["headers"]["Authorization"] == "Bearer tok-1"
    assert FakeSession.post_args["json"] == _payload()


async def test_non_200_retries_once_then_drops(monkeypatch):
    calls = {"n": 0}

    class FakeResponse:
        status = 503

        async def text(self):
            return "unavailable"

    class FakePostContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *exc):
            return False

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            calls["n"] += 1
            return FakePostContext()

    monkeypatch.setattr(
        "services.decoy.emitter.aiohttp.ClientSession", FakeSession
    )
    sleeps = []

    async def instant_sleep(_):
        sleeps.append(_)

    monkeypatch.setattr("services.decoy.emitter.asyncio.sleep", instant_sleep)
    emitter = SessionEventEmitter(ingest_url="http://daemon:8081/ingest", token="t")
    assert await emitter.emit(_payload()) is False
    assert calls["n"] == 2  # two attempts, then give up
    assert emitter.dropped == 1


async def test_connection_error_is_counted_not_raised(monkeypatch):
    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            raise OSError("connection refused")

    monkeypatch.setattr(
        "services.decoy.emitter.aiohttp.ClientSession", FakeSession
    )

    async def instant_sleep(_):
        return

    monkeypatch.setattr("services.decoy.emitter.asyncio.sleep", instant_sleep)
    emitter = SessionEventEmitter(ingest_url="http://daemon:8081/ingest", token="t")
    assert await emitter.emit(_payload()) is False
    assert emitter.dropped == 1
    assert emitter.emitted == 0


def test_token_defaults_through_the_secret_channel(monkeypatch):
    monkeypatch.setattr(
        "services.decoy.emitter.get_secret",
        lambda key: "from-channel" if key == INGEST_TOKEN_SECRET_KEY else None,
        raising=True,
    )
    emitter = SessionEventEmitter(ingest_url="http://daemon:8081/ingest")
    assert emitter._token == "from-channel"


def test_explicit_token_beats_the_channel(monkeypatch):
    monkeypatch.setattr(
        "services.decoy.emitter.get_secret", lambda key: "from-channel", raising=True
    )
    emitter = SessionEventEmitter(ingest_url="http://daemon:8081/ingest", token="explicit")
    assert emitter._token == "explicit"
