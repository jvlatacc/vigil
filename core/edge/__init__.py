"""Edge autonomy mesh — control plane (spec: Decentralized Edge Agent Daemons).

The control-plane half of the edge feature: the node registry that enrolls and
revokes edge daemons, the DSSE signing stack that issues policy bundles, and
the import path that replays a partitioned daemon's journal into the ordinary
findings and approval surfaces. The daemon side lives in ``services/edge``
(built separately, isolated from ``core`` the way medic is); the two halves
share wire contracts only.

Everything here follows the house rules the spec pins down: a node credential
is a named actor, never a score; the signed bundle is the only source of edge
autonomy; and revocation beats every local allowance.
"""
