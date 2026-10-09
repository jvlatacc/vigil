"""The breaker admin surface: authenticated status and audited reset (#944).

The auth fixture makes every request a permitted admin (the real cookie/JWT
path is exercised by tests/security/); what is tested here is the surface
itself — status reads the live breaker, reset is audited as the signed-in
analyst, and an unexplained reset is refused.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.v1.breaker_router import (
    provide_audit_writer,
    provide_breaker,
)
from core.api.v1.breaker_router import router as breaker_router
from core.response.breaker import ContainmentBreaker
from core.response.guards_config import GuardConfig

pytestmark = pytest.mark.unit

DEAD_REDIS = "redis://127.0.0.1:1/0"


@pytest.fixture
def breaker() -> ContainmentBreaker:
    # Fallback mode (dead Redis) keeps these tests DB- and Redis-free; the
    # breaker's Redis path is exercised by the unit suite against the same
    # fallback semantics and belongs in tests/integration with a live Redis.
    return ContainmentBreaker(
        GuardConfig(), redis_url=DEAD_REDIS, namespace="router-test"
    )


@pytest.fixture
def env(authenticate_app, breaker):
    audit_calls: List[Dict[str, Any]] = []
    app = FastAPI()
    app.include_router(breaker_router, prefix="/api/v1/response")
    authenticate_app(app)
    app.dependency_overrides[provide_breaker] = lambda: breaker
    app.dependency_overrides[provide_audit_writer] = lambda: (
        lambda old, new, changed_by, reason: audit_calls.append(
            {
                "old": old,
                "new": new,
                "changed_by": changed_by,
                "reason": reason,
            }
        )
    )
    return TestClient(app), breaker, audit_calls


def _trip(breaker: ContainmentBreaker) -> None:
    async def go():
        for _ in range(3):
            await breaker.note_invariant_block()

    asyncio.run(go())


def test_status_reads_the_live_breaker(env):
    client, breaker, _ = env
    closed = client.get("/api/v1/response/breaker")
    assert closed.status_code == 200
    assert closed.json()["state"] == "closed"
    assert closed.json()["escalation_fired"] is False

    _trip(breaker)
    opened = client.get("/api/v1/response/breaker")
    assert opened.status_code == 200
    body = opened.json()
    assert body["state"] == "open"
    assert "protected-asset probe run" in body["reason"]
    assert body["rule"].startswith("response.breaker_invariant_probe_trip=")
    assert body["seconds_left"] is not None and 1 <= body["seconds_left"] <= 900
    assert body["counters"]["invariant_probe"]["recent"] == 3.0


def test_reset_is_audited_as_the_signed_in_analyst(env):
    client, breaker, audit_calls = env
    _trip(breaker)

    response = client.post(
        "/api/v1/response/breaker/reset",
        json={"reason": "operator confirmed the flood was benign"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["before"]["state"] == "open"
    assert body["after"]["state"] == "closed"
    assert body["rule"] == "response.breaker_reset=manual"

    assert len(audit_calls) == 1
    entry = audit_calls[0]
    assert entry["old"]["state"] == "open"
    assert entry["new"]["state"] == "closed"
    assert entry["changed_by"] == "test-admin"
    assert entry["reason"] == "operator confirmed the flood was benign"
    # And the breaker is genuinely closed afterwards.
    assert client.get("/api/v1/response/breaker").json()["state"] == "closed"


def test_reset_requires_a_reason(env):
    client, _, audit_calls = env
    response = client.post("/api/v1/response/breaker/reset", json={})
    assert response.status_code == 422
    assert audit_calls == []


def test_status_reports_the_fallback_store(env):
    client, _, _ = env
    body = client.get("/api/v1/response/breaker").json()
    assert body["store"] == "memory"
