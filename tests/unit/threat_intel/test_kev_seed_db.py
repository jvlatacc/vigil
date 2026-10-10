"""init_database() seeds the bundled KEV catalog, and nothing duplicates it.

Against the throwaway Postgres (a faked session would pass the freshness and
uniqueness checks pointing either way): the throwaway schema is empty, so
init_database() runs on it exactly as it would on a fresh install, and the
fixture deliberately leaves the seeding to the caller.
"""

from __future__ import annotations

import pytest

from core.storage.connection import get_db_manager, init_database
from core.storage.models import ThreatIndicator

pytestmark = [pytest.mark.unit, pytest.mark.external_service, pytest.mark.database]


def _kev_rows():
    with get_db_manager().session_scope() as session:
        return (
            session.query(ThreatIndicator)
            .filter_by(source="cisa_kev", indicator_type="cve")
            .all()
        )


def _kev_count() -> int:
    return len(_kev_rows())


@pytest.fixture(scope="module")
def seeded_store(throwaway_database):
    """init_database() on the empty throwaway schema, once for the module.

    Depends on throwaway_database directly, not only via the autouse marker
    hook: a module fixture instantiates before the function-scoped autouse
    that requests it, and without the explicit dependency the first test's
    setup would call init_database() against an engineless manager.
    """
    from core.threat_intel import kev_seed

    kev_seed.reset_kev_seed_check()
    init_database()
    rows = _kev_rows()
    assert rows, "init_database() seeded no KEV indicators"
    return len(rows)


def test_fresh_init_seeds_the_catalog(seeded_store):
    rows = _kev_rows()
    assert len(rows) == seeded_store

    log4j = next(r for r in rows if r.indicator_value == "CVE-2021-44228")
    assert log4j.source == "cisa_kev"
    assert log4j.indicator_type == "cve"
    assert float(log4j.confidence) == 100.0
    assert log4j.threat_level == "high"
    assert "ransomware" in (log4j.labels or [])
    assert log4j.raw_stix["catalog"] == "cisa_kev"


def test_second_init_adds_no_duplicates(seeded_store):
    init_database()
    assert _kev_count() == seeded_store


def test_second_seed_through_the_upsert_adds_no_duplicates(seeded_store):
    """Idempotence is the upsert's (the UNIQUE triple), not only the guard's."""
    from core.threat_intel import kev_seed

    kev_seed.reset_kev_seed_check()
    assert kev_seed.seed_kev_indicators() == seeded_store
    assert _kev_count() == seeded_store


def test_cve_indicator_is_queryable(seeded_store):
    from core.threat_intel.threat_feed_service import lookup_indicators

    hits = lookup_indicators("cve", ["CVE-2021-44228", "CVE-0000-0"])
    assert "CVE-2021-44228" in hits
    assert hits["CVE-2021-44228"]["source"] == "cisa_kev"
    assert "CVE-0000-0" not in hits  # an unknown CVE is no hit, not an error


def test_cve_entity_keys_roundtrip(seeded_store):
    from core.memory.entity_keys import entity_key, normalise_key

    key = entity_key("cve", "CVE-2021-44228")
    assert key == "cve:cve-2021-44228"
    assert normalise_key("cve:CVE-2021-44228") == key


def test_missing_catalog_is_nonfatal(seeded_store, monkeypatch):
    from core.threat_intel import kev_seed

    kev_seed.reset_kev_seed_check()
    monkeypatch.setattr(
        kev_seed, "CATALOG_PATH", kev_seed.CATALOG_PATH.with_suffix(".missing")
    )
    # Returns 0 and does not raise: startup continues either way.
    assert kev_seed.seed_kev_indicators() == 0
    # The failed attempt touched nothing.
    assert _kev_count() == seeded_store


def test_failed_upsert_is_nonfatal_and_touches_nothing(seeded_store, monkeypatch):
    from core.threat_intel import kev_seed, threat_feed_service

    kev_seed.reset_kev_seed_check()

    def _boom(indicators):
        raise RuntimeError("database gone")

    monkeypatch.setattr(threat_feed_service, "upsert_indicators", _boom)
    assert kev_seed.seed_kev_indicators() == 0
    assert _kev_count() == seeded_store
