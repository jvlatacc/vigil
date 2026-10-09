"""Fast-Path executors — the apply/undo pairs that give leases their effects.

Every executor implements the same contract (``ContainmentExecutor``):

- ``apply(lease)`` returns an undo payload or raises — never a partial
  effect. Calling apply twice with the same lease id is a no-op: object
  names are derived from the lease id, so a re-apply finds its object
  instead of duplicating it.
- ``undo(lease_id, undo_payload)`` removes ONLY the object that lease's
  apply created. Undoing twice succeeds (already-gone is success), and
  undoing an EMPTY payload still works: every object name is
  reconstructable from the lease id alone, so a crash between apply and
  the CAS that stores the payload cannot orphan the effect (spec:
  crash-orphan safety; the undo precedent is ``_waf_unblock_ip`` in
  ``core.integrations.cloudflare.tool``, which deletes by the rule id the
  apply returned).

Two v1 built-ins:

- ``CloudflareChallengeExecutor`` (``challenge``) and
  ``CloudflareRateLimitExecutor`` (``rate_limit``) — one WAF rule per
  lease on the account-level rulesets API, scoped by a per-principal
  expression (``(ip.src eq ..)`` / ``(http.host eq ..)``). The rule name
  is ``vigil-fastpath-{lease_id}``; undo deletes that one rule. Hostname
  and domain principals ride a custom-rules expression; user principals
  are refused — Cloudflare has no per-username primitive, and pretending
  otherwise would record friction that does not exist.
- ``EdgeContainmentExecutor`` (``tarpit``, ``latency_injection``,
  ``pin_session``) — one signed HTTPS call to an operator-run endpoint.
  The endpoint owns its own state; Vigil caps concurrency at the gate and
  the endpoint is the single source of truth for its objects. Undo is a
  DELETE keyed by the undo token — or, when the token was never stored,
  by the lease id, which the endpoint can resolve deterministically.

These executors live in THIS registry, owned by the fastpath package.
They are never wired into ``_approved_action_executor``'s 30 s approval
sweep: that sweep re-scans unknown types forever and executes on a
cadence, the opposite of lease semantics (spec: locked decision).
``execute_approved_actions`` refuses types it does not know — a test in
``tests/unit/response/fastpath/test_executors.py`` pins that refusal.

Import discipline: this module imports ``core.config`` (settings and the
integration-config accessors) and ``core.time`` — never services, the
API surface, or the LLM stack. lint-imports enforces it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, Optional, Protocol, Tuple, runtime_checkable

import httpx

from core.config import get_integration_config, get_settings, is_integration_enabled

logger = logging.getLogger(__name__)

# Cloudflare API surface. Account-level WAF rulesets, the same account
# credentials the approved Cloudflare actions use
# (core.integrations.cloudflare.tool: api_token + account_id).

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_TIMEOUT_SECONDS = 30.0

# Ruleset phases the built-ins write into. Challenge rules and rate-limit
# rules live in different phases of the same account entrypoint ruleset.
CF_PHASE_CUSTOM = "firewalls_custom"
CF_PHASE_RATE_LIMIT = "http_ratelimit"

# Deterministic rule-name prefix: the rest is the lease id, so any crash
# orphan can be found — and undone — from the lease id alone.
RULE_NAME_PREFIX = "vigil-fastpath"


def rule_name_for(lease_id: str) -> str:
    """The deterministic Cloudflare rule name for a lease.

    The single point where lease id becomes object name: apply is
    idempotent by lookup on this name, and undo can reconstruct it
    without any stored token.
    """
    return f"{RULE_NAME_PREFIX}-{lease_id}"


class ExecutorError(RuntimeError):
    """An apply or undo the executor refuses or could not complete."""


@dataclass(frozen=True)
class LeaseSpec:
    """The executor-facing projection of a lease row (see
    ``ledger.lease_spec_of``). Everything an executor needs, nothing it
    doesn't — no session, no ORM object, no ledger internals."""

    lease_id: str
    action_type: str
    entity_type: str
    entity_id: str
    ttl_seconds: Optional[int] = None
    expires_at: Optional[datetime] = None
    observed: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ContainmentExecutor(Protocol):
    """apply returns an undo payload or raises; undo consumes ONLY that
    token. Both directions are idempotent, and undo tokens are
    reconstructable from the lease id alone — the crash-orphan guarantee
    above. ``action_type`` (or ``action_types`` for multi-verb
    executors) is what the registry keys on."""

    action_type: ClassVar[str]

    async def apply(self, lease: LeaseSpec) -> Dict[str, Any]: ...

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None: ...


# ----------------------------------------------------------------------
# Cloudflare built-ins — module-level REST helpers in the repo idiom
# ----------------------------------------------------------------------


def _cf_headers(api_token: str) -> Dict[str, str]:
    """Same header shape as core.integrations.cloudflare.tool._headers."""
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _principal_expression(entity_type: str, entity_id: str) -> str:
    """The per-principal WAF expression for a lease target.

    Never a subnet — the spec scopes every built-in to the PRINCIPAL
    (ip.src eq the single address), never a prefix. Hostnames and domains
    match as exact strings.
    """
    if entity_type == "ip":
        return f"(ip.src eq {entity_id})"
    if entity_type == "hostname":
        return f'(http.host eq "{entity_id}")'
    if entity_type == "domain":
        return f'(dns.fr eq "{entity_id}")'
    raise ExecutorError(
        f"cloudflare executor scopes to ip/hostname/domain principals, "
        f"not {entity_type!r} — user friction rides the edge endpoint"
    )


def _find_rule(
    api_token: str,
    account_id: str,
    ruleset_phase: str,
    name: str,
) -> Optional[Tuple[str, str]]:
    """Locate this lease's rule in the account ruleset.

    Returns ``(ruleset_id, rule_id)`` or None. This lookup is what makes
    apply idempotent (found ⇒ no-op) and undo reconstructable (the rule
    is findable by its deterministic name even with no stored token).
    """
    resp = httpx.get(
        f"{CF_API_BASE}/accounts/{account_id}/rulesets/phases/{ruleset_phase}"
        "/entrypoint",
        headers=_cf_headers(api_token),
        timeout=CF_TIMEOUT_SECONDS,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or not data.get("success", False):
        # A missing entrypoint ruleset means no rule was ever created in
        # this phase — for undo that is success; for apply it is an error
        # the caller sees as a refused status_code.
        if resp.status_code == 404:
            return None
        raise ExecutorError(
            f"cloudflare ruleset lookup failed: status={resp.status_code} "
            f"errors={data.get('errors')}"
        )
    for rule in data.get("result", {}).get("rules", []):
        if rule.get("name") == name:
            return data["result"]["id"], rule["id"]
    return None


def _create_rule(
    api_token: str,
    account_id: str,
    ruleset_phase: str,
    name: str,
    expression: str,
    action: str,
    rule_body_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create one named rule in the phase's entrypoint ruleset."""
    body: Dict[str, Any] = {
        "name": name,
        "expression": expression,
        "action": action,
        "description": f"Vigil speculative-containment lease {name}",
        **(rule_body_extra or {}),
    }
    resp = httpx.post(
        f"{CF_API_BASE}/accounts/{account_id}/rulesets/phases/{ruleset_phase}"
        "/entrypoint/rules",
        headers=_cf_headers(api_token),
        json=body,
        timeout=CF_TIMEOUT_SECONDS,
    )
    data = resp.json() if resp.content else {}
    success = resp.status_code in (200, 201) and data.get("success", False)
    result = data.get("result") or {}
    return {
        "success": success,
        "status_code": resp.status_code,
        "ruleset_id": result.get("id"),
        "rule_id": (result.get("rule") or {}).get("id"),
        "errors": data.get("errors"),
    }


def _delete_rule(
    api_token: str,
    account_id: str,
    ruleset_phase: str,
    ruleset_id: str,
    rule_id: str,
) -> Dict[str, Any]:
    """Delete one rule by id. 404 is success — undo is idempotent."""
    resp = httpx.delete(
        f"{CF_API_BASE}/accounts/{account_id}/rulesets/{ruleset_id}/rules/"
        f"{rule_id}",
        headers=_cf_headers(api_token),
        timeout=CF_TIMEOUT_SECONDS,
    )
    data = resp.json() if resp.content else {}
    return {
        "success": resp.status_code in (200, 204) or resp.status_code == 404,
        "status_code": resp.status_code,
        "rule_id": rule_id,
        "errors": data.get("errors"),
    }


class _CloudflareRuleExecutor:
    """Shared machinery for the two Cloudflare built-ins.

    Both write ONE rule per lease into their own ruleset phase and undo
    by deleting exactly that rule. Subclasses fix the phase, the WAF
    action and any rule-body extras.
    """

    action_type: ClassVar[str] = ""
    _phase: ClassVar[str] = CF_PHASE_CUSTOM
    _cf_action: ClassVar[str] = "managed_challenge"

    def _credentials(self) -> Tuple[str, str]:
        """Read the integration config at call time, the way
        ``_execute_cloudflare_action`` does — never cached at import."""
        if not is_integration_enabled("cloudflare"):
            raise ExecutorError("cloudflare_integration_disabled")
        cfg = get_integration_config("cloudflare") or {}
        api_token = cfg.get("api_token")
        account_id = cfg.get("account_id")
        if not api_token:
            raise ExecutorError("cloudflare api_token not configured")
        if not account_id:
            raise ExecutorError("cloudflare account_id not configured")
        return str(api_token), str(account_id)

    async def apply(self, lease: LeaseSpec) -> Dict[str, Any]:
        api_token, account_id = self._credentials()
        name = rule_name_for(lease.lease_id)
        expression = _principal_expression(lease.entity_type, lease.entity_id)

        # Idempotent apply: a rule with this deterministic name already
        # exists (the apply ran before a crash) — return its token again.
        existing = await _find_rule_threaded(api_token, account_id, self._phase, name)
        if existing is not None:
            ruleset_id, rule_id = existing
            return {
                "rule_id": rule_id,
                "ruleset_id": ruleset_id,
                "rule_name": name,
                "reapplied": True,
            }

        rule_extra = (
            self._rate_limit_body(lease) if self._phase == CF_PHASE_RATE_LIMIT else None
        )
        result = await _create_rule_threaded(
            api_token,
            account_id,
            self._phase,
            name,
            expression,
            self._cf_action,
            rule_extra,
        )
        if not result.get("success"):
            raise ExecutorError(
                f"cloudflare rule create failed: status={result.get('status_code')} "
                f"errors={result.get('errors')}"
            )
        return {
            "rule_id": result["rule_id"],
            "ruleset_id": result["ruleset_id"],
            "rule_name": name,
        }

    def _rate_limit_body(self, lease: LeaseSpec) -> Optional[Dict[str, Any]]:
        return None

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        api_token, account_id = self._credentials()
        name = rule_name_for(lease_id)

        rule_id = undo_payload.get("rule_id")
        ruleset_id = undo_payload.get("ruleset_id")
        if not (rule_id and ruleset_id):
            # Crash-orphan path: no stored token. The deterministic name
            # is the reconstruction — find the rule (and its ruleset) by
            # name in this executor's phase.
            found = await _find_rule_threaded(api_token, account_id, self._phase, name)
            if found is None:
                return  # already gone — idempotent undo succeeds
            ruleset_id, rule_id = found

        result = await _delete_rule_threaded(
            api_token, account_id, self._phase, str(ruleset_id), str(rule_id)
        )
        if not result.get("success"):
            raise ExecutorError(
                f"cloudflare rule delete failed: status={result.get('status_code')} "
                f"errors={result.get('errors')}"
            )
        logger.info(
            "containment executor undo rule_deleted lease=%s rule_id=%s "
            "action_type=%s",
            lease_id,
            rule_id,
            self.action_type,
        )


async def _find_rule_threaded(
    api_token: str, account_id: str, phase: str, name: str
) -> Optional[Tuple[str, str]]:
    return await asyncio.to_thread(_find_rule, api_token, account_id, phase, name)


async def _create_rule_threaded(
    api_token: str,
    account_id: str,
    phase: str,
    name: str,
    expression: str,
    action: str,
    rule_body_extra: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _create_rule,
        api_token,
        account_id,
        phase,
        name,
        expression,
        action,
        rule_body_extra,
    )


async def _delete_rule_threaded(
    api_token: str, account_id: str, phase: str, ruleset_id: str, rule_id: str
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _delete_rule, api_token, account_id, phase, ruleset_id, rule_id
    )


class CloudflareChallengeExecutor(_CloudflareRuleExecutor):
    """A per-principal managed-challenge rule — the milder of the two
    built-ins; the gate maps ``high`` severity here."""

    action_type: ClassVar[str] = "challenge"
    _phase: ClassVar[str] = CF_PHASE_CUSTOM
    _cf_action: ClassVar[str] = "managed_challenge"


class CloudflareRateLimitExecutor(_CloudflareRuleExecutor):
    """A per-principal rate-limit rule — the stronger built-in; the gate
    maps ``critical`` severity here.

    ``requests_per_period`` / ``period_seconds`` are constructor knobs
    with conservative defaults; the lease TTL bounds how long the rule
    lives, never how hard it throttles.
    """

    action_type: ClassVar[str] = "rate_limit"
    _phase: ClassVar[str] = CF_PHASE_RATE_LIMIT
    _cf_action: ClassVar[str] = "block"

    def __init__(
        self,
        requests_per_period: int = 100,
        period_seconds: int = 60,
    ) -> None:
        self.requests_per_period = requests_per_period
        self.period_seconds = period_seconds

    def _rate_limit_body(self, lease: LeaseSpec) -> Dict[str, Any]:
        return {
            "ratelimit": {
                "characteristics": ["ip.src"],
                "period": self.period_seconds,
                "requests_per_period": self.requests_per_period,
                "mitigation_timeout": min(self.period_seconds, 600),
            }
        }


# ----------------------------------------------------------------------
# Edge containment — one signed call to an operator-run endpoint
# ----------------------------------------------------------------------


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over ``{timestamp}.{body}`` — replay-window signed.

    mTLS is the noted alternative (spec open question); the contract
    holds under either, and the header pair travels the same way.
    """
    mac = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    )
    return mac.hexdigest()


class EdgeContainmentExecutor:
    """Tarpit / synthetic latency / session pinning on operator-run infra.

    Vigil never sits inline on TCP — this executor makes ONE signed HTTPS
    call per verb to an endpoint the OPERATOR runs (spec scope boundary).
    The endpoint owns its own state, caps its own concurrency, and never
    claims stealth; Vigil's gate caps leases and TTLs on its side.

    ``base_url`` and ``signing_secret`` come from settings
    (``daemon_fastpath_edge_*``); constructor injection keeps tests honest
    without monkeypatching settings.
    """

    action_types: ClassVar[Tuple[str, ...]] = (
        "tarpit",
        "latency_injection",
        "pin_session",
    )

    def __init__(
        self,
        base_url: str,
        signing_secret: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.signing_secret = signing_secret
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls) -> Optional["EdgeContainmentExecutor"]:
        """The registry wiring: registered only when the endpoint is
        configured. An unconfigured verb is NOT an apply failure — it is
        simply not offered, and the gate never issues what the registry
        cannot execute."""
        settings = get_settings()
        base_url = getattr(settings, "daemon_fastpath_edge_endpoint_url", None)
        secret = getattr(settings, "daemon_fastpath_edge_signing_secret", None)
        if not base_url or not secret:
            return None
        return cls(base_url=str(base_url), signing_secret=str(secret))

    def _headers(self, body: bytes) -> Dict[str, str]:
        timestamp = str(int(time.time()))
        return {
            "Content-Type": "application/json",
            "X-Vigil-Timestamp": timestamp,
            "X-Vigil-Signature": _sign(self.signing_secret, timestamp, body),
        }

    async def apply(self, lease: LeaseSpec) -> Dict[str, Any]:
        if lease.action_type not in self.action_types:
            raise ExecutorError(
                f"edge executor does not implement {lease.action_type!r}"
            )
        return await asyncio.to_thread(self._apply_sync, lease)

    def _apply_sync(self, lease: LeaseSpec) -> Dict[str, Any]:
        body = httpx.Request(
            "POST",
            self.base_url,
            json={
                "lease_id": lease.lease_id,
                "action": lease.action_type,
                "target": lease.entity_id,
                "target_type": lease.entity_type,
                "ttl_seconds": lease.ttl_seconds,
            },
        ).read()
        resp = httpx.post(
            f"{self.base_url}/v1/containments",
            headers=self._headers(body),
            content=body,
            timeout=self.timeout_seconds,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code not in (200, 201):
            raise ExecutorError(
                f"edge containment apply failed: status={resp.status_code} "
                f"body={data!r}"
            )
        undo_token = data.get("undo_token")
        if not undo_token:
            # The endpoint MUST return an undo token; refusing to record
            # an effect we could not undo is the whole contract.
            raise ExecutorError("edge containment apply returned no undo_token")
        return {"undo_token": str(undo_token)}

    async def undo(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        await asyncio.to_thread(self._undo_sync, lease_id, undo_payload)

    def _undo_sync(self, lease_id: str, undo_payload: Dict[str, Any]) -> None:
        undo_token = undo_payload.get("undo_token")
        if undo_token:
            url = f"{self.base_url}/v1/containments/{undo_token}"
        else:
            # Crash-orphan path: no stored token. The endpoint can resolve
            # the object from the lease id — the contract's DELETE-by-lease
            # route — so undo never depends on a stored token alone.
            url = f"{self.base_url}/v1/containments/by-lease/{lease_id}"
        body = httpx.Request("DELETE", url).read()
        resp = httpx.delete(
            url,
            headers=self._headers(body),
            content=body,
            timeout=self.timeout_seconds,
        )
        # 404 = already undone — idempotent success, never an error.
        if resp.status_code not in (200, 204, 404):
            raise ExecutorError(
                f"edge containment undo failed: status={resp.status_code}"
            )


# ----------------------------------------------------------------------
# The registry — owned by THIS package, never the approval sweep
# ----------------------------------------------------------------------


class ExecutorRegistry:
    """The fastpath package's own executor registry.

    Keyed by action type. The daemon's approval sweep
    (``_approved_action_executor``) never sees these objects; the only
    caller of ``apply``/``undo`` is the ledger's drivers and the TTL
    sweeper.
    """

    def __init__(self) -> None:
        self._executors: Dict[str, ContainmentExecutor] = {}

    def register(self, executor: Any) -> None:
        types = getattr(executor, "action_types", None) or (
            getattr(executor, "action_type", None),
        )
        if not types or not all(types):
            raise ExecutorError(
                f"{executor!r} declares no action type — cannot register"
            )
        for action_type in types:
            self._executors[str(action_type)] = executor

    def get(self, action_type: str) -> Optional[ContainmentExecutor]:
        return self._executors.get(action_type)

    def action_types(self) -> Tuple[str, ...]:
        return tuple(sorted(self._executors))


def default_registry() -> ExecutorRegistry:
    """The v1 wiring: Cloudflare challenge/rate-limit always offered (they
    fail closed on missing integration config), the edge verbs only when
    an operator endpoint is configured."""
    registry = ExecutorRegistry()
    registry.register(CloudflareChallengeExecutor())
    registry.register(CloudflareRateLimitExecutor())
    edge = EdgeContainmentExecutor.from_settings()
    if edge is not None:
        registry.register(edge)
    return registry
