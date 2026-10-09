"""iptables renderer: a ruleset fragment for the decision's enforcement.

iptables matches packets; a Vigil policy matches findings — the archetype's
predicate tree has no packet-level form. For a policy whose decision names
containment (isolate/block), the fragment prepares the chain the enforcement
integration populates from APPROVED containment actions (never from the
policy itself — the address set is a response-pipeline artifact). Any other
decision renders a comment-only fragment: there is nothing for iptables to
do, and the artifact says so instead of inventing a rule.
"""

from __future__ import annotations

from core.policy_compiler.models import PolicyIR
from core.policy_compiler.renderers._common import (
    BLOCKING_ACTIONS,
    provenance_header,
)


def chain_name(policy_id: str) -> str:
    """A deterministic chain name derived from the policy id.

    iptables caps chain names at 30 characters (28 in some tables), so the
    name drops the pol_ prefix and uppercases the id part: 16 hex
    characters give VIGIL_POL_<16> = 26.
    """
    return "VIGIL_POL_" + policy_id.removeprefix("pol_").upper()


def render_iptables(policy: PolicyIR) -> str:
    header = provenance_header(policy, tool="iptables")
    if policy.decision.recommended_action not in BLOCKING_ACTIONS:
        note = (
            "# Fidelity note: this decision carries no packet-level"
            " containment — there is no rule for iptables to hold. The Vigil"
            " evaluator decides; approved containment actions name any"
            " addresses an enforcement integration would install."
        )
        return f"{header}\n{note}\n"
    chain = chain_name(policy.policy_id)
    lines = [
        header,
        (
            "# Fidelity note: the predicate tree is not expressible in"
            " iptables — matching stays authoritative in the Vigil evaluator"
            " and the exported Rego module."
        ),
        (
            f"# Populate {chain} from APPROVED containment actions only"
            " (response pipeline / ApprovalService), never from this policy:"
        ),
        f"-N {chain}",
        (
            f"-A {chain} -m comment --comment"
            f' "vigil:{policy.policy_id}:v{policy.version}" -j DROP'
        ),
        "",
        "# Wire the chain into your ingress path explicitly, e.g.:",
        f"# -I INPUT -j {chain}",
    ]
    return "\n".join(lines) + "\n"
