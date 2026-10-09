"""The steering backend seam: Vigil decides, the backend programs the plane.

A backend is what turns a lease into routed traffic. The protocol is the
whole contract the response pipeline knows about; everything else (nftables,
Cilium, a WireGuard overlay) arrives as a backend behind it, which is why no
Kubernetes client, CNI or eBPF code can leak into the API or daemon dependency
trees — the repo's vendor-control-plane precedent, applied to the network
plane.

The shipped backend is :class:`DryRunBackend`: it records what it would do
and touches nothing, which keeps the whole pipeline exercisable in dev and
the feature inert until an operator selects a real backend.
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, TypedDict, runtime_checkable

logger = logging.getLogger(__name__)


class SteerScope(TypedDict):
    """What one redirect covers — attacker, victims, ports, lifetime."""

    source_ip: str  # validated by routable_ip / responder._actionable_ip
    destination_ips: List[str]  # the internal targets the probes hit
    ports: List[int]  # suspicious service class first, never "all traffic"
    ttl_seconds: int  # the lease, not the approval row, is what expires
    lease_id: str


@runtime_checkable
class SteeringBackend(Protocol):
    """The three verbs a steering backend answers to.

    ``steer`` is an upsert keyed on ``scope["lease_id"]`` — renewal re-steers
    with a longer TTL rather than needing a fourth verb. Every method returns
    the standard ``{success, backend_ref?, error?, message?}`` dict the
    executor feeds to ``mark_executed`` / ``mark_failed``.
    """

    name: str

    async def steer(self, scope: SteerScope) -> Dict[str, Any]: ...

    async def unsteer(
        self, lease_id: str, backend_ref: Optional[str]
    ) -> Dict[str, Any]: ...

    async def status(self, lease_id: str) -> Dict[str, Any]: ...


class DryRunBackend:
    """Records every call and touches nothing.

    The rollback handle it returns is the controller API path the real
    backend would honour, so a dry-run execution_result reads exactly like
    the live one will — a rehearsal you can audit.
    """

    name = "dry_run"

    def __init__(self) -> None:
        self.steered: List[Dict[str, Any]] = []
        self.unsteered: List[Dict[str, Any]] = []

    async def steer(self, scope: SteerScope) -> Dict[str, Any]:
        self.steered.append(dict(scope))
        logger.info(
            "Dry-run steer: lease %s would route %s (ports %s) to decoys",
            scope.get("lease_id"),
            scope.get("source_ip"),
            scope.get("ports"),
        )
        return {
            "success": True,
            "backend": self.name,
            "backend_ref": f"dry-run:{scope.get('lease_id')}",
            "message": "dry-run: no traffic was touched",
        }

    async def unsteer(
        self, lease_id: str, backend_ref: Optional[str]
    ) -> Dict[str, Any]:
        self.unsteered.append({"lease_id": lease_id, "backend_ref": backend_ref})
        logger.info("Dry-run unsteer: lease %s would be removed", lease_id)
        return {
            "success": True,
            "backend": self.name,
            "backend_ref": backend_ref,
            "message": "dry-run: no traffic was touched",
        }

    async def status(self, lease_id: str) -> Dict[str, Any]:
        steered = any(s.get("lease_id") == lease_id for s in self.steered)
        removed = any(u["lease_id"] == lease_id for u in self.unsteered)
        return {
            "success": True,
            "backend": self.name,
            "active": steered and not removed,
            "message": "dry-run: no traffic was touched",
        }


def build_backend(name: str) -> SteeringBackend:
    """The backend a config names.

    Only ``dry_run`` ships today; the controller backend lands with the
    decoy-controller service and will refuse to build without its
    credentials. Unknown names fail here, at construction, rather than
    mid-incident.
    """
    if name == "dry_run":
        return DryRunBackend()
    if name == "controller":
        raise NotImplementedError(
            "The controller steering backend ships with the decoy-controller "
            "service (services/decoy_controller/); configure dry_run until then."
        )
    raise ValueError(f"Unknown deception steering backend: {name!r}")
