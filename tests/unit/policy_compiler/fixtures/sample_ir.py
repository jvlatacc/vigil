"""Shared policy-IR fixtures for the policy_compiler unit tests.

The sample mirrors the spec's canonical IR sample (art_hwuYOmdW): one policy
for the ``wf_hunt_cred_stuffing`` archetype, matched on data source, technique
set, and entity-context types. Builders return fresh objects per call so a
test mutating one cannot leak into another.
"""

from __future__ import annotations

from typing import Any

from core.policy_compiler.models import (
    PolicyIR,
    compute_content_hash,
    validate_ir,
)

WORKFLOW_ID = "wf_hunt_cred_stuffing"
DATA_SOURCES = ["okta.system_log", "splunk"]
TECHNIQUES = ["T1110.003", "T1110.004"]
ENTITY_TYPES = ["src_ip", "user_account"]
COMPILED_AT = "2026-10-09T20:00:00Z"
# Compiler-minted form: pol_ + 16 hex chars (see compiler.archetype_policy_id).
POLICY_ID = "pol_9f2c1a7b3d5e4082"


def sample_match() -> dict[str, Any]:
    return {
        "workflow_id": WORKFLOW_ID,
        "data_source": {"any_of": DATA_SOURCES},
        "techniques": {"any_of": TECHNIQUES},
        "entity_context_types": {"all_of": ENTITY_TYPES},
    }


def sample_decision() -> dict[str, Any]:
    return {
        "severity": "high",
        "confidence": 0.93,
        "recommended_action": "investigate",
        "category": "credential_stuffing",
        "reasoning": (
            "Compiled from 15 completed runs of wf_hunt_cred_stuffing: 14/15 "
            "resolved consistently, no analyst overrides in the 30-day window."
        ),
        "actions_human_only": True,
    }


def sample_maturity() -> dict[str, Any]:
    return {
        "workflow_id": WORKFLOW_ID,
        "window_days": 30,
        "outcomes": {"resolved": 14, "false_positive": 1},
        "consistency": 0.93,
        "analyst_overrides": 0,
    }


def sample_ir_dict() -> dict[str, Any]:
    """The sample document as the compiler emits it — no hash, no renders yet."""
    return {
        "ir_version": 1,
        "policy_id": POLICY_ID,
        "version": 3,
        "state": "candidate",
        "compiled_at": COMPILED_AT,
        "match": sample_match(),
        "decision": sample_decision(),
        "maturity": sample_maturity(),
    }


def hashed_ir_dict() -> dict[str, Any]:
    """The sample document with its content hash attached (the stored form)."""
    ir = sample_ir_dict()
    ir["content_hash"] = compute_content_hash(ir)
    return ir


def sample_policy_ir() -> PolicyIR:
    """The sample policy as a validated typed view."""
    return PolicyIR.from_dict(hashed_ir_dict())


def verified_ir() -> dict[str, Any]:
    """The sample document, canonicalized through validation."""
    return validate_ir(sample_ir_dict())
