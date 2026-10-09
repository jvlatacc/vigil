"""E12 — the Cloudy webhook requires a timestamp and rejects replays.

The receiver verified an HMAC over the raw body with no timestamp and no
memory: a captured request could be replayed forever. The signed body now
carries a numeric unix timestamp accepted only within a ±5-minute skew
window, and a verified signature is remembered briefly so the same signed
body posted twice is rejected as a replay.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

pytestmark = pytest.mark.unit

ENDPOINT = "/api/webhooks/cloudflare/cloudy"
SECRET = "s3cret"

# Imported for the shared rejection counters the health endpoint reports.
from core import webhook_rejections as wr  # noqa: E402


def _load_router_module():
    """Fresh module state per test — the replay cache lives at module level."""
    spec = importlib.util.spec_from_file_location(
        "cloudy_replay_under_test",
        REPO / "core" / "integrations" / "cloudflare" / "cloudflare_webhooks_router.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def receiver(monkeypatch):
    mod = _load_router_module()
    monkeypatch.setattr(mod, "cloudy_ingestion_enabled", lambda: True)
    monkeypatch.setattr(mod, "_get_secret", lambda: SECRET)
    ingested = []

    def _fake_ingest(payload):
        ingested.append(payload)
        return {"accepted": True, "finding_id": "f-1"}

    monkeypatch.setattr(mod, "_ingest", _fake_ingest)
    wr._counts.clear()
    wr._log_state.clear()
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/webhooks/cloudflare")
    return mod, TestClient(app), ingested


def _sign(raw: bytes) -> str:
    return hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _signed_body(**overrides):
    payload = {
        "event_id": "e-1",
        "cloudy_summary": "test finding",
        "timestamp": time.time(),
        **overrides,
    }
    raw = json.dumps(payload).encode()
    return raw, _sign(raw)


def _post(client, raw, sig):
    return client.post(
        ENDPOINT,
        content=raw,
        headers={"Content-Type": "application/json", "X-Cloudflare-Signature": sig},
    )


def test_fresh_signed_payload_is_accepted(receiver):
    _, client, ingested = receiver
    raw, sig = _signed_body()
    resp = _post(client, raw, sig)
    assert resp.status_code == 202, resp.text
    assert len(ingested) == 1
    assert ingested[0]["event_id"] == "e-1"


def test_replay_of_same_signed_body_is_rejected(receiver):
    _, client, ingested = receiver
    raw, sig = _signed_body()
    first = _post(client, raw, sig)
    replay = _post(client, raw, sig)
    assert first.status_code == 202
    assert replay.status_code == 401, replay.text
    assert "Replayed" in replay.json()["detail"]
    assert len(ingested) == 1  # the replay never reached ingestion
    health = client.get(ENDPOINT + "/health")
    rejections = health.json()["rejections"]["cloudflare/cloudy"]
    assert rejections.get("replay") == 1


def test_stale_timestamp_is_rejected(receiver):
    _, client, ingested = receiver
    past, sig = _signed_body(timestamp=time.time() - 400)
    resp = _post(client, past, sig)
    assert resp.status_code == 401
    assert "outside the accepted window" in resp.json()["detail"]
    future, sig = _signed_body(timestamp=time.time() + 400)
    resp = _post(client, future, sig)
    assert resp.status_code == 401
    assert len(ingested) == 0


def test_missing_or_malformed_timestamp_is_rejected(receiver):
    _, client, ingested = receiver
    body = json.loads(json.dumps({"event_id": "e-1", "cloudy_summary": "x"}))
    raw = json.dumps(body).encode()
    resp = _post(client, raw, _sign(raw))
    assert resp.status_code == 422
    assert "timestamp" in resp.json()["detail"]

    raw, sig = _signed_body(timestamp="not-a-number")
    resp = _post(client, raw, sig)
    assert resp.status_code == 422
    assert len(ingested) == 0


def test_tampered_body_still_fails_signature(receiver):
    _, client, ingested = receiver
    raw, sig = _signed_body()
    tampered = raw.replace(b"test finding", b"evil finding")
    resp = _post(client, tampered, sig)
    assert resp.status_code == 401
    assert "signature" in resp.json()["detail"].lower()
    assert len(ingested) == 0


def test_different_signed_body_is_not_a_replay(receiver):
    _, client, ingested = receiver
    raw1, sig1 = _signed_body(event_id="e-1")
    raw2, sig2 = _signed_body(event_id="e-2")
    assert _post(client, raw1, sig1).status_code == 202
    assert _post(client, raw2, sig2).status_code == 202
    assert len(ingested) == 2


def test_replay_cache_expires_after_ttl(receiver):
    mod, _, _ = receiver
    now = 1000.0
    assert mod._seen_before("sig-a", now=now) is False
    assert mod._seen_before("sig-a", now=now + 1) is True
    assert (
        mod._seen_before("sig-a", now=now + mod._REPLAY_TTL_SECONDS + 1) is False
    ), "an expired entry must not block the same signature forever"
