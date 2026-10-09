"""AC1 — the deterministic recon predicate: evidence, never triage guesses.

Covers the pure halves (recon shape, canonicalization, ports) here; the
corroboration count over the durable probe log is covered DB-backed in
test_lease_sweep.py, and end-to-end through the processor's queueing arm.
"""

import pytest

from tests.unit.deception.fixtures import (
    ATTACKER,
    VICTIM,
    FakeProbeSignals,
    recon_finding,
)

from core.deception.allowlist import Allowlist
from core.deception.signals import (
    canonical_source_ip,
    deception_signal_for_finding,
    destination_ips,
    extract_ports,
    is_recon_shaped,
    recon_evidence,
    recon_tids,
    routable_ip,
)

pytestmark = pytest.mark.unit


class TestReconShape:
    def test_a_recon_tid_names_the_phase(self):
        assert is_recon_shaped(recon_finding()) is True

    def test_a_lateral_movement_category_names_the_phase(self):
        finding = recon_finding(mitre_predictions={}, category="lateral_movement")
        assert is_recon_shaped(finding) is True

    def test_a_recon_subtechnique_matches_through_its_base_id(self):
        finding = recon_finding(mitre_predictions={"T1595.003": 0.7}, category="malware")
        assert is_recon_shaped(finding) is True

    def test_recon_tids_accepts_list_and_string_shapes(self):
        assert recon_tids(recon_finding(mitre_predictions=["T1046", "T1486"])) == {"T1046"}
        assert recon_tids(recon_finding(mitre_predictions="t1046")) == {"T1046"}

    def test_non_recon_evidence_is_not_recon_shaped(self):
        finding = recon_finding(
            mitre_predictions={"T1486": 0.99}, category="ransomware"  # ransomware
        )
        assert is_recon_shaped(finding) is False

    def test_no_evidence_at_all_is_not_recon_shaped(self):
        finding = recon_finding(mitre_predictions=None, category=None)
        finding.pop("mitre_predictions", None)
        assert is_recon_shaped(finding) is False

    def test_triage_output_alone_is_never_evidence(self):
        """The AI-triage fields the old rule trusted carry no recon signal."""
        finding = recon_finding(mitre_predictions=None, category=None)
        finding["recommended_action"] = "isolate"  # the model's guess
        finding["severity"] = "critical"
        assert is_recon_shaped(finding) is False


class TestCanonicalSourceIp:
    def test_a_list_valued_src_ips_yields_its_first_address(self):
        assert canonical_source_ip(recon_finding()) == ATTACKER

    def test_a_scalar_src_ip_is_accepted(self):
        finding = recon_finding(
            entity_context={"src_ip": ATTACKER, "dst_ips": [VICTIM]}
        )
        assert canonical_source_ip(finding) == ATTACKER

    def test_the_source_shaped_keys_are_preferred_over_source_ip(self):
        finding = recon_finding(
            entity_context={"src_ips": [ATTACKER], "source_ip": "198.51.100.1"}
        )
        assert canonical_source_ip(finding) == ATTACKER

    def test_dst_keys_never_name_the_attacker(self):
        finding = recon_finding(entity_context={"dst_ips": [ATTACKER]})
        assert canonical_source_ip(finding) is None

    def test_unroutable_addresses_are_dropped(self):
        for bad in ("127.0.0.1", "169.254.1.1", "224.0.0.5", "0.0.0.0", "240.0.0.1"):
            finding = recon_finding(entity_context={"src_ips": [bad]})
            assert canonical_source_ip(finding) is None, bad

    def test_an_ipv4_mapped_ipv6_address_is_normalized(self):
        finding = recon_finding(entity_context={"src_ips": ["::ffff:203.0.113.7"]})
        assert canonical_source_ip(finding) == ATTACKER

    def test_garbage_finds_nothing(self):
        assert canonical_source_ip(recon_finding(entity_context="junk")) is None
        assert canonical_source_ip(recon_finding(entity_context={"src_ips": ["n/a"]})) is None


class TestDestinationsAndPorts:
    def test_destination_ips_reads_the_dst_keys(self):
        assert destination_ips(recon_finding()) == [VICTIM]

    def test_extract_ports_drops_the_implausible(self):
        finding = recon_finding(
            entity_context={"src_ips": [ATTACKER], "ports": [445, "3389", 0, 70000, "http"]}
        )
        assert extract_ports(finding) == [445, 3389]

    def test_extract_ports_falls_back_to_the_finding_body(self):
        finding = recon_finding()
        finding.pop("entity_context")
        finding["ports"] = 22
        assert extract_ports(finding) == [22]

    def test_recon_evidence_names_what_the_predicate_saw(self):
        evidence = recon_evidence(recon_finding())
        assert evidence["tids"] == ["T1018", "T1046"]
        assert evidence["category"] == "recon"
        assert evidence["destination_ips"] == [VICTIM]
        assert evidence["ports"] == [445, 3389]


class TestThePredicate:
    def _predicate(self, finding, *, config=None, allowlist=None, signals=None):
        config = config or FakeProbeSignals().config
        return deception_signal_for_finding(
            finding,
            signals=signals or FakeProbeSignals(config),
            allowlist=allowlist or Allowlist(),
        )

    def test_a_disabled_posture_never_fires(self):
        from core.deception.config import DeceptionConfig

        signals = FakeProbeSignals(DeceptionConfig(enabled=False))
        assert deception_signal_for_finding(
            recon_finding(), signals=signals, allowlist=Allowlist()
        ) is False

    def test_the_kill_switch_refuses_even_a_corroborated_source(self):
        from core.deception.config import DeceptionConfig

        signals = FakeProbeSignals(DeceptionConfig(enabled=True), kill_switch=True)
        assert deception_signal_for_finding(
            recon_finding(), signals=signals, allowlist=Allowlist()
        ) is False

    def test_a_non_recon_finding_never_fires(self):
        assert self._predicate(recon_finding(category="malware", mitre_predictions={})) is False

    def test_a_sourceless_finding_never_fires(self):
        assert self._predicate(recon_finding(entity_context={})) is False

    def test_an_exempt_source_never_fires_and_never_accumulates_probes(self):
        allowlist = Allowlist(f"{ATTACKER}/32")
        signals = FakeProbeSignals()
        assert deception_signal_for_finding(
            recon_finding(), signals=signals, allowlist=allowlist
        ) is False
        assert signals.recorded == []

    def test_a_corroborated_recon_source_fires(self):
        signals = FakeProbeSignals(FakeProbeSignals().config, corroborated=True)
        assert deception_signal_for_finding(
            recon_finding(), signals=signals, allowlist=Allowlist()
        ) is True

    def test_every_qualifying_finding_records_one_probe(self):
        signals = FakeProbeSignals(FakeProbeSignals().config, corroborated=False)
        assert deception_signal_for_finding(
            recon_finding(), signals=signals, allowlist=Allowlist()
        ) is False  # below the corroboration floor...
        assert len(signals.recorded) == 1  # ...but still counted as evidence


def test_routable_ip_normalizes_and_refuses():
    assert routable_ip(" 203.0.113.7 ") == ATTACKER
    assert routable_ip("::ffff:10.0.4.25") == VICTIM
    assert routable_ip("not an ip") is None
    assert routable_ip(None) is None
