"""KEV refresher: the fetch validates before anything reaches the store.

Fetch and gate only — no server, no database. ``_fetch_kev_entries`` is the
refresher's only gate between a response body and ``upsert_indicators``, so
the shape checks are pinned against a recorded response body, the same checks
``scripts/update_kev_catalog.py`` applies before bundling. The store-level
behaviour (add, expire, failure posture) is pinned against the throwaway
Postgres in test_kev_refresh_db.py.
"""

from __future__ import annotations

import io
import json
import urllib.request

import pytest

from core.config import get_settings
from core.time import utcnow
from services.daemon import threat_feed_poller

pytestmark = pytest.mark.unit


# Recorded entries, byte-shape preserved from the official catalog (the seed's
# spot-check CVE and a Zyxel entry), so the parser is pinned to the
# publisher's shape and not to a tidied copy.
LOG4J = {
    "cveID": "CVE-2021-44228",
    "vendorProject": "Apache",
    "product": "Log4j2",
    "vulnerabilityName": "Apache Log4j2 Remote Code Execution Vulnerability",
    "dateAdded": "2021-12-10",
    "shortDescription": "Apache Log4j2 allows remote code execution via JNDI.",
    "requiredAction": "Apply updates.",
    "dueDate": "2021-12-24",
    "knownRansomwareCampaignUse": "Known",
    "forensicTriage": "No",
    "notes": "https://nvd.nist.gov/vuln/detail/CVE-2021-44228",
    "cwes": ["CWE-20", "CWE-400", "CWE-502"],
}
ZYXEL = {
    "cveID": "CVE-2020-29583",
    "vendorProject": "Zyxel",
    "product": "Multiple Products",
    "vulnerabilityName": "Zyxel Multiple Products Use of Hard-Coded Credentials Vulnerability",
    "dateAdded": "2021-11-03",
    "shortDescription": "Zyxel firewalls contain a use of hard-coded credentials vulnerability.",
    "requiredAction": "Apply updates per vendor instructions.",
    "dueDate": "2022-05-03",
    "knownRansomwareCampaignUse": "Unknown",
    "forensicTriage": "No",
    "notes": "https://nvd.nist.gov/vuln/detail/CVE-2020-29583",
    "cwes": ["CWE-522"],
}


def _recorded_body(entries) -> bytes:
    """A catalog body exactly as the publisher frames it."""
    return json.dumps(
        {
            "title": "CISA Catalog of Known Exploited Vulnerabilities",
            "catalogVersion": "2026.10.08",
            "dateReleased": "2026-10-08T20:09:18.9833Z",
            "count": len(entries),
            "vulnerabilities": entries,
        }
    ).encode("utf-8")


def _serve(monkeypatch, body: bytes) -> None:
    """Answer the fetch with ``body`` — no network."""
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: io.BytesIO(body)
    )


def test_fetch_parses_a_recorded_catalog(monkeypatch):
    _serve(monkeypatch, _recorded_body([LOG4J, ZYXEL]))

    entries = threat_feed_poller._fetch_kev_entries()

    assert [e["cveID"] for e in entries] == ["CVE-2021-44228", "CVE-2020-29583"]
    assert entries[0]["knownRansomwareCampaignUse"] == "Known"


@pytest.mark.parametrize(
    "body",
    [
        b"not json at all",  # a truncated download is not JSON
        json.dumps({"title": "CISA Catalog"}).encode(),  # reshaped: no list
        json.dumps({"vulnerabilities": []}).encode(),  # empty is not an answer
        json.dumps(
            {"vulnerabilities": [LOG4J, {"product": "no cveID"}]}
        ).encode(),  # an entry without a cveID cannot map
    ],
)
def test_a_response_that_fails_validation_raises(monkeypatch, body):
    _serve(monkeypatch, body)

    # JSONDecodeError is a ValueError; the shape checks raise it directly.
    with pytest.raises(ValueError):
        threat_feed_poller._fetch_kev_entries()


@pytest.mark.asyncio
async def test_the_gate_off_skips_the_fetch(monkeypatch):
    monkeypatch.setattr(get_settings(), "vigil_threat_feed_kev_enabled", False)

    def _boom():
        raise AssertionError("the refresher fetched while disabled")

    monkeypatch.setattr(threat_feed_poller, "_fetch_kev_entries", _boom)

    assert await threat_feed_poller.run_kev_refresh_once() == {"skipped": "disabled"}


@pytest.mark.asyncio
async def test_a_refresh_inside_the_window_is_not_due(monkeypatch):
    threat_feed_poller.reset_kev_refresh_check()
    threat_feed_poller._kev_last_refresh = utcnow()

    def _boom():
        raise AssertionError("the refresher fetched inside the daily window")

    monkeypatch.setattr(threat_feed_poller, "_fetch_kev_entries", _boom)

    assert await threat_feed_poller.run_kev_refresh_once() == {"skipped": "not_due"}
