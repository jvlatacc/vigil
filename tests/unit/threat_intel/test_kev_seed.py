"""KEV catalog entries map onto NormalizedIndicator exactly as specified.

Mapping only — no server. The write path (upsert, init, idempotence) is
pinned against the throwaway Postgres in test_kev_seed_db.py; a faked session
here would pass it pointing either way.
"""

from __future__ import annotations

import json
import re

import pytest

from core.threat_intel import kev_seed
from core.threat_intel.threat_feed_service import NormalizedIndicator

pytestmark = pytest.mark.unit

# Real fields of a real catalog entry (the spec's spot-check CVE), so the
# mapping is pinned to the publisher's shape and not to a tidied copy.
LOG4J = {
    "cveID": "CVE-2021-44228",
    "cwes": ["CWE-20", "CWE-400", "CWE-502"],
    "dateAdded": "2021-12-10",
    "dueDate": "2021-12-24",
    "forensicTriage": "No",
    "knownRansomwareCampaignUse": "Known",
    "notes": "https://nvd.nist.gov/vuln/detail/CVE-2021-44228",
    "product": "Log4j2",
    "requiredAction": "Apply updates.",
    "shortDescription": "Apache Log4j2 allows remote code execution via JNDI.",
    "vendorProject": "Apache",
    "vulnerabilityName": "Apache Log4j2 Remote Code Execution Vulnerability",
}


def test_kev_entry_maps_per_the_spec():
    ind = kev_seed.kev_entry_to_indicator(LOG4J)

    assert isinstance(ind, NormalizedIndicator)
    assert ind.indicator_type == "cve"
    assert ind.indicator_value == "CVE-2021-44228"  # published upper-case form
    assert ind.source == "cisa_kev"
    assert ind.collection_id is None
    assert ind.confidence == 100.0  # authoritative, on the STIX 0..100 scale
    assert ind.threat_level == "high"
    assert ind.labels == ["Apache", "Log4j2", "ransomware"]
    assert ind.valid_from is not None and ind.valid_from.year == 2021
    assert ind.valid_until is None
    assert ind.raw_stix["catalog"] == "cisa_kev"
    assert ind.raw_stix["vulnerabilityName"] == LOG4J["vulnerabilityName"]
    assert ind.raw_stix["dueDate"] == "2021-12-24"
    assert ind.raw_stix["notes"] == LOG4J["notes"]
    assert ind.raw_stix["knownRansomwareCampaignUse"] == "Known"


def test_not_ransomware_has_no_ransomware_label():
    entry = {**LOG4J, "knownRansomwareCampaignUse": "Unknown"}
    ind = kev_seed.kev_entry_to_indicator(entry)
    assert "ransomware" not in ind.labels
    assert ind.labels == ["Apache", "Log4j2"]


def test_missing_or_odd_dates_become_none():
    ind = kev_seed.kev_entry_to_indicator({**LOG4J, "dateAdded": "not-a-date"})
    assert ind.valid_from is None
    ind = kev_seed.kev_entry_to_indicator({**LOG4J, "dateAdded": None})
    assert ind.valid_from is None
    ind = kev_seed.kev_entry_to_indicator(
        {k: v for k, v in LOG4J.items() if k != "dateAdded"}
    )
    assert ind.valid_from is None


def test_bundled_catalog_maps_whole():
    """Every entry of the shipped catalog maps, in canonical form, unmodified.

    Reads only the bundled file — no network in tests.
    """
    catalog = json.loads(kev_seed.CATALOG_PATH.read_text(encoding="utf-8"))
    entries = catalog["vulnerabilities"]
    assert entries, "bundled catalog has no entries"

    indicators = [kev_seed.kev_entry_to_indicator(e) for e in entries]
    assert len(indicators) == len(entries)
    assert all(i.indicator_type == "cve" for i in indicators)
    assert all(
        re.fullmatch(r"CVE-\d{4}-\d+", i.indicator_value) for i in indicators
    ), "a cveID is not in the published CVE-YYYY-NNNN form"
    # The UNIQUE triple would skip a duplicate at upsert; catch it here too.
    assert len({i.indicator_value for i in indicators}) == len(indicators)

    log4j = next(i for i in indicators if i.indicator_value == "CVE-2021-44228")
    assert "ransomware" in log4j.labels
