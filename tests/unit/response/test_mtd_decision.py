"""The honey-routing decision, gate by gate: every refusal names its rule.

``mtd_route_decision`` is the deception sibling of ``response_action_decision``:
a pure function over verb, confidence, destination, config and exclusion that
either proposes ``honey_route`` or names the rule it refused on. Disabled is
tested first — with MTD off every input refuses on ``mtd.enabled`` and the
isolate/block bands are never consulted, because a refusal routes nothing and
the probe falls back to the normal response path.
"""

import pytest

from core.response.config import MtdConfig, mtd_route_decision

pytestmark = pytest.mark.unit

INTERNAL_IP = "10.0.0.53"
PUBLIC_IP = "8.8.8.8"


def _config(**overrides) -> MtdConfig:
    values = dict(
        enabled=True,
        confidence_floor=0.60,
        session_ttl_seconds=3600,
        internal_destinations_only=True,
    )
    values.update(overrides)
    return MtdConfig(**values)


# --- the default-off gate -----------------------------------------------------


@pytest.mark.parametrize(
    "recommended, confidence, dest_ip, is_excluded",
    [
        ("deceive", 0.95, INTERNAL_IP, False),  # every other gate would pass
        ("deceive", 0.95, INTERNAL_IP, True),
        ("isolate", 0.95, PUBLIC_IP, False),
        ("deceive", 0.10, None, False),
    ],
)
def test_disabled_every_input_refuses_on_mtd_enabled(
    recommended, confidence, dest_ip, is_excluded
):
    # Default-off is bit-for-bit: nothing about the probe matters before
    # the feature itself does.
    action, rule = mtd_route_decision(
        recommended, confidence, dest_ip, MtdConfig(enabled=False), is_excluded
    )
    assert action is None
    assert rule == "mtd.enabled=False"


# --- the destination gate -----------------------------------------------------


def test_a_probe_with_no_destination_is_not_a_candidate():
    action, rule = mtd_route_decision("deceive", 0.95, None, _config(), False)
    assert action is None
    assert rule == "mtd.dest_not_internal=None"


@pytest.mark.parametrize("dest", [PUBLIC_IP, "1.2.3.4", "2606:4700:4700::1111", "not-an-ip"])
def test_a_public_or_unparseable_destination_is_not_internal(dest):
    action, rule = mtd_route_decision("deceive", 0.95, dest, _config(), False)
    assert action is None
    assert rule == f"mtd.dest_not_internal={dest}"


@pytest.mark.parametrize(
    "dest",
    [
        "10.0.0.53",
        "172.16.4.9",
        "192.168.1.20",
        "127.0.0.1",
        "169.254.7.7",
        "fd00::53",
    ],
)
def test_private_loopback_and_link_local_destinations_are_internal(dest):
    action, rule = mtd_route_decision("deceive", 0.95, dest, _config(), False)
    assert action == "honey_route"
    assert rule == "mtd.confidence_floor met=0.60 met (0.95)"


def test_relaxing_the_internal_gate_lets_public_destinations_through():
    # internal-only off is an operator's explicit opt-out of the destination
    # gate; the exclusion and verb gates still stand behind it.
    action, _ = mtd_route_decision(
        "deceive", 0.95, PUBLIC_IP, _config(internal_destinations_only=False), False
    )
    assert action == "honey_route"


# --- the exclusion gate -------------------------------------------------------


def test_an_excluded_destination_is_never_routed():
    action, rule = mtd_route_decision("deceive", 0.95, INTERNAL_IP, _config(), True)
    assert action is None
    assert rule == f"mtd.exclusion_list={INTERNAL_IP}"


def test_exclusion_is_decided_before_the_verb_gate():
    # Where the probe was aimed is audited before what was recommended: an
    # excluded host reads its own refusal even on a non-deceive verb.
    action, rule = mtd_route_decision("isolate", 0.95, INTERNAL_IP, _config(), True)
    assert action is None
    assert rule.startswith("mtd.exclusion_list")


# --- the verb gate ------------------------------------------------------------


@pytest.mark.parametrize(
    "verb", ["isolate", "block", "investigate", "monitor", "dismiss", ""]
)
def test_only_the_deceive_verb_is_a_routing_candidate(verb):
    # Containment verbs stay containment: honey-routing never fires because
    # a triage reply wanted a host isolated or an IP blocked.
    action, rule = mtd_route_decision(verb, 0.95, INTERNAL_IP, _config(), False)
    assert action is None
    assert rule == f"mtd.no_deceive_verb={verb}"


# --- the confidence gates -----------------------------------------------------


@pytest.mark.parametrize("confidence", [1.01, 5.0, 42.0, -0.5, float("nan")])
def test_a_confidence_that_is_not_a_probability_refuses(confidence):
    # The range guard, same as the approval gate: a number outside [0, 1]
    # is a caller inflating the figure and must not read as "above the
    # floor".
    action, rule = mtd_route_decision(
        "deceive", confidence, INTERNAL_IP, _config(), False
    )
    assert action is None
    assert rule.startswith("mtd.confidence_range")


def test_below_the_floor_refuses_on_the_floor():
    action, rule = mtd_route_decision("deceive", 0.59, INTERNAL_IP, _config(), False)
    assert action is None
    assert rule == "mtd.confidence_floor=0.60 not met (0.59)"


def test_at_the_floor_routes():
    # The floor is a >= floor: the boundary is a candidate, not a refusal.
    action, rule = mtd_route_decision("deceive", 0.60, INTERNAL_IP, _config(), False)
    assert action == "honey_route"
    assert rule == "mtd.confidence_floor met=0.60 met (0.60)"


def test_the_floor_reports_the_operators_number():
    action, rule = mtd_route_decision(
        "deceive", 0.80, INTERNAL_IP, _config(confidence_floor=0.75), False
    )
    assert action == "honey_route"
    assert rule == "mtd.confidence_floor met=0.75 met (0.80)"


def test_a_high_confidence_probe_of_an_internal_host_routes():
    action, rule = mtd_route_decision("deceive", 0.95, INTERNAL_IP, _config(), False)
    assert action == "honey_route"
    assert rule == "mtd.confidence_floor met=0.60 met (0.95)"
