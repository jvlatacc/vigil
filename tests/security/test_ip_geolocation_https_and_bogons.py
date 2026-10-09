"""E10 — geolocation transport and pre-call target refusal.

ip_geolocation queried ip-api.com over plaintext HTTP: every investigated
IP (often RFC1918) left the host in the clear, and a MITM could forge the
intel fed to agents. The lookup now speaks HTTPS only, and bogon or
non-literal targets are refused before any outbound call — the query
itself is the disclosure, so refusal has to happen before it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import core.integrations.ip_geolocation.tool as geo  # noqa: E402

pytestmark = pytest.mark.unit

# RFC1918, loopback, cloud metadata, unspecified, multicast, reserved,
# link-local v6, unique-local v6, and the v4-mapped private form.
BOGON_TARGETS = [
    "10.0.0.1",
    "192.168.1.10",
    "172.16.0.5",
    "127.0.0.1",
    "169.254.169.254",
    "0.0.0.0",
    "224.0.0.1",
    "240.0.0.1",
    "::1",
    "fe80::1",
    "fd00::1",
    "::ffff:10.0.0.1",
]

NON_LITERALS = ["example.com", "localhost", "8.8.8.256"]


@pytest.fixture()
def outbound_calls(monkeypatch):
    """Record HTTP calls; a refusal test reaching one is the bug itself."""
    calls = []

    def _boom(url, *args, **kwargs):
        calls.append(url)
        raise AssertionError("outbound HTTP call made for a refused target")

    monkeypatch.setattr(geo.httpx, "get", _boom)
    return calls


def _payload(out):
    return json.loads(out[0].text)


@pytest.mark.parametrize("ip", BOGON_TARGETS)
async def test_bogon_refused_before_any_call(ip, outbound_calls):
    out = await geo.handle_call_tool("geolocate_ip", {"ip": ip})
    payload = _payload(out)
    assert payload["error"], f"{ip} must be refused with an error"
    assert "not looked up" in payload["error"]
    assert outbound_calls == []


@pytest.mark.parametrize("ip", NON_LITERALS)
async def test_non_literal_refused_before_any_call(ip, outbound_calls):
    out = await geo.handle_call_tool("geolocate_ip", {"ip": ip})
    payload = _payload(out)
    assert "literal" in payload["error"]
    assert outbound_calls == []


async def test_public_ip_is_looked_up_over_https(monkeypatch):
    seen_urls = []

    def _fake_get(url, **kwargs):
        seen_urls.append(url)
        # ipwho.is response shape (live-verified 2026-10-09); the tool
        # remaps it onto its original country/region/city/isp/org keys.
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "ip": "8.8.8.8",
                "success": True,
                "country": "United States",
                "region": "California",
                "city": "San Jose",
                "connection": {"isp": "Google LLC", "org": "Google LLC"},
                "latitude": 37.3393939,
                "longitude": -121.8949553,
            },
        )

    monkeypatch.setattr(geo.httpx, "get", _fake_get)
    out = await geo.handle_call_tool("geolocate_ip", {"ip": "8.8.8.8"})
    payload = _payload(out)
    assert payload["country"] == "United States"
    assert payload["isp"] == "Google LLC"
    assert payload["lat"] == 37.3393939
    assert payload["lon"] == -121.8949553
    assert len(seen_urls) == 1
    assert seen_urls[0].startswith("https://")


async def test_batch_refuses_bogons_and_keeps_public(monkeypatch, outbound_calls):
    def _fake_get(url, **kwargs):
        outbound_calls.append(url)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "success": True,
                "country": "United States",
                "connection": {"isp": "Google LLC", "org": "Google LLC"},
                "latitude": 37.3393939,
                "longitude": -121.8949553,
            },
        )

    monkeypatch.setattr(geo.httpx, "get", _fake_get)
    out = await geo.handle_call_tool(
        "geolocate_batch", {"ips": ["8.8.8.8", "10.0.0.1", "example.com"]}
    )
    payload = _payload(out)
    assert payload["count"] == 3  # every input yields an entry, refusals inline
    assert payload["results"][0]["country"] == "United States"
    assert "error" not in payload["results"][0]
    assert payload["results"][1]["error"].startswith("private")
    assert payload["results"][2]["error"].startswith("lookup target must be a literal")
    assert outbound_calls == ["https://ipwho.is/8.8.8.8"]  # https only, one call


async def test_provider_failure_returns_fixed_error(monkeypatch):
    monkeypatch.setattr(
        geo.httpx,
        "get",
        lambda url, **k: SimpleNamespace(status_code=503, json=lambda: {}),
    )
    out = await geo.handle_call_tool("geolocate_ip", {"ip": "8.8.8.8"})
    assert _payload(out) == {"ip": "8.8.8.8", "error": "Lookup failed"}


def test_bogon_reason_vocabulary():
    assert geo.bogon_reason("8.8.8.8") is None
    assert "metadata" in geo.bogon_reason("169.254.169.254")
    assert "RFC1918" in geo.bogon_reason("192.168.0.1")
    assert "loopback" in geo.bogon_reason("127.0.0.1")
