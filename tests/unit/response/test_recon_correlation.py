"""The correlator's recon branch: T1046/T1595 findings get a small boost
and a DECEIVE recommendation below the review line, while the containment
bands keep precedence and everything else is untouched."""

import pytest

from core.response.autonomous_response_service import AutonomousResponseService
from core.response.config import ResponseConfig

pytestmark = pytest.mark.unit


def _correlate(mitre_predictions):
    service = AutonomousResponseService()
    finding = {
        "finding_id": "f-recon",
        "severity": "medium",
        "mitre_predictions": mitre_predictions,
        "entity_context": {"src_ips": ["203.0.113.7"]},
    }
    return service.correlate_alerts(tempo_flow_alert=finding)


def test_a_t1046_probe_gets_the_recon_boost():
    correlation = _correlate({"T1046": "Network Service Scanning"})
    assert correlation["confidence"] == pytest.approx(0.10)
    assert "recon_scanning" in correlation["indicators"]


def test_a_t1595_subtechnique_boosts_too():
    correlation = _correlate({"T1595.002": "Vulnerability Scanning"})
    assert correlation["confidence"] == pytest.approx(0.10)
    assert "recon_scanning" in correlation["indicators"]


def test_non_scanning_tags_get_no_recon_boost():
    correlation = _correlate({"T1110": "Brute Force"})
    assert correlation["confidence"] == pytest.approx(0.0)
    assert "recon_scanning" not in correlation["indicators"]


def test_boosts_add_with_the_existing_branches():
    """Recon rides beside the established boosts, capped at 1.0 as before."""
    correlation = _correlate(
        {"T1046": "Network Service Scanning", "T1486": "Data Encrypted for Impact"}
    )
    assert correlation["confidence"] == pytest.approx(0.35)


class TestTheRecommendationLadder:
    """The ladder keeps containment in front and reads recon as deceive
    only below the review line."""

    def setup_method(self):
        self.service = AutonomousResponseService(
            approvals=None, config=ResponseConfig()
        )

    def test_a_recon_probe_below_the_review_line_recommends_deceiving(self):
        recommendation = self.service._get_recommendation(0.65, ["recon_scanning"])
        assert recommendation.startswith("DECEIVE")

    def test_containment_keeps_precedence(self):
        assert self.service._get_recommendation(0.95, ["recon_scanning"]).startswith(
            "AUTO-ISOLATE"
        )
        assert self.service._get_recommendation(0.86, ["recon_scanning"]).startswith(
            "ISOLATE WITH APPROVAL"
        )

    def test_without_the_indicator_the_bands_are_untouched(self):
        assert self.service._get_recommendation(0.65, []).startswith("MONITOR")
