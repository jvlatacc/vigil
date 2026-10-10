"""Renderers: project a compiled policy IR to external enforcement formats.

The IR is the canonical artifact and the Vigil evaluator is its engine;
these projections carry the same decision into tooling that cannot run
Python — an OPA deployment, an IDS tier, an edge firewall. Two honesty
rules bind every renderer:

1. **Determinism** — a pure function of the IR document; golden fixtures
   pin the output of each format (regenerate deliberately, never silently).
2. **No silent fallback** — an unknown target raises rather than rendering
   something else. The compile validation gate already rejects render
   targets outside RENDER_TARGETS, so a bad target never gets this far;
   the check here is defense in depth, not the primary gate.

Fidelity differs by format and says so in its own header: Rego carries the
full predicate tree (semantics mirroring evaluator.py); the packet formats
(Snort/Suricata/iptables) match packets, not findings, so they carry the
policy's identity, decision, and documentation — matching stays
authoritative in Vigil.
"""

from __future__ import annotations

from typing import Callable

from core.policy_compiler.models import RENDER_TARGETS, PolicyIR
from core.policy_compiler.renderers.iptables import render_iptables
from core.policy_compiler.renderers.rego import render_rego
from core.policy_compiler.renderers.snort import render_snort
from core.policy_compiler.renderers.suricata import render_suricata

Renderer = Callable[[PolicyIR], str]

RENDERERS: dict[str, Renderer] = {
    "rego": render_rego,
    "snort": render_snort,
    "suricata": render_suricata,
    "iptables": render_iptables,
}


class UnsupportedRenderTarget(ValueError):
    """A render target outside RENDER_TARGETS was requested.

    Raised instead of rendering a fallback: an export that says "rego" but
    contains something else is a corrupted audit trail, not a convenience.
    """


def render(policy: PolicyIR, target: str) -> str:
    """Project the policy to the named target format."""
    if target not in RENDER_TARGETS:
        raise UnsupportedRenderTarget(
            f"render target {target!r} is not one the renderer set can"
            f" represent (allowed: {list(RENDER_TARGETS)})"
        )
    return RENDERERS[target](policy)
