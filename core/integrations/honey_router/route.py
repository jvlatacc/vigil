"""Honey-routing enforcement backends.

The enforcement seam behind the ``honey_route`` response action. The
decision plane (``core.response``) approves a route; this module turns it
into a real one. Everything here is synchronous — the Kubernetes client is
sync — and callers off the event loop wrap it in ``asyncio.to_thread``
(the Cloudflare executor and fastpath sweep precedent).

Two properties the whole module is built around:

**Fail-safe direction.** Any backend failure routes nothing and says so —
the normal traffic path is untouched. Unrouting only ever *restores* the
normal path, so its failure mode (stale policy, retried by the daemon's
TTL sweep) errs toward keeping the decoy up, never toward blocking.

**Honest failures.** A missing k8s client, an absent Cilium CRD, a decoy
endpoint that is not a routable IP — every one returns
``{"success": False, "error": ...}``. A success result is returned only
when the policy object is verifiably in place. The ``isolate_host`` rule:
never record an enforcement that did not happen.

The k8s client lives behind lazy imports: an install without the
``kubernetes`` package never imports it and gets a structured failure at
route time instead of an import error at startup.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Protocol, Tuple

from core.integrations._base.config import resolve
from core.integrations.honey_router.descriptor import HONEY_ROUTER

logger = logging.getLogger(__name__)

# The Cilium primitive this backend emits. CANDIDATE, pinned at build time:
# the golden test validates generated manifests against the vendored CRD
# (cilium v1.17.3, tests/unit/integrations/fixtures/), and the kind-cluster
# runbook (docs/runbooks/honey-routing-kind-verification.md) is where the
# primitive is verified against a live cluster — the golden test pins the
# shape, only the kind run proves the engagement.
CILIUM_API_GROUP = "cilium.io"
CILIUM_API_VERSION = "v2"
CILIUM_LRP_PLURAL = "ciliumlocalredirectpolicies"
CILIUM_LRP_CRD_NAME = f"{CILIUM_LRP_PLURAL}.{CILIUM_API_GROUP}"
LRP_API_VERSION = f"{CILIUM_API_GROUP}/{CILIUM_API_VERSION}"
LRP_KIND = "CiliumLocalRedirectPolicy"

# Labels every generated policy carries. The decoy deployment (the sibling
# workstream that owns services/decoy/ and the compose `decoys` profile)
# must label decoy pods with vigil.io/decoy-id so the redirect backend can
# select them — that contract is documented in the runbook.
_LABEL_MANAGED_BY = "app.kubernetes.io/managed-by"
_LABEL_ROUTE = "vigil.io/honey-route"
_LABEL_DECOY = "vigil.io/decoy-id"
_LABEL_ATTACKER = "vigil.io/attacker"


@dataclass(frozen=True)
class DecoyTarget:
    """The decoy a route lands on, resolved from ``mtd_decoy_registry``.

    The registry row's ``endpoint`` is ``host:port`` — the address the decoy
    presents. For the Cilium backend that address must be a routable IP
    (typically the decoy Service's ClusterIP): the LRP frontend matches a
    literal destination address, and resolving a DNS name through the
    Kubernetes API is deliberately out of scope for v1 (an honest failure
    instead — see :meth:`CiliumBackend.route`).
    """

    decoy_id: str
    name: str
    kind: str
    endpoint_host: str
    endpoint_port: int
    namespace: str


class RouteBackend(Protocol):
    """One enforcement technology that can pin an attacker to a decoy."""

    name: str

    def route(self, attacker_ip: str, decoy: DecoyTarget) -> Dict[str, Any]:
        """Pin the attacker's flows to the decoy. Never raises: the result
        dict is the contract — ``{"success": True, ...}`` or
        ``{"success": False, "error": ...}``."""
        ...

    def unroute(self, attacker_ip: str) -> Dict[str, Any]:
        """Remove the attacker's routing, restoring the normal path."""
        ...


def parse_endpoint(endpoint: str) -> Tuple[str, int]:
    """Split a registry ``endpoint`` into (host, port).

    Handles ``host:port`` and bracketed IPv6 ``[host]:port``. Raises
    ``ValueError`` on a missing/invalid port — malformed endpoints fail
    loudly rather than routing into the void.
    """
    text = endpoint.strip()
    if text.startswith("["):  # [2001:db8::1]:22
        host, _, rest = text.partition("]")
        if not rest.startswith(":"):
            raise ValueError(f"endpoint {endpoint!r} has no port")
        port_text = rest[1:]
    else:
        host, _, port_text = text.rpartition(":")
        if not host:  # no colon at all
            raise ValueError(f"endpoint {endpoint!r} has no port")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError(f"endpoint {endpoint!r} port {port} out of range")
    return host, port


def policy_name_for(attacker_ip: str) -> str:
    """The deterministic policy name for one attacker's route.

    Hashed rather than embedded: policy names must be RFC 1123 DNS labels
    (lowercase alphanumerics, ``-``), and attacker-controlled bytes must
    never reach an object name. Deterministic so unroute finds the policy
    without a cluster-side search.
    """
    digest = hashlib.sha256(attacker_ip.encode("utf-8")).hexdigest()[:12]
    return f"vigil-honey-{digest}"


def attacker_label_value(attacker_ip: str) -> str:
    """A sanitized, audit-friendly label value naming the attacker.

    Prefixed so the value always starts and ends alphanumerically no
    matter what the address looked like.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9.\-]", "-", attacker_ip)[:40]
    return f"ip-{sanitized.strip('-')}"


def build_local_redirect_policy(
    attacker_ip: str,
    decoy: DecoyTarget,
    namespace: Optional[str] = None,
) -> Dict[str, Any]:
    """The ``CiliumLocalRedirectPolicy`` manifest for one attacker→decoy route.

    Pure: no cluster access, no config reads — the golden test pins this
    byte-for-byte and validates it against the vendored CRD schema.

    Frontend is an ``addressMatcher`` on the decoy's endpoint IP: LRP
    matching is destination-based (traffic *to that address* is redirected),
    so the route captures whatever flows arrive at the address the decoy
    presents — the transparent-reroute model where the decoy stands in at
    the probed address. The routing is keyed to one attacker in the policy
    name and labels (and unrouted per attacker); the redirect itself is
    address-scoped, which is the LRP primitive's documented granularity and
    one of the things the kind-cluster verification confirms is acceptable
    for the deployment's exposure model.

    Raises ``ValueError`` when the decoy endpoint host is not a routable IP
    (the v1 endpoint contract — see :class:`DecoyTarget`).
    """
    # Validates and canonicalizes (rejects DNS names, "localhost", bare
    # hostnames) — a hostname endpoint must fail here, loudly, not quietly
    # produce a policy that matches nothing.
    addr = ipaddress.ip_address(decoy.endpoint_host)
    port_entry = {"port": str(decoy.endpoint_port), "protocol": "TCP"}
    ns = namespace or decoy.namespace
    return {
        "apiVersion": LRP_API_VERSION,
        "kind": LRP_KIND,
        "metadata": {
            "name": policy_name_for(attacker_ip),
            "namespace": ns,
            "labels": {
                _LABEL_MANAGED_BY: "vigil",
                _LABEL_ROUTE: "true",
                _LABEL_DECOY: decoy.decoy_id,
                _LABEL_ATTACKER: attacker_label_value(attacker_ip),
            },
        },
        "spec": {
            "redirectFrontend": {
                "addressMatcher": {
                    "ip": str(addr),
                    "toPorts": [port_entry],
                }
            },
            "redirectBackend": {
                "localEndpointSelector": {
                    "matchLabels": {_LABEL_DECOY: decoy.decoy_id}
                },
                "toPorts": [port_entry],
            },
            # The decoy's own replies must not be re-redirected into itself.
            # Decoy egress is default-deny anyway; this closes the loop even
            # if that invariant is ever misconfigured.
            "skipRedirectFromBackend": True,
        },
    }


@dataclass(frozen=True)
class DecoyResolution:
    """The outcome of a registry lookup, with the error named, not swallowed."""

    target: Optional[DecoyTarget]
    # "" on success; "decoy_not_found" | "decoy_retired" | "malformed_endpoint".
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == "" and self.target is not None


def resolve_decoy(decoy_id: str, namespace: str) -> DecoyResolution:
    """Resolve a decoy id to a routable target from ``mtd_decoy_registry``.

    Only an active row routes; a retired decoy is a named refusal, not a
    fallback to some other decoy — the registry is the operator's word on
    what may receive attacker traffic.
    """
    # Imported here, not at module top: this module sits in core.integrations
    # and must stay importable on installs that never touch the storage layer
    # (the MCP server imports it for its tool list).
    from core.storage.connection import get_db_manager
    from core.storage.models.mtd import MtdDecoyRegistry

    db = get_db_manager()
    with db.session_scope() as session:
        row = session.get(MtdDecoyRegistry, decoy_id)
        if row is None:
            return DecoyResolution(None, error="decoy_not_found")
        if row.status != "active":
            return DecoyResolution(None, error="decoy_retired")
        try:
            host, port = parse_endpoint(row.endpoint)
        except ValueError as e:
            logger.error("Decoy %s has a malformed endpoint: %s", decoy_id, e)
            return DecoyResolution(None, error="malformed_endpoint")
        return DecoyResolution(
            target=DecoyTarget(
                decoy_id=row.decoy_id,
                name=row.name,
                kind=row.kind,
                endpoint_host=host,
                endpoint_port=port,
                namespace=namespace,
            )
        )


def get_backend() -> Tuple[Optional[RouteBackend], str]:
    """The configured backend, or the honest failure naming what is missing."""
    cfg = resolve(HONEY_ROUTER)
    name = cfg.get("backend") or "cilium"
    if name == "cilium":
        return CiliumBackend(), ""
    return None, f"unknown honey-router backend {name!r}"


def route(
    attacker_ip: str, decoy_id: str, ttl_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Route an approved attacker into a registered decoy.

    The executor seam the ``honey_route`` dispatch calls. ``ttl_seconds``
    is carried through to the result for the audit trail — TTL enforcement
    belongs to the daemon's sweep, not to the policy object, which has no
    TTL field.
    """
    namespace = resolve(HONEY_ROUTER).get("namespace") or "default"
    resolution = resolve_decoy(decoy_id, namespace)
    if not resolution.ok:
        return {
            "success": False,
            "error": resolution.error,
            "message": f"Decoy {decoy_id!r} cannot receive routes",
        }
    backend, err = get_backend()
    if backend is None:
        return {"success": False, "error": "no_route_backend", "message": err}
    result = backend.route(attacker_ip, resolution.target)
    if result.get("success"):
        result.setdefault("decoy_id", decoy_id)
        result.setdefault("session_ttl_seconds", ttl_seconds)
    return result


def unroute(attacker_ip: str) -> Dict[str, Any]:
    """Remove one attacker's routing, restoring the normal traffic path."""
    backend, err = get_backend()
    if backend is None:
        return {"success": False, "error": "no_route_backend", "message": err}
    return backend.unroute(attacker_ip)


def list_active_decoys() -> list[Dict[str, Any]]:
    """The active decoys, for the read-only MCP tool surface.

    ``canary_credential_ref`` is deliberately absent: it points into the
    credential store, and the tool surface must not become a map to it.
    """
    from core.storage.connection import get_db_manager
    from core.storage.models.mtd import MtdDecoyRegistry

    db = get_db_manager()
    with db.session_scope() as session:
        rows = (
            session.query(MtdDecoyRegistry)
            .filter(MtdDecoyRegistry.status == "active")
            .order_by(MtdDecoyRegistry.decoy_id)
            .all()
        )
        return [
            {
                "decoy_id": r.decoy_id,
                "name": r.name,
                "kind": r.kind,
                "endpoint": r.endpoint,
                "rotated_at": r.rotated_at.isoformat() if r.rotated_at else None,
            }
            for r in rows
        ]


def is_route_expired(
    executed_at: Optional[str],
    ttl_seconds: Any,
    now: datetime,
) -> bool:
    """Whether one executed route's TTL has passed.

    Pure so the sweep's selection is unit-testable without a database. A
    row missing either piece of data is never expired by the sweep —
    unrouting on guessed data is how production paths get silently cut.
    """
    if not executed_at or ttl_seconds is None:
        return False
    try:
        executed = datetime.fromisoformat(str(executed_at).replace("Z", "+00:00"))
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        return False
    if executed.tzinfo is None:
        executed = executed.replace(tzinfo=now.tzinfo)
    return now >= executed + timedelta(seconds=ttl)


def needs_unroute(execution_result: Optional[Dict[str, Any]]) -> bool:
    """Whether an executed route still needs its unroute recorded.

    A reversal already recorded as successful suppresses re-unrouting;
    anything else (no reversal, failed attempts) keeps the row eligible so
    the sweep retries.
    """
    reversal = (execution_result or {}).get("reversal") or {}
    return not bool(reversal.get("success"))


class CiliumBackend:
    """Cilium LRP enforcement, for clusters that already run Cilium.

    Emits a :class:`CiliumLocalRedirectPolicy` pinning flows destined to the
    decoy's endpoint address onto the decoy pods (selected by
    ``vigil.io/decoy-id``). The primitive is a candidate by construction:
    the golden test verifies the manifest against the vendored CRD schema
    (cilium v1.17.3), and the kind-cluster runbook is the verification that
    the policy actually engages attacker flows on a live cluster — including
    confirming the destination-based matching granularity documented on
    :func:`build_local_redirect_policy`.

    Cluster access is detected, not assumed: the CRD must exist (a cluster
    without Cilium CRDs is a structured failure, never a half-applied
    policy), and the k8s client import is deferred until a route is actually
    applied so installs without the package never touch it.
    """

    name = "cilium"

    def _k8s(self) -> Tuple[Optional[Any], str]:
        """(client module, error) — lazy import, then config load."""
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config
        except ImportError as e:
            return None, f"kubernetes client unavailable: {e}"
        try:
            # In-cluster (daemon pod on the cluster) first, kubeconfig second
            # (operator workstation, kind runbook).
            k8s_config.load_incluster_config()
        except Exception:  # noqa: BLE001 — config loaders raise their own types
            try:
                k8s_config.load_kube_config()
            except Exception as e:  # noqa: BLE001
                return None, f"no kubernetes configuration available: {e}"
        return k8s_client, ""

    def _crd_available(self, k8s_client: Any) -> Tuple[bool, str]:
        """Whether the cluster serves the CiliumLocalRedirectPolicy CRD."""
        api = k8s_client.ApiextensionsV1Api()
        try:
            api.read_custom_resource_definition(name=CILIUM_LRP_CRD_NAME)
        except k8s_client.ApiException as e:
            if e.status == 404:
                return False, (
                    f"{CILIUM_LRP_CRD_NAME} not found — this cluster does not "
                    "run Cilium (or the CRD is not installed)"
                )
            return False, f"CRD lookup failed: {e.reason}"
        return True, ""

    def route(self, attacker_ip: str, decoy: DecoyTarget) -> Dict[str, Any]:
        k8s_client, err = self._k8s()
        if k8s_client is None:
            return {"success": False, "error": "k8s_client_unavailable", "message": err}
        ok, err = self._crd_available(k8s_client)
        if not ok:
            return {"success": False, "error": "cilium_crd_unavailable", "message": err}
        try:
            manifest = build_local_redirect_policy(attacker_ip, decoy)
        except ValueError as e:
            return {
                "success": False,
                "error": "decoy_endpoint_not_routable_ip",
                "message": str(e),
            }
        api = k8s_client.CustomObjectsApi()
        try:
            api.create_namespaced_custom_object(
                group=CILIUM_API_GROUP,
                version=CILIUM_API_VERSION,
                namespace=manifest["metadata"]["namespace"],
                plural=CILIUM_LRP_PLURAL,
                body=manifest,
            )
        except k8s_client.ApiException as e:
            if e.status == 409:
                # The policy already exists — the route IS in effect. A
                # truthful success (the isolate_host rule is about recording
                # enforcement that never happened; this enforcement exists).
                logger.info(
                    "Honey-route policy %s already present for %s",
                    manifest["metadata"]["name"],
                    attacker_ip,
                )
                return {
                    "success": True,
                    "backend": self.name,
                    "policy": manifest["metadata"]["name"],
                    "namespace": manifest["metadata"]["namespace"],
                    "already_existed": True,
                    "manifest": manifest,
                }
            return {
                "success": False,
                "error": "cilium_api_error",
                "message": f"policy apply failed: {e.reason}",
            }
        logger.info(
            "Honey-routed %s into decoy %s (policy %s)",
            attacker_ip,
            decoy.decoy_id,
            manifest["metadata"]["name"],
        )
        return {
            "success": True,
            "backend": self.name,
            "policy": manifest["metadata"]["name"],
            "namespace": manifest["metadata"]["namespace"],
            "manifest": manifest,
        }

    def unroute(self, attacker_ip: str) -> Dict[str, Any]:
        k8s_client, err = self._k8s()
        if k8s_client is None:
            return {"success": False, "error": "k8s_client_unavailable", "message": err}
        namespace = resolve(HONEY_ROUTER).get("namespace") or "default"
        name = policy_name_for(attacker_ip)
        api = k8s_client.CustomObjectsApi()
        try:
            api.delete_namespaced_custom_object(
                group=CILIUM_API_GROUP,
                version=CILIUM_API_VERSION,
                namespace=namespace,
                plural=CILIUM_LRP_PLURAL,
                name=name,
            )
        except k8s_client.ApiException as e:
            if e.status == 404:
                # Already gone: the normal path is restored either way. The
                # fail-safe direction is satisfied — this is not an error.
                return {
                    "success": True,
                    "backend": self.name,
                    "policy": name,
                    "already_gone": True,
                }
            return {
                "success": False,
                "error": "cilium_api_error",
                "message": f"policy delete failed: {e.reason}",
            }
        logger.info("Unrouted %s (policy %s) — normal path restored", attacker_ip, name)
        return {"success": True, "backend": self.name, "policy": name}


async def sweep_expired_routes(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Unroute every executed ``honey_route`` whose TTL has passed.

    The daemon scheduler's tick calls this (the fastpath sweep precedent:
    off-thread, datastore-enforced, runs regardless of the MTD enable
    switch — disabling MTD stops new routes, it never strands live ones).
    Returns the sweep's tally for the scheduler stats.
    """
    from core.time import utcnow

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sweep_expired_routes_sync, now or utcnow())


def _sweep_expired_routes_sync(now: datetime) -> Dict[str, Any]:
    from core.response.approval_service import ActionStatus, ActionType, ApprovalService

    service = ApprovalService()
    actions = service.list_actions(
        status=ActionStatus.EXECUTED, action_type=ActionType.HONEY_ROUTE
    )
    expired = unrouted = failed = 0
    for action in actions:
        params = action.parameters or {}
        if not is_route_expired(
            action.executed_at, params.get("session_ttl_seconds"), now
        ):
            continue
        if not needs_unroute(action.execution_result):
            continue
        expired += 1
        result = unroute(action.target)
        service.record_reversal(
            action.action_id,
            {
                "success": bool(result.get("success")),
                "error": result.get("error", ""),
                "policy": result.get("policy", ""),
                "reason": "ttl_expired",
            },
        )
        if result.get("success"):
            unrouted += 1
        else:
            failed += 1
            logger.error(
                "TTL unroute for %s (action %s) failed: %s — retried next sweep",
                action.target,
                action.action_id,
                result.get("error"),
            )
    return {
        "scanned": len(actions),
        "expired": expired,
        "unrouted": unrouted,
        "failed": failed,
    }
