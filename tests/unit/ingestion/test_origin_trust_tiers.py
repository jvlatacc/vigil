"""What each importer claims, and what nothing claimed.

The tier is set at ingest, once, by the receiver that verified the
channel: HMAC-verified webhooks stamp ``signed``; credentialed pulls,
bearer-keyed pushes, and the daemon's own pipeline stamp ``transport``;
and a funnel with no claim stamps ``unverified`` — never a guess.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO))

from core.ingestion.ingestion_service import IngestionService  # noqa: E402
from core.ingestion.siem_ingestion_service import SIEMIngestionService  # noqa: E402
from core.storage.origin_trust import (  # noqa: E402
    ORIGIN_DEFAULT,
    ORIGIN_SIGNED,
    ORIGIN_TIERS,
    ORIGIN_TRANSPORT,
    ORIGIN_UNVERIFIED,
    tier_rank,
    trusted_tier,
)

pytestmark = pytest.mark.unit


class _SIEM(SIEMIngestionService):
    """The minimal concrete adapter every SIEM integration extends."""

    async def fetch_alerts(self, start_time=None, end_time=None, limit=100, oldest_first=False):
        return []

    def transform_alert_to_finding(self, alert):
        return None


def test_the_tier_order_is_unverified_transport_signed():
    assert ORIGIN_TIERS == ("unverified", "transport", "signed")
    assert tier_rank(ORIGIN_UNVERIFIED) < tier_rank(ORIGIN_TRANSPORT)
    assert tier_rank(ORIGIN_TRANSPORT) < tier_rank(ORIGIN_SIGNED)


def test_an_unknown_tier_falls_back_to_the_funnel_default():
    assert trusted_tier("not-a-tier", ORIGIN_TRANSPORT) == ORIGIN_TRANSPORT
    assert trusted_tier(None, ORIGIN_TRANSPORT) == ORIGIN_TRANSPORT
    assert trusted_tier("signed", ORIGIN_UNVERIFIED) == ORIGIN_SIGNED


def test_a_credential_backed_pull_adapter_stamps_transport():
    # The base class builds its funnel pre-raised to transport: the channel
    # authenticated the sender even though nothing signed the payload.
    assert _SIEM().ingestion_service.default_origin_trust == ORIGIN_TRANSPORT


def test_a_funnel_with_no_claim_defaults_to_unverified():
    assert IngestionService().default_origin_trust == ORIGIN_UNVERIFIED
    assert ORIGIN_DEFAULT == ORIGIN_UNVERIFIED
