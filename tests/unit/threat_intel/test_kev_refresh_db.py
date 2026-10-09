"""The KEV refresher writes through the store exactly as claimed.

Against the throwaway Postgres — a faked session would pass the add, expire
and failure-posture checks pointing either way. The fetch is a recorded
fixture (the seed's spot-check CVE and a Zyxel entry, byte-shape preserved
from the official catalog); no live network in CI.
"""

from __future__ import annotations

import json
import logging

import pytest

from core.storage.models import ThreatIndicator
from services.daemon import threat_feed_poller

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


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


def _kev_rows():
    from core.storage.connection import get_db_manager

    with get_db_manager().session_scope() as session:
        return (
            session.query(ThreatIndicator)
            .filter_by(source="cisa_kev", indicator_type="cve")
            .all()
        )


async def _refresh(monkeypatch, entries):
    """Serve ``entries`` as the fetch and run one refresh; (summary, fetches)."""
    fetches: list = []

    def _fetch():
        fetches.append(len(entries))
        return json.loads(json.dumps(entries))

    monkeypatch.setattr(threat_feed_poller, "_fetch_kev_entries", _fetch)
    summary = await threat_feed_poller.run_kev_refresh_once()
    return summary, fetches


@pytest.fixture
def clean_store(throwaway_database):
    """The cisa_kev slice starts (and ends) empty.

    Depends on throwaway_database directly, not only via the autouse marker
    hook, for the reason test_kev_seed_db.py records: the explicit dependency
    guarantees the manager is retargeted before the first store read.
    """
    from core.storage.connection import get_db_manager

    def _clear():
        with get_db_manager().session_scope() as session:
            session.query(ThreatIndicator).filter_by(source="cisa_kev").delete()

    _clear()
    threat_feed_poller.reset_kev_refresh_check()
    yield
    _clear()
    threat_feed_poller.reset_kev_refresh_check()


@pytest.mark.asyncio
async def test_a_fetched_entry_lands_in_the_store_through_the_shared_mapper(
    clean_store, monkeypatch
):
    summary, fetches = await _refresh(monkeypatch, [LOG4J])

    assert fetches == [1]
    assert summary["seen"] == 1
    assert summary["inserted"] == 1
    assert summary["expired"] == 0

    rows = _kev_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.indicator_value == "CVE-2021-44228"
    assert row.source == "cisa_kev"
    assert row.indicator_type == "cve"
    assert float(row.confidence) == 100.0
    assert row.threat_level == "high"
    assert "ransomware" in (row.labels or [])
    assert row.valid_until is None
    assert row.raw_stix["catalog"] == "cisa_kev"
    assert row.raw_stix["dueDate"] == "2021-12-24"


@pytest.mark.asyncio
async def test_an_entry_removed_from_the_catalog_expires_and_is_never_deleted(
    clean_store, monkeypatch
):
    await _refresh(monkeypatch, [LOG4J, ZYXEL])
    # Each refresh is its own day; without forgetting the watermark the second
    # run would skip as not_due and never see the smaller catalog.
    threat_feed_poller.reset_kev_refresh_check()

    summary, _ = await _refresh(monkeypatch, [LOG4J])
    assert summary["expired"] == 1

    rows = _kev_rows()
    assert len(rows) == 2  # the row stays; only its validity ends
    by_value = {r.indicator_value: r for r in rows}
    assert by_value["CVE-2020-29583"].valid_until is not None
    assert by_value["CVE-2021-44228"].valid_until is None

    from core.threat_intel.threat_feed_service import lookup_indicators

    hits = lookup_indicators("cve", ["CVE-2021-44228", "CVE-2020-29583"])
    assert set(hits) == {"CVE-2021-44228"}


@pytest.mark.asyncio
async def test_a_republished_entry_becomes_live_again(clean_store, monkeypatch):
    await _refresh(monkeypatch, [LOG4J, ZYXEL])
    threat_feed_poller.reset_kev_refresh_check()
    await _refresh(monkeypatch, [LOG4J])
    threat_feed_poller.reset_kev_refresh_check()
    await _refresh(monkeypatch, [LOG4J, ZYXEL])

    by_value = {r.indicator_value: r for r in _kev_rows()}
    assert by_value["CVE-2020-29583"].valid_until is None


@pytest.mark.asyncio
async def test_a_failed_fetch_leaves_the_store_intact_and_logs(
    clean_store, monkeypatch, caplog
):
    await _refresh(monkeypatch, [LOG4J, ZYXEL])
    threat_feed_poller.reset_kev_refresh_check()

    def _dead():
        raise RuntimeError("cisa.gov unreachable")

    monkeypatch.setattr(threat_feed_poller, "_fetch_kev_entries", _dead)
    with caplog.at_level(logging.ERROR, logger="services.daemon.threat_feed_poller"):
        summary = await threat_feed_poller.run_kev_refresh_once()

    assert summary.get("error") == "cisa.gov unreachable"
    assert "KEV refresh failed" in caplog.text

    rows = _kev_rows()
    assert {r.indicator_value for r in rows} == {
        "CVE-2021-44228",
        "CVE-2020-29583",
    }
    assert all(r.valid_until is None for r in rows)
    # The watermark did not advance: the next tick retries the fetch.
    assert threat_feed_poller._kev_last_refresh is None


@pytest.mark.asyncio
async def test_a_second_call_the_same_day_does_not_fetch(clean_store, monkeypatch):
    summary, fetches = await _refresh(monkeypatch, [LOG4J])
    second = await threat_feed_poller.run_kev_refresh_once()

    assert summary["seen"] == 1
    assert second == {"skipped": "not_due"}
    assert fetches == [1]
