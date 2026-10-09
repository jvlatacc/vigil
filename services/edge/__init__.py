"""Vigil Edge Daemon (Local Autonomy Mesh).

The node-side half of the edge-daemons design spec: a standalone daemon that
keeps defending its segment with pre-distributed, operator-signed policy
bundles while the central control plane is unreachable, then reconciles when
it returns. The SLM advises; the deterministic gate decides.

It imports nothing from ``core``, ``tools`` or any other service (the
``edge`` contract in ``.importlinter`` enforces this), and has its own
``pyproject.toml``/``uv.lock`` for the same reason Medic does: a
control-plane dependency bump must not reach the node that defends the
segment. Runs as ``python -m services.edge`` from the repo root, the way the
other services run.
"""

__version__ = "1.0.0"
