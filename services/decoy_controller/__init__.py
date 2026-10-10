"""Vigil decoy-controller — the reference steering enforcement service.

A small, token-authenticated HTTP service that turns honey-route leases into
data-plane redirects. Vigil decides, scores, leases, and audits; this service
only programs the plane it is told about:

- ``POST /steer``          upsert one lease's redirect (source, destinations,
                           ports, TTL) into the decoys
- ``DELETE /steer/{id}``   remove one lease's redirect (idempotent)
- ``GET /steer/{id}``      one lease's rule, or 404
- ``GET /reconcile``       every rule the controller currently holds
- ``POST /drain``          remove every rule (operator kill-switch path)
- ``GET /health``          liveness for the container healthcheck (no data)

Fail-open by construction: the controller only ever ADDS redirects for the
sources Vigil sends it. It is never on the production routing path — when it
is down, unreachable, or draining, ordinary traffic flows untouched and the
caller (``core/deception/backends.py``) marks the lease failed.

Self-contained by contract: this service runs on the network plane, outside
Vigil's trust domain, and imports nothing from ``core`` or the other
services. The smaller its dependency surface, the smaller its blast radius —
it is the one component that programs production DNAT. The ``.importlinter``
medic contract enforces the same rule for services/medic and lists this
package alongside it.

Shipped default is inert: the ``memory`` driver records rules in-process and
touches no traffic; with no token configured the API answers 401 to
everything. Real enforcement is opt-in per deployment (``nftables`` for
compose/single-host DNAT, ``cilium`` for Kubernetes — see ``drivers/`` and
README.md).
"""
