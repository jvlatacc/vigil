"""Snort renderer: the policy's identity and decision as an IDS rule.

Snort matches packets; a Vigil policy matches findings. No Snort rule can
test technique predictions or entity-context shapes, so this projection is
deliberately honest about what travels: the policy's id, version, content
hash, and decision ride in msg/metadata for correlation with IDS alerts,
and the rule's action follows the decision (drop only for the actions that
name packet-level containment). Matching itself stays authoritative in the
Vigil evaluator and the exported Rego module — the header comments state
this on every artifact.
"""

from __future__ import annotations

from core.policy_compiler.models import PolicyIR
from core.policy_compiler.renderers._common import (
    BLOCKING_ACTIONS,
    provenance_header,
    sid_for,
)


def render_snort(policy: PolicyIR) -> str:
    header = provenance_header(policy, tool="Snort")
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
        "# Fidelity note: Snort rules match packets, not findings — the"
        " archetype's predicate tree is not expressible here. Matching stays"
        " authoritative in the Vigil evaluator and the exported Rego module;"
        " this rule carries the policy's identity and decision for"
        " correlation."
    )
    return f"{header}\n{fidelity}\n\n{rule}\n"
