"""Enforcement adapters: what a speculative action does to the world.

The registry is the fast path's single authority on enforcement. An adapter
owns both halves of the contract — apply and release — keyed by action type,
so a restriction that cannot be released is known before it is applied
(locked decision 4). Two implementations ship in v1: the Cloudflare
rate-limit adapter is the only real enforcement, and the simulation adapter
records intent for every type without one.

An action type with no adapter is refused loudly, never silently simulated:
a row that fell through to simulation would record a containment that never
happened — the #1686 failure shape — and the type is refused before any row
exists.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from core.response.approval_service import PendingAction

logger = logging.getLogger(__name__)

# The rate-limit rule's counting window and threshold when the row does not
# name them: a one-minute window, one hundred requests. Deliberately loose —
# the speculative tier's job is to slow a source down, not to sit on its
# spend, and the adjudicator can escalate to a hard block.
DEFAULT_PERIOD_SECONDS = 60
DEFAULT_REQUESTS_PER_PERIOD = 100


class UnknownActionTypeError(ValueError):
    """No enforcement adapter is registered for the action type.

    Loud on purpose. A missing registry entry must degrade to an error, not
    to the simulation adapter: the simulation exists for types we know are
    safe to pretend at, not as a catch-all that turns a wiring mistake into
    a phantom containment.
    """


@dataclass(frozen=True)
class EnforceResult:
    """What an adapter did, recorded on the row's ``execution_result``.

    ``applied=False`` is a refusal or a vendor rejection — never treated as
    success-with-caveats: the service marks the row failed so the ledger
    never claims a restriction that does not exist. ``external_ref`` names
    the enforced thing at the vendor (a Cloudflare ruleset rule id), and is
    the release verb's handle; simulation adapters have none.
    """

    applied: bool
    external_ref: Optional[str]
    detail: str


class EnforcementAdapter(Protocol):
    """Apply and release, for the action types in ``applies_to``.

    ``simulates`` marks the adapters that touch nothing external — surfaces
    label those rows — and ``name`` identifies the adapter in the row's
    rollback recipe.
    """

    simulates: bool
    name: str

    def applies_to(self) -> frozenset[str]: ...

    def apply(self, action: PendingAction) -> EnforceResult: ...

    def release(self, action: PendingAction) -> EnforceResult: ...


class SimulationAdapter:
    """Reference adapter: records what it would do, touches nothing external.

    The default for ``tarpit``, ``session_pin`` and ``latency_inject``, and
    for ``rate_limit`` when the configuration says simulation — every type
    without a real enforcement integration rides here. Deterministic by
    construction: the same action always yields the same result, and the
    result carries no external reference because nothing external exists.
    """

    simulates = True
    name = "simulation"

    def applies_to(self) -> frozenset[str]:
        return frozenset({"rate_limit", "tarpit", "session_pin", "latency_inject"})

    def apply(self, action: PendingAction) -> EnforceResult:
        detail = (
            f"simulated {action.action_type} on {action.target}: "
            "intent recorded, nothing enforced"
        )
        logger.info("SimulationAdapter apply: %s", detail)
        return EnforceResult(applied=True, external_ref=None, detail=detail)

    def release(self, action: PendingAction) -> EnforceResult:
        detail = (
            f"simulated release for {action.action_type} on {action.target}: "
            "nothing external to release"
        )
        logger.info("SimulationAdapter release: %s", detail)
        return EnforceResult(applied=True, external_ref=None, detail=detail)


def _cloudflare_config() -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The integration config when it can enforce, else the reason it cannot.

    ``(cfg, None)`` or ``(None, reason)`` — exactly one side is None. The
    imports are lazy so environments that never enable Cloudflare pay
    nothing, matching the approved-action executor's seam.
    """
    try:
        from core.config import get_integration_config, is_integration_enabled
    except Exception as e:  # noqa: BLE001
        logger.error("config import failed for the cloudflare adapter: %s", e)
        return None, "cloudflare configuration could not be read"
    if not is_integration_enabled("cloudflare"):
        return None, "cloudflare integration is disabled"
    cfg = get_integration_config("cloudflare") or {}
    if not cfg.get("api_token"):
        return None, "cloudflare api_token is not configured"
    if not cfg.get("zone_id"):
        return None, (
            "cloudflare zone_id is not configured "
            "(rate limiting rules are zone-scoped)"
        )
    return cfg, None


def _cloudflare_tool():
    """The Cloudflare REST helpers, imported lazily (see ``_cloudflare_config``)."""
    from core.integrations.cloudflare import tool as cf_tool

    return cf_tool


class CloudflareRateLimitAdapter:
    """The one real enforcement primitive in v1.

    A zone-level WAF rate-limiting rule in the ``http_ratelimit`` phase,
    scoped to the target source IP: ``ip.src eq <target>``, action block,
    with ``mitigation_timeout`` set from the row's TTL so Cloudflare lifts
    the mitigation on its own even when no release arrives. The vendor call
    lives with the other REST helpers in
    ``core/integrations/cloudflare/tool.py`` (single source of truth for the
    Cloudflare API surface); the adapter interface, not the vendor shape, is
    the fixed contract.
    """

    simulates = False
    name = "cloudflare_rate_limit"

    def applies_to(self) -> frozenset[str]:
        return frozenset({"rate_limit"})

    def apply(self, action: PendingAction) -> EnforceResult:
        cfg, reason = _cloudflare_config()
        if cfg is None:
            return EnforceResult(False, None, f"refused: {reason}")
        params = action.parameters or {}
        try:
            cf_tool = _cloudflare_tool()
        except Exception as e:  # noqa: BLE001
            logger.error("cloudflare integration client unavailable: %s", e)
            return EnforceResult(
                False, None, "refused: cloudflare integration client unavailable"
            )
        result = cf_tool._ratelimit_apply_ip(
            api_token=cfg["api_token"],
            zone_id=cfg["zone_id"],
            ip=action.target,
            mitigation_timeout=params.get("ttl_seconds"),
            reason=action.reason,
            period=params.get("rate_limit_period", DEFAULT_PERIOD_SECONDS),
            requests_per_period=params.get(
                "rate_limit_requests_per_period", DEFAULT_REQUESTS_PER_PERIOD
            ),
        )
        if result.get("error"):
            return EnforceResult(False, None, f"refused: {result['error']}")
        if result.get("success"):
            ref = result.get("external_ref")
            return EnforceResult(
                True,
                ref,
                f"enforced: rate-limit rule {ref} on {action.target} "
                f"(HTTP {result.get('status_code')})",
            )
        return EnforceResult(
            False,
            None,
            f"cloudflare rejected the rate-limit rule (HTTP {result.get('status_code')})",
        )

    def release(self, action: PendingAction) -> EnforceResult:
        cfg, reason = _cloudflare_config()
        if cfg is None:
            return EnforceResult(False, None, f"refused: {reason}")
        params = action.parameters or {}
        rollback = params.get("rollback") or {}
        external_ref = rollback.get("external_ref")
        try:
            cf_tool = _cloudflare_tool()
        except Exception as e:  # noqa: BLE001
            logger.error("cloudflare integration client unavailable: %s", e)
            return EnforceResult(
                False, None, "refused: cloudflare integration client unavailable"
            )
        result = cf_tool._ratelimit_release_ip(
            api_token=cfg["api_token"],
            zone_id=cfg["zone_id"],
            external_ref=external_ref,
        )
        if result.get("error"):
            return EnforceResult(False, None, f"refused: {result['error']}")
        if result.get("already_released"):
            return EnforceResult(
                True, external_ref, "released: rate-limit rule already absent"
            )
        return EnforceResult(True, external_ref, "released: rate-limit rule deleted")


class EnforcementRegistry:
    """Adapters by action type — the dispatch seam the service talks to."""

    def __init__(self, adapters: Dict[str, EnforcementAdapter]):
        self._adapters = dict(adapters)

    def adapter_for(self, action_type: str) -> EnforcementAdapter:
        adapter = self._adapters.get(action_type)
        if adapter is None:
            raise UnknownActionTypeError(
                f"no enforcement adapter for action type {action_type!r}"
            )
        return adapter


def build_registry(config) -> EnforcementRegistry:
    """The registry for a configuration: the real adapter where one exists.

    Every allowed action type gets an adapter — the Cloudflare one where the
    type is enforced and a real adapter implements it, the simulation one
    otherwise. A type named in ``enforced_action_types`` without a real
    adapter is a configuration error and fails here, at construction:
    dispatching it through the simulation adapter would be exactly the
    silent simulation the registry refuses.
    """
    cloudflare = CloudflareRateLimitAdapter()
    unimplemented = config.enforced_action_types - cloudflare.applies_to()
    if unimplemented:
        raise UnknownActionTypeError(
            "enforced_action_types names types with no real adapter: "
            + ", ".join(sorted(unimplemented))
        )
    adapters: Dict[str, EnforcementAdapter] = {}
    for action_type in sorted(config.allowed_action_types):
        if action_type in config.enforced_action_types:
            adapters[action_type] = cloudflare
        else:
            adapters[action_type] = SimulationAdapter()
    return EnforcementRegistry(adapters)
