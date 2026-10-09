"""The Local Autonomy Mesh's shared edge domain.

``core.edge`` holds what both sides of the mesh speak: the containment-policy
pack schema (``policy.py``), the DSSE v1 / Ed25519 offline verifier
(``verify.py``, ported from the Medic trust pattern), and the signing helpers
the control plane uses to build what the verifier accepts (``signing.py``).
Medic itself is not modified — the import fence keeps the two apart.

The load-bearing ordering lives across these modules: an unverified payload is
never parsed (``verify.verify_envelope`` checks signatures on raw bytes), and a
parsed policy is never loaded without passing its freshness and version gates
(``policy.parse_policy`` and ``policy.check_policy_version``). Every refusal
carries a recorded rejection class.
"""

from __future__ import annotations

# The content types this domain signs and verifies. Both sides hardcode these
# strings — they are part of the wire contract, not configuration.
EDGE_POLICY = "application/vnd.deeptempo.vigil.edge-policy.v1+json"
EDGE_TRUST_ROOT = "application/vnd.deeptempo.vigil.edge-trust-root.v1+json"

__all__ = ["EDGE_POLICY", "EDGE_TRUST_ROOT"]
