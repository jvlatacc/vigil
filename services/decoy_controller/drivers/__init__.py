"""Enforcement drivers: make the data plane match the registry.

Every driver answers one verb — ``sync(rules)`` — which is the whole
contract: make the plane hold exactly ``rules`` and return the lease →
backend-reference map. Steering, unsteering, renewal, and drain all reduce
to a sync against the registry's current contents, which is what makes every
path idempotent and reconcile trivially honest (the refs it reports are the
refs the last sync produced).

Drivers are synchronous and blocking (subprocess, Kubernetes API) and must
never touch the registry — the API layer runs them via ``asyncio.to_thread``.
"""

from __future__ import annotations

from typing import Dict, List, Protocol, Sequence, runtime_checkable

from services.decoy_controller.registry import Rule

from ..config import (
    DRIVER_CILIUM,
    DRIVER_MEMORY,
    DRIVER_NFTABLES,
    ControllerConfig,
)


@runtime_checkable
class SteeringDriver(Protocol):
    """Make the data plane match ``rules`` exactly."""

    name: str

    def sync(self, rules: Sequence[Rule]) -> Dict[str, str]:
        """Apply the desired state; return {lease_id: backend_ref}."""
        ...

    def boot(self) -> None:
        """Clear anything stale from a previous controller life.

        Called once at startup with an empty registry: after a restart the
        controller cannot name rules a previous process created, so it
        removes them rather than leaving redirects nobody can reconcile.
        Drivers whose plane cannot hold stale state (memory) are no-ops.
        """
        ...


class MemoryDriver:
    """The shipped default: records the sync result, touches nothing.

    The refs it returns are real, stable, and queryable — integration tests
    assert against the same ``memory:<lease>`` handles the audit trail will
    show — but no packet is ever affected. Inert by construction.
    """

    name = DRIVER_MEMORY

    def __init__(self) -> None:
        # The plane as last synced: {lease_id: (ref, rule)} — the test
        # surface's view of "what the data plane holds".
        self.plane: Dict[str, tuple] = {}
        self.sync_calls: List[int] = []

    def sync(self, rules: Sequence[Rule]) -> Dict[str, str]:
        self.sync_calls.append(len(rules))
        desired = {r.lease_id: r for r in rules}
        removed = set(self.plane) - set(desired)
        for lease_id in removed:
            del self.plane[lease_id]
        refs: Dict[str, str] = {}
        for lease_id, rule in desired.items():
            ref = f"memory:{lease_id}"
            self.plane[lease_id] = (ref, rule)
            refs[lease_id] = ref
        return refs

    def boot(self) -> None:
        self.plane.clear()


def build_driver(config: ControllerConfig) -> SteeringDriver:
    """The driver the config names.

    Construction failures happen here, at startup, not mid-incident. The
    cilium driver imports its Kubernetes client lazily and raises a clear
    error when the dependency is missing — that dependency is scoped to this
    service (services/decoy_controller/requirements.txt) and must never leak
    into Vigil's shared requirements.
    """
    if config.driver == DRIVER_MEMORY:
        return MemoryDriver()
    if config.driver == DRIVER_NFTABLES:
        from .nftables import NftablesDriver

        return NftablesDriver(config)
    if config.driver == DRIVER_CILIUM:
        from .cilium import CiliumDriver

        return CiliumDriver(config)
    raise ValueError(f"Unknown decoy-controller driver: {config.driver!r}")
