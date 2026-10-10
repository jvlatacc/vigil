"""Bundle model: strict parse, matching, effective tier, revocation."""

from datetime import UTC, datetime

import pytest

from services.edge.gate.tiers import AutonomyTier
from services.edge.policy.model import BundleError, parse_bundle
from services.edge.tests._fixtures import bundle_payload, make_bundle, make_observation

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
AFTER_EXPIRY = datetime(2026, 10, 20, 0, 0, 0, tzinfo=UTC)


def test_spec_example_parses() -> None:
    bundle = make_bundle()
    assert bundle.bundle_id == "edge-pol-vpc-west-gw"
    assert bundle.version == 7
    assert bundle.autonomy_tier is AutonomyTier.TIER_2
    assert bundle.decision.auto_act_confidence == 0.92
    assert len(bundle.allowed_actions) == 3


def test_unknown_top_level_field_refused() -> None:
    with pytest.raises(BundleError, match="unknown bundle field"):
        parse_bundle(bundle_payload(signed_by_extra_field=True))


def test_schema_version_bump_refused() -> None:
    with pytest.raises(BundleError, match="B-SCHEMA-VERSION"):
        parse_bundle(bundle_payload(edge_schema_version=2))


def test_tier_above_v1_ceiling_refused() -> None:
    with pytest.raises(BundleError, match="B-TIER-CEILING"):
        parse_bundle(bundle_payload(autonomy_tier="tier3"))


def test_unknown_tier_label_refused() -> None:
    with pytest.raises(BundleError, match="B-TIER"):
        parse_bundle(bundle_payload(autonomy_tier="autonomy"))


def test_invalid_time_window_refused() -> None:
    with pytest.raises(BundleError, match="B-BOUNDS"):
        parse_bundle(
            bundle_payload(
                not_before="2026-10-16T00:00:00Z", expires_at="2026-10-09T00:00:00Z"
            )
        )


def test_escalate_above_auto_act_refused() -> None:
    decision = bundle_payload()["decision"] | {
        "escalate_confidence": 0.95,
        "auto_act_confidence": 0.90,
    }
    with pytest.raises(BundleError, match="escalate_confidence"):
        parse_bundle(bundle_payload(decision=decision))


def test_confidence_out_of_range_refused() -> None:
    decision = bundle_payload()["decision"] | {"auto_act_confidence": 1.5}
    with pytest.raises(BundleError, match="B-BOUNDS"):
        parse_bundle(bundle_payload(decision=decision))


def test_bad_cidr_ioc_entry_refused() -> None:
    payload = bundle_payload()
    payload["ioc_sets"]["c2-active"]["entries"] = ["not-a-cidr"]
    with pytest.raises(BundleError, match="bad cidr entry"):
        parse_bundle(payload)


def test_rule_referencing_unknown_ioc_set_refused() -> None:
    payload = bundle_payload()
    payload["rules"][0]["match"]["ioc_set"] = "ghost"
    with pytest.raises(BundleError, match="unknown ioc_set"):
        parse_bundle(payload)


def test_unsupported_action_type_refused() -> None:
    payload = bundle_payload()
    payload["allowed_actions"].append(
        {"action_type": "quarantine_file", "executor": "nftables"}
    )
    with pytest.raises(BundleError, match="B-ACTION"):
        parse_bundle(payload)


def test_cidr_match_hits_and_directions_filter() -> None:
    bundle = make_bundle()
    assert bundle.match(make_observation()) is not None  # 203.0.113.55 in /24
    ingress = make_observation(direction="ingress")
    assert bundle.match(ingress) is None  # rule is egress-only
    outside = make_observation(dest_ip="198.51.100.1")
    assert bundle.match(outside) is None  # not in the IOC set


def test_domain_match_matches_subdomain_not_lookalike() -> None:
    payload = bundle_payload()
    payload["rules"] = [
        {
            "rule_id": "c2-dns",
            "match": {
                "direction": "egress",
                "ioc_set": "c2-domains",
                "dest_kind": "domain",
            },
            "severity_floor": "high",
        }
    ]
    payload["ioc_sets"]["c2-domains"] = {
        "kind": "domain",
        "entries": ["evil.example"],
        "source": "ti",
    }
    bundle = parse_bundle(payload)
    hit = bundle.match(
        make_observation(dest_ip=None, dest_domain="beacon.evil.example")
    )
    assert hit is not None
    assert (
        bundle.match(make_observation(dest_ip=None, dest_domain="notevil.example"))
        is None
    )


def test_effective_tier_after_expiry_is_tier0() -> None:
    bundle = make_bundle()
    assert bundle.effective_tier(NOW) is AutonomyTier.TIER_2
    assert bundle.effective_tier(AFTER_EXPIRY) is AutonomyTier.TIER_0
    assert bundle.in_validity(NOW)
    assert not bundle.in_validity(AFTER_EXPIRY)


def test_revocation_precedence_shapes() -> None:
    payload = bundle_payload()
    payload["revocations"] = [{"bundle_id": "edge-pol-other", "version": 3}]
    revoker = parse_bundle(payload)

    payload2 = bundle_payload(bundle_id="edge-pol-other")
    payload2["version"] = 3
    other_v3 = parse_bundle(payload2)
    payload3 = bundle_payload(bundle_id="edge-pol-other")
    payload3["version"] = 9
    other_v9 = parse_bundle(payload3)

    assert revoker.revokes(other_v3)  # exact bundle_id + version
    assert not revoker.revokes(other_v9)  # version pinned, 9 != 3

    payload["revocations"] = [{"bundle_id": "edge-pol-other"}]
    wildcard = parse_bundle(payload)
    assert wildcard.revokes(other_v3) and wildcard.revokes(other_v9)
    assert not wildcard.revokes(make_bundle())  # different bundle_id


def test_scope_label_matching() -> None:
    bundle = make_bundle()
    assert bundle.segment_scope.matches_labels({"vigil.ai/edge-role": "gateway"})
    assert not bundle.segment_scope.matches_labels({"vigil.ai/edge-role": "worker"})


def test_bundle_error_carries_code() -> None:
    with pytest.raises(BundleError) as excinfo:
        parse_bundle(bundle_payload(edge_schema_version=99))
    assert excinfo.value.code == "B-SCHEMA-VERSION"
