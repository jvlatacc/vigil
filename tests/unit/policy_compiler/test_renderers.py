"""Golden-file tests pinning every renderer to the IR.

Deliberate-regeneration policy: the fixtures under ``renderers/golden/``
are committed snapshots of renderer output. Run with ``UPDATE_GOLDEN=1``
to rewrite them after an intentional format change, inspect the diff, and
commit it — a silent golden drift is a renderer bug, never a test problem.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.policy_compiler.compiler import ArchetypeEvidence, compile_policy
from core.policy_compiler.models import RENDER_TARGETS, PolicyIR
from core.policy_compiler.renderers import UnsupportedRenderTarget, render
from core.policy_compiler.renderers._common import sid_for
from core.policy_compiler.renderers.iptables import chain_name
from tests.unit.policy_compiler.fixtures.sample_ir import sample_evidence

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 9, 20, 0, 0, tzinfo=timezone.utc)

GOLDEN_DIR = Path(__file__).parent / "renderers" / "golden"

# One IR fixture — the compiled sample archetype — rendered to every target.
GOLDEN_FILES = {
    "rego": "sample.rego",
    "snort": "sample.snort",
    "suricata": "sample.suricata",
    "iptables": "sample.iptables",
}


def sample_policy():
    return PolicyIR.from_dict(compile_policy(sample_evidence(), now=NOW).ir)


def blocked_policy():
    """The sample archetype with a containment decision (for action mapping)."""
    evidence = ArchetypeEvidence(
        **{**sample_evidence().__dict__, "observed_recommended_action": "block"}
    )
    return PolicyIR.from_dict(compile_policy(evidence, now=NOW).ir)


@pytest.mark.parametrize("target", sorted(RENDER_TARGETS))
def test_every_supported_target_renders(target):
    assert render(sample_policy(), target)


@pytest.mark.parametrize("target,file_name", sorted(GOLDEN_FILES.items()))
def test_golden_files_pin_render_output(target, file_name):
    actual = render(sample_policy(), target)
    golden = GOLDEN_DIR / file_name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.write_text(actual)
    assert golden.exists(), (
        "missing golden fixture — regenerate deliberately: UPDATE_GOLDEN=1 "
        "pytest tests/unit/policy_compiler/test_renderers.py"
    )
    assert actual == golden.read_text()


@pytest.mark.parametrize("target", sorted(RENDER_TARGETS))
def test_rendering_is_deterministic(target):
    policy = sample_policy()
    assert render(policy, target) == render(policy, target)


def test_an_unknown_target_is_rejected_not_fallback_rendered():
    with pytest.raises(UnsupportedRenderTarget, match="allowed"):
        render(sample_policy(), "crowdstrike-falcon")


# --- The provenance header every artifact carries -------------------------------


@pytest.mark.parametrize("target", sorted(RENDER_TARGETS))
def test_every_artifact_names_the_policy_version_and_hash(target):
    policy = sample_policy()
    artifact = render(policy, target)
    assert f"{policy.policy_id} v{policy.version}" in artifact
    assert policy.content_hash in artifact
    assert policy.match.workflow_id in artifact


def test_the_header_describes_the_full_match_clause():
    artifact = render(sample_policy(), "rego")
    assert "data_source in ['okta.system_log', 'splunk']" in artifact
    assert "techniques any_of ['T1110.003', 'T1110.004']" in artifact
    assert "entity-context types all_of ['src_ip', 'user_account']" in artifact


# --- Rego carries the full predicate tree ----------------------------------------


def test_the_rego_module_mirrors_the_evaluator_semantics():
    module = render(sample_policy(), "rego")
    assert module.startswith("#")
    assert "package vigil.compiled_policies" in module
    # Workflow identity: mismatch fails, absence (undefined) does not.
    assert 'input.workflow_id != "' in module
    # Fail-closed guards on both dynamic fields.
    assert module.count("is_object(input.mitre_predictions)") >= 2
    assert "is_object(input.entity_context)" in module
    # Every alias of the sample's entity types is tried.
    for alias in ("src_ips", "src_ip", "usernames", "username"):
        assert f'"{alias}"' in module
    # The non-empty helper accompanies any entity clause.
    assert "non_empty(value) if" in module


# --- IDS rules carry identity + decision, with the fidelity stated ---------------


def test_snort_and_suricata_differ_and_each_names_its_tool():
    snort = render(sample_policy(), "snort")
    suricata = render(sample_policy(), "suricata")
    assert snort != suricata
    assert "Rendered for Snort" in snort
    assert "Rendered for Suricata" in suricata


def test_a_containment_decision_renders_drop_rules():
    blocked = blocked_policy()
    assert render(blocked, "snort").splitlines()[-1].startswith("drop ip ")
    assert render(blocked, "suricata").splitlines()[-1].startswith("drop ip ")
    iptables_artifact = render(blocked, "iptables")
    assert "-j DROP" in iptables_artifact
    assert chain_name(blocked.policy_id) in iptables_artifact


def test_a_non_containment_decision_renders_no_enforcement_rule():
    assert render(sample_policy(), "snort").splitlines()[-1].startswith("alert ip ")
    iptables_artifact = render(sample_policy(), "iptables")
    assert "-j DROP" not in iptables_artifact
    assert "no rule for iptables to hold" in iptables_artifact


def test_the_sids_are_stable_and_in_the_local_range():
    sid = sid_for(sample_policy().policy_id)
    assert sid == sid_for(sample_policy().policy_id)
    assert 1_000_000 <= sid < 10_000_000


# --- Export digests --------------------------------------------------------------


def test_the_render_digest_is_pinnable_in_the_ir_renders_map():
    digest = (
        "sha256:"
        + hashlib.sha256(render(sample_policy(), "rego").encode("utf-8")).hexdigest()
    )
    assert digest.startswith("sha256:") and len(digest) == 71
