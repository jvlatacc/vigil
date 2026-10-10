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

import asyncio
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    TypedDict,
    runtime_checkable,
)

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


# ---------------------------------------------------------------------------
# Controller backend — the reference decoy-controller service
# ---------------------------------------------------------------------------

# Vendor id for the daemon's shared cooldown bookkeeping
# (services/daemon/vendor_errors.py). ``core`` must not import ``services``
# (the deployables contract), so the daemon registers the hooks at startup
# via :func:`set_vendor_error_hooks`; without wiring there is no cooldown —
# the backend still fails open on every error path.
DECOY_VENDOR_ID = "decoy_controller"

_record_error_hook: Optional[Callable[[str, int], None]] = None
_cooling_down_hook: Optional[Callable[[str], bool]] = None


def set_vendor_error_hooks(
    record_error: Optional[Callable[[str, int], None]],
    cooling_down: Optional[Callable[[str], bool]],
) -> None:
    """Wire the daemon's vendor-error bookkeeping into the controller backend.

    The composition-root seam for the import-layer rule: ``core.deception``
    cannot import ``services.daemon.vendor_errors``, so the daemon process
    calls this once at startup with ``(record_vendor_error,
    vendor_cooling_down)``. Passing ``(None, None)`` clears (tests).
    """
    global _record_error_hook, _cooling_down_hook
    _record_error_hook = record_error
    _cooling_down_hook = cooling_down


def _credentials() -> Optional[Dict[str, Any]]:
    """The integration slice's resolved config, or None while unconfigured.

    Resolved per call (not per backend) so an operator can add the base_url
    and token in Settings without restarting the daemon — the same laziness
    the Cloudflare executor's ``_config()`` shows.
    """
    from core.integrations._base.config import resolve
    from core.integrations.decoy_controller.descriptor import DECOY_CONTROLLER

    cfg = resolve(DECOY_CONTROLLER)
    if not cfg.get("base_url") or not cfg.get("api_token"):
        return None
    return cfg


class ControllerBackend:
    """Steer through the reference decoy-controller service.

    The pipeline's first real network-plane executor. Sync REST helpers
    (``core/integrations/decoy_controller/tool.py``, the Cloudflare anatomy)
    run on worker threads; every failure returns the standard
    ``{success: False, error}`` shape — a controller outage marks the lease
    failed and production routing is untouched (fail-open). A 401/403/429
    feeds the daemon's cooldown bookkeeping through the registered hooks, so
    a revoked controller token backs off instead of hammering.
    """

    name = "controller"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> None:
        # Explicit credentials (tests, unusual deployments) win over the
        # integration slice; empty means "resolve per call".
        self._base_url = base_url or None
        self._api_token = api_token or None

    def _config(self) -> Optional[Dict[str, Any]]:
        if self._base_url and self._api_token:
            return {"base_url": self._base_url, "api_token": self._api_token}
        return _credentials()

    def _not_configured(self) -> Dict[str, Any]:
        return {
            "success": False,
            "backend": self.name,
            "error": "decoy_controller_not_configured",
            "message": (
                "Enable the decoy_controller integration (base_url + api_token) "
                "in Settings → Integrations, or use the dry_run backend."
            ),
        }

    def _gated(self) -> Optional[Dict[str, Any]]:
        """The refusal to return while the vendor cooldown is active, if any."""
        if _cooling_down_hook is None:
            return None
        if _cooling_down_hook(DECOY_VENDOR_ID):
            return {
                "success": False,
                "backend": self.name,
                "error": "decoy_controller_cooling_down",
                "message": (
                    "Prior controller auth/quota failure; backing off (the lease "
                    "row stays failed and can be re-steered)."
                ),
            }
        return None

    def _record(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Feed a failed call's status into the cooldown bookkeeping, if wired."""
        status = result.get("status_code")
        if (
            _record_error_hook is not None
            and not result.get("success")
            and isinstance(status, int)
            and status in (401, 403, 429)
        ):
            _record_error_hook(DECOY_VENDOR_ID, status)
        return result

    async def steer(self, scope: SteerScope) -> Dict[str, Any]:
        cfg = self._config()
        if cfg is None:
            return self._not_configured()
        gated = self._gated()
        if gated is not None:
            return gated
        from core.integrations.decoy_controller import tool as controller_tool

        result = await asyncio.to_thread(
            controller_tool._steer,
            cfg["base_url"],
            cfg["api_token"],
            scope["lease_id"],
            scope["source_ip"],
            list(scope["destination_ips"]),
            list(scope["ports"]),
            int(scope["ttl_seconds"]),
        )
        return self._record(result)

    async def unsteer(
        self, lease_id: str, backend_ref: Optional[str]
    ) -> Dict[str, Any]:
        cfg = self._config()
        if cfg is None:
            return self._not_configured()
        from core.integrations.decoy_controller import tool as controller_tool

        # The rollback path never gates on cooldown: removing redirects must
        # always be attempted, whatever the bookkeeping says about steering.
        return await asyncio.to_thread(
            controller_tool._unsteer,
            cfg["base_url"],
            cfg["api_token"],
            lease_id,
            backend_ref,
        )

    async def status(self, lease_id: str) -> Dict[str, Any]:
        cfg = self._config()
        if cfg is None:
            return self._not_configured()
        from core.integrations.decoy_controller import tool as controller_tool

        result = await asyncio.to_thread(
            controller_tool._reconcile, cfg["base_url"], cfg["api_token"]
        )
        if not result.get("success"):
            return self._record(result)
        held = {rule.get("lease_id"): rule for rule in (result.get("rules") or [])}
        rule = held.get(lease_id)
        return {
            "success": True,
            "backend": self.name,
            "active": rule is not None,
            "rule": rule,
            "error": None,
        }


def build_backend(name: str) -> SteeringBackend:
    """The backend a config names.

    ``dry_run`` is the shipped default; ``controller`` speaks to the
    reference decoy-controller service. Unknown names fail here, at
    construction, rather than mid-incident.
    """
    if name == "dry_run":
        return DryRunBackend()
    if name == "controller":
        return ControllerBackend()
    raise ValueError(f"Unknown deception steering backend: {name!r}")
