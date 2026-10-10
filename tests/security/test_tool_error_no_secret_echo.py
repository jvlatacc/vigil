"""E11 — agent-visible tool errors are classified strings, never str(e).

Raw exception text carries upstream URLs, response bodies and internal
hostnames, and went straight into agent context; Splunk failure results
additionally echoed the full SPL query. The fix: full exception detail
goes to the privileged server-side log only — the agent channel gets a
fixed string from a small classified vocabulary.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import core.integrations.carbon_black.tool as cb  # noqa: E402
import core.integrations.ip_geolocation.tool as geo  # noqa: E402
import core.integrations.microsoft_defender.tool as mde  # noqa: E402
import core.integrations.splunk.tool as sp  # noqa: E402
from core.integrations._base.tool_errors import classified_error  # noqa: E402

pytestmark = pytest.mark.unit

# What a raw exception would have leaked: an internal URL and a credential.
CANARY = "SECRET-CANARY https://internal.corp/v1 db-password=hunter2"
SPL = "index=main SENSITIVE-HUNT-TERMS"


def _payload(out):
    return json.loads(out[0].text)


@pytest.fixture()
def server_log(caplog):
    """The privileged channel: classified_error's full-detail warning."""
    caplog.set_level(logging.WARNING)
    return caplog


async def test_defender_exception_is_classified(monkeypatch, server_log):
    monkeypatch.setattr(mde, "get_token", lambda: "test-token")
    monkeypatch.setattr(
        mde.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(CANARY))
    )
    out = await mde.handle_call_tool("mde_get_alerts", {"limit": 5})
    payload = _payload(out)
    assert CANARY not in out[0].text
    assert payload["error"].startswith("tool 'mde_get_alerts' failed:")
    assert CANARY in server_log.text


async def test_carbon_black_exception_is_classified(monkeypatch, server_log):
    monkeypatch.setattr(
        cb,
        "resolve",
        lambda d: {
            "url": "https://cbc.example",
            "api_id": "i",
            "api_key": "k",
            "org_key": "o",
        },
    )
    monkeypatch.setattr(cb, "missing", lambda cfg, *req: ())
    monkeypatch.setattr(
        cb.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(CANARY))
    )
    out = await cb.handle_call_tool("cb_get_alerts", {"limit": 5})
    payload = _payload(out)
    assert CANARY not in out[0].text
    assert payload["error"].startswith("tool 'cb_get_alerts' failed:")
    assert CANARY in server_log.text


class _FailingService:
    def search(self, *a, **k):
        raise RuntimeError(CANARY)


class _NullService:
    def search(self, *a, **k):
        return None


async def test_splunk_exception_is_classified_and_echoes_no_spl(
    monkeypatch, server_log
):
    monkeypatch.setattr(sp, "get_splunk_service", lambda: _FailingService())
    out = await sp.handle_call_tool("splunk_execute", {"spl_query": SPL})
    payload = _payload(out)
    assert CANARY not in out[0].text
    assert "SENSITIVE-HUNT-TERMS" not in out[0].text
    assert payload["error"].startswith("tool 'splunk_execute' failed:")
    assert CANARY in server_log.text


async def test_splunk_failed_search_does_not_echo_query(monkeypatch):
    monkeypatch.setattr(sp, "get_splunk_service", lambda: _NullService())
    out = await sp.handle_call_tool("splunk_execute", {"spl_query": SPL})
    assert _payload(out) == {"error": "Splunk search failed or timed out"}
    assert "SENSITIVE-HUNT-TERMS" not in out[0].text


async def test_splunk_not_configured_does_not_echo_query(monkeypatch):
    monkeypatch.setattr(sp, "get_splunk_service", lambda: None)
    out = await sp.handle_call_tool("splunk_execute", {"spl_query": SPL})
    assert _payload(out) == {"error": "Splunk not configured"}
    assert "SENSITIVE-HUNT-TERMS" not in out[0].text


async def test_geolocation_exception_is_classified(monkeypatch, server_log):
    monkeypatch.setattr(
        geo.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError(CANARY))
    )
    out = await geo.handle_call_tool("geolocate_ip", {"ip": "8.8.8.8"})
    payload = _payload(out)
    assert CANARY not in out[0].text
    assert payload["error"] == "tool 'geolocate_ip' failed: the tool call failed"
    assert CANARY in server_log.text


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://vendor.example/api")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        "upstream exploded", request=request, response=response
    )


def test_classification_vocabulary_hides_detail():
    # A connect error names the host it failed to reach — that stays in the log.
    connect = httpx.ConnectError("dial tcp 10.9.9.9:443 failed")
    err = classified_error("carbon-black", "cb_get_alerts", connect)
    assert "10.9.9.9" not in err
    assert "could not be reached" in err

    # A status error may carry the code (classification), not the body.
    err = classified_error("x", "y", _status_error(503))
    assert "HTTP 503" in err
    assert "upstream exploded" not in err

    # Timeouts classify; anything unmapped fails closed to the generic string.
    assert "did not respond in time" in classified_error(
        "x", "y", httpx.TimeoutException("t")
    )
    assert "the tool call failed" in classified_error("x", "y", ValueError("weird"))
