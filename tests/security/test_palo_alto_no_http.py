"""E13 — an explicit http:// Palo Alto base URL is refused unless dev mode.

The Settings form collects a hostname, but the config accepted a scheme:
an explicit http:// base URL sent the PAN-OS API key (a query parameter)
over the wire in cleartext. The tool now refuses http:// unless dev mode —
and the spawned child's narrowed env carries no DEV_MODE, so the default
there is always off.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import core.integrations.palo_alto.tool as pa  # noqa: E402

pytestmark = pytest.mark.unit


def _config(hostname):
    return {
        "hostname": hostname,
        "api_key": "pan-key",
        "verify_ssl": None,
        "ca_cert_path": None,
    }


@pytest.fixture()
def requests_made(monkeypatch):
    """Record outbound calls; a refusal test reaching one is the bug itself."""
    calls = []

    def _record(url, *args, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(pa.httpx, "get", _record)
    return calls


def _payload(out):
    return json.loads(out[0].text)


@pytest.mark.parametrize(
    "hostname", ["http://pan.example", "HTTP://pan.example", "http://pan.example/"]
)
async def test_http_base_url_refused(hostname, monkeypatch, requests_made):
    monkeypatch.setattr(pa, "_dev_mode", lambda: False)
    monkeypatch.setattr(pa, "resolve", lambda d: _config(hostname))
    monkeypatch.setattr(pa, "missing", lambda cfg, *req: ())
    out = await pa.handle_call_tool("pan_get_threats", {"limit": 1})
    payload = _payload(out)
    assert "refused" in payload["error"]
    assert "https://" in payload["error"]
    assert requests_made == []


async def test_https_base_url_dispatches(monkeypatch, requests_made):
    monkeypatch.setattr(pa, "_dev_mode", lambda: False)
    monkeypatch.setattr(pa, "resolve", lambda d: _config("https://pan.example"))
    monkeypatch.setattr(pa, "missing", lambda cfg, *req: ())
    out = await pa.handle_call_tool("pan_get_threats", {"limit": 1})
    assert _payload(out)["success"] is True
    assert requests_made == ["https://pan.example/api/"]


async def test_bare_hostname_gets_https_prefix(monkeypatch, requests_made):
    monkeypatch.setattr(pa, "_dev_mode", lambda: False)
    monkeypatch.setattr(pa, "resolve", lambda d: _config("pan.example"))
    monkeypatch.setattr(pa, "missing", lambda cfg, *req: ())
    out = await pa.handle_call_tool("pan_get_threats", {"limit": 1})
    assert _payload(out)["success"] is True
    assert requests_made == ["https://pan.example/api/"]


async def test_http_base_url_allowed_in_dev_mode(monkeypatch, requests_made):
    monkeypatch.setattr(pa, "_dev_mode", lambda: True)
    monkeypatch.setattr(pa, "resolve", lambda d: _config("http://pan.example"))
    monkeypatch.setattr(pa, "missing", lambda cfg, *req: ())
    out = await pa.handle_call_tool("pan_get_threats", {"limit": 1})
    assert _payload(out)["success"] is True
    # The explicit scheme is honored, not re-prefixed.
    assert requests_made == ["http://pan.example/api/"]


async def test_dev_mode_off_blocks_both_tools(monkeypatch, requests_made):
    """The refusal sits on the base URL, so it guards both tools."""
    monkeypatch.setattr(pa, "_dev_mode", lambda: False)
    monkeypatch.setattr(pa, "resolve", lambda d: _config("http://pan.example"))
    monkeypatch.setattr(pa, "missing", lambda cfg, *req: ())
    out = await pa.handle_call_tool("pan_block_ip", {"ip": "9.9.9.9", "reason": "r"})
    assert "refused" in _payload(out)["error"]
    assert requests_made == []
