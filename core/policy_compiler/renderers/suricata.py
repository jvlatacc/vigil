"""Suricata renderer: the same identity+decision rule as Snort, in Suricata.

Identical scope and honesty rules as the Snort renderer (see its
docstring); the separate renderer exists because the formats are not
byte-compatible and the golden files pin each independently.
"""

from __future__ import annotations

from core.policy_compiler.models import PolicyIR
from core.policy_compiler.renderers._common import (
    BLOCKING_ACTIONS,
    provenance_header,
    sid_for,
)


def render_suricata(policy: PolicyIR) -> str:
    header = provenance_header(policy, tool="Suricata")
    action = (
        "drop" if policy.decision.recommended_action in BLOCKING_ACTIONS else "alert"
    )
    digest_hex = (policy.content_hash or "").removeprefix("sha256:")
    rule = (
        f'{action} ip any any -> any any (msg:"VIGIL {policy.decision.category}'
        f' {policy.policy_id} v{policy.version}";'
        f" metadata:vigil_policy_id {policy.policy_id}, vigil_policy_version"
        f" {policy.version}, vigil_content_hash {digest_hex};"
        f" sid:{sid_for(policy.policy_id)}; rev:{policy.version};)"
    )
    fidelity = (
        "# Fidelity note: Suricata rules match packets, not findings — the"
        " archetype's predicate tree is not expressible here. Matching stays"
        " authoritative in the Vigil evaluator and the exported Rego module;"
        " this rule carries the policy's identity and decision for"
        " correlation."
    )
    return f"{header}\n{fidelity}\n\n{rule}\n"
