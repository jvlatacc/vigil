"""Bundled CISA KEV catalog as the t=0 threat-indicator seed.

A fresh install boots with an empty ``threat_indicators`` store, so the agents
that check indicators against authoritative sources have nothing to check until
an operator configures a feed. This module loads the CISA Known Exploited
Vulnerabilities catalog shipped at ``data/threat_intel/cisa-kev/catalog.json``
— U.S. Government published data, attribution retained (see that folder's
README) — into the store at database init, through the same
``upsert_indicators`` path the feed poller uses, so bundled and refreshed rows
cannot drift apart.

Seeding is idempotent (the ``UNIQUE (source, indicator_type, indicator_value)``
triple) and never fatal: a missing or malformed catalog is logged and startup
continues, matching the poller's degraded-mode philosophy. A future feed source
in the poller reuses :func:`kev_entry_to_indicator` to stay byte-identical with
this seed; the freshness work (fetching, expiring removals) belongs to the
poller, not to this init-time seed.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.threat_intel.threat_feed_service import NormalizedIndicator

logger = logging.getLogger(__name__)

# Anchored to the source tree rather than the working directory: a source
# install may not launch from the repo root, and both Docker images copy
# data/ to /app/data (infra/docker/Dockerfile.{backend,daemon}).
REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "data" / "threat_intel" / "cisa-kev" / "catalog.json"

# The catalog's own vocabulary, spelled once so the poller's refresher and any
# caller agree on what landed in the store.
SOURCE = "cisa_kev"

# Every KEV entry is a vulnerability CISA has confirmed exploited in the wild,
# so the level is a constant rather than a judgement.
THREAT_LEVEL = "high"

# Matches the drift check's retry window (core.storage.connection): a failed
# seed is retried on a later init, not spun on in a loop.
_RETRY_AFTER_SECONDS = 30.0


def _parse_date(value: Any) -> Optional[datetime]:
    """A KEV ``dateAdded``/``dueDate`` (``YYYY-MM-DD``) as a naive UTC datetime.

    The columns hold UTC without offsets (``threat_feed_service._parse_dt``
    strips them the same way). Unparseable or missing dates become ``None`` —
    one odd entry is not worth failing a 1,700-row seed over.
    """
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def kev_entry_to_indicator(entry: Dict[str, Any]) -> NormalizedIndicator:
    """Map one KEV catalog entry to a NormalizedIndicator.

    ``cveID`` is stored in its published upper-case ``CVE-YYYY-NNNN`` form —
    the canonical value everywhere exact-value lookups happen.
    """
    ransomware = entry.get("knownRansomwareCampaignUse") == "Known"
    labels = [
        str(part) for part in (entry.get("vendorProject"), entry.get("product")) if part
    ]
    if ransomware:
        labels.append("ransomware")
    return NormalizedIndicator(
        indicator_type="cve",
        indicator_value=entry["cveID"],
        source=SOURCE,
        collection_id=None,
        # The catalog is authoritative. The column is STIX's 0..100 scale, so
        # certainty is 100, not 1.
        confidence=100.0,
        threat_level=THREAT_LEVEL,
        labels=labels,
        valid_from=_parse_date(entry.get("dateAdded")),
        valid_until=None,
        raw_stix={
            "catalog": SOURCE,
            "vendorProject": entry.get("vendorProject"),
            "product": entry.get("product"),
            "vulnerabilityName": entry.get("vulnerabilityName"),
            "dateAdded": entry.get("dateAdded"),
            "dueDate": entry.get("dueDate"),
            "knownRansomwareCampaignUse": entry.get("knownRansomwareCampaignUse"),
            "notes": entry.get("notes"),
        },
    )


_kev_seed_done: set[str] = set()
_kev_seed_failed_at: Dict[str, float] = {}
_kev_seed_lock = threading.Lock()


def reset_kev_seed_check() -> None:
    """Forget which databases have been seeded. For tests."""
    with _kev_seed_lock:
        _kev_seed_done.clear()
        _kev_seed_failed_at.clear()


def _seed_now() -> int:
    """Read the catalog, map every entry, and upsert the batch. Raises."""
    entries = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["vulnerabilities"]
    indicators = [kev_entry_to_indicator(entry) for entry in entries]
    # Deferred like every write in threat_feed_service: storage imports at
    # module load would make this module order-sensitive at init time.
    from core.threat_intel.threat_feed_service import upsert_indicators

    upsert_indicators(indicators)
    return len(indicators)


def seed_kev_indicators() -> int:
    """Load the bundled KEV catalog through ``upsert_indicators`` (idempotent).

    Once per database per process: ``init_database()`` runs on every
    DatabaseDataService construction, and re-reading the catalog each time buys
    nothing — the poller's refresher is what keeps rows current afterwards.

    Returns the number of rows offered to the store, or 0 when the seed already
    ran on this database, failed, or had nothing to load. Never raises: a
    missing or unreadable catalog, or a database hiccup, is logged and startup
    continues — an empty t=0 store is bad, but an install that cannot boot is
    worse.
    """
    try:
        from core.storage.connection import get_db_manager

        manager = get_db_manager()
    except Exception as e:  # noqa: BLE001
        logger.error("KEV seed skipped (database unavailable): %s", e)
        return 0
    if manager.engine is None:
        return 0
    key = manager.engine.url.render_as_string(hide_password=True)

    with _kev_seed_lock:
        if key in _kev_seed_done:
            return 0
        failed_at = _kev_seed_failed_at.get(key)
        if (
            failed_at is not None
            and time.monotonic() - failed_at < _RETRY_AFTER_SECONDS
        ):
            return 0
        try:
            count = _seed_now()
        except Exception as e:  # noqa: BLE001
            _kev_seed_failed_at[key] = time.monotonic()
            logger.error("KEV seed failed (%s); startup continues: %s", CATALOG_PATH, e)
            return 0
        _kev_seed_done.add(key)
        _kev_seed_failed_at.pop(key, None)

    logger.info("Seeded %d CISA KEV indicators from %s", count, CATALOG_PATH)
    return count
