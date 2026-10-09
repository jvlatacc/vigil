"""Cilium driver — Kubernetes enforcement (contained spike).

PR2's brief expects a spike here: the repo has no Kubernetes client
precedent, and Cilium has **no native "source IP X → honeypot Y"
primitive**. This driver implements the mechanics that ARE solid —
per-lease ``CiliumLocalRedirectPolicy`` objects applied/removed/listed via
the Kubernetes client, label-scoped so reconcile and drain are exact — and
documents the limitation it hits:

**Spike finding 1 — CLRP is destination-scoped, not source-scoped.**
``addressMatcher.matchIps`` redirects traffic *to* the matched destination
IPs; there is no source-IP predicate on the policy. A lease's policy
therefore scopes to the destination IPs the probes hit and redirects ALL
sources hitting them — acceptable only where the decoy destination IPs are
dedicated (not real production addresses). The per-source paths (bounded
expiring eBPF map of suspicious sources at TC/XDP, or Envoy TPROXY config)
are the documented follow-up; the driver interface below does not change
when that lands — ``build_policy`` grows a source selector.

**Spike finding 2 — per-port redirection is coarse.** CLRP's
``addressMatcher`` redirects whole addresses; ``excludePorts`` carves
traffic out rather than mapping ports. The per-port decoy map
(``DECOY_CONTROLLER_DECOY_MAP``) applies to the nftables driver; here the
redirect target is one decoy IP (``DECOY_CONTROLLER_DECOY_IP``).

The Kubernetes client dependency is scoped to this service
(``services/decoy_controller/requirements.txt``) and imported lazily so the
shared image without it still runs the memory and nftables drivers.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from services.decoy_controller.config import ControllerConfig
from services.decoy_controller.registry import Rule

logger = logging.getLogger(__name__)

GROUP = "cilium.io"
VERSION = "v2"
PLURAL = "ciliumlocalredirectpolicies"
MANAGED_BY = "vigil-decoy-controller"
LABEL_MANAGED = "app.kubernetes.io/managed-by"
LABEL_LEASE = "vigil.io/lease-id"
DEFAULT_NAMESPACE = "decoys"
# Lease ids are "lease-<hex>"; anything else is sanitized into the name.
_SAFE_NAME_RE = re.compile(r"[^a-z0-9-]+")


def policy_name(lease_id: str) -> str:
    """A valid k8s object name for one lease — deterministic, ≤ 63 chars."""
    safe = _SAFE_NAME_RE.sub("-", lease_id.lower())[:48].strip("-") or "lease"
    return f"vigil-decoy-{safe}"


def build_policy(rule: Rule, namespace: str, decoy_ip: str) -> Dict[str, Any]:
    """The CLRP manifest for one lease — pure, unit-tested directly.

    See the module docstring for the two spike findings this shape carries.
    IPv4-only by construction: ``redirectAddress.v4`` and /32 matchers cannot
    express an IPv6 lease; IPv6 destinations are skipped loudly rather than
    rendered into an invalid manifest.
    """
    match_ips = []
    for ip in sorted(set(rule.destination_ips)):
        if ":" in ip:
            logger.warning(
                "Lease %s: cilium driver is IPv4-only; skipping IPv6 " "destination %s",
                rule.lease_id,
                ip,
            )
            continue
        match_ips.append(f"{ip}/32")
    return {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "CiliumLocalRedirectPolicy",
        "metadata": {
            "name": policy_name(rule.lease_id),
            "namespace": namespace,
            "labels": {
                LABEL_MANAGED: MANAGED_BY,
                LABEL_LEASE: rule.lease_id,
            },
        },
        "spec": {
            "addressMatcher": {
                # /32 per destination: the lease names hosts, never ranges.
                "matchIps": match_ips,
                "redirectAddress": {"v4": [decoy_ip]},
            },
        },
    }


class CiliumDriver:
    """Syncs lease policies into the cluster as CLRP objects."""

    name = "cilium"

    def __init__(
        self,
        config: ControllerConfig,
        api: Optional[Any] = None,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> None:
        self._config = config
        self._api = api if api is not None else _custom_objects_api()
        self._namespace = namespace

    def boot(self) -> None:
        """Delete every policy this controller manages (registry is empty)."""
        for name in self._managed_names():
            self._delete(name)
            logger.info("Boot drain: removed policy %s", name)

    def sync(self, rules: Sequence[Rule]) -> Dict[str, str]:
        """Converge cluster state to exactly the leases' policies."""
        for rule in rules:
            name = policy_name(rule.lease_id)
            body = build_policy(rule, self._namespace, self._config.decoy_ip)
            self._upsert(name, body)

        held = set(self._managed_names())
        desired = {policy_name(rule.lease_id) for rule in rules}
        for name in held - desired:
            self._delete(name)
        return {
            rule.lease_id: self.ref_for(policy_name(rule.lease_id)) for rule in rules
        }

    @staticmethod
    def ref_for(name: str) -> str:
        return f"cilium:{name}"

    def _upsert(self, name: str, body: Dict[str, Any]) -> None:
        try:
            self._api.create_cluster_custom_object(
                group=GROUP, version=VERSION, plural=PLURAL, body=body
            )
        except Exception as e:  # noqa: BLE001 — the k8s client raises plain
            # APIException subclasses; 409 (exists) is the idempotent case.
            if "409" not in str(e):
                raise
            self._api.patch_cluster_custom_object(
                group=GROUP, version=VERSION, plural=PLURAL, name=name, body=body
            )

    def _managed_names(self) -> List[str]:
        listing = self._api.list_cluster_custom_object(
            group=GROUP,
            version=VERSION,
            plural=PLURAL,
            label_selector=f"{LABEL_MANAGED}={MANAGED_BY}",
        )
        items = (listing or {}).get("items") or []
        names: List[str] = []
        for item in items:
            name = ((item.get("metadata") or {}).get("name") or "").strip()
            if name:
                names.append(name)
        return names

    def _delete(self, name: str) -> None:
        try:
            self._api.delete_cluster_custom_object(
                group=GROUP, version=VERSION, plural=PLURAL, name=name
            )
        except Exception as e:  # noqa: BLE001 — 404 (already gone) is the
            # only acceptable failure for a removal.
            if "404" not in str(e):
                raise


def _custom_objects_api() -> Any:
    """Build the CustomObjectsApi, in-cluster config first, kubeconfig second.

    Raises with a name-the-fix message when the kubernetes client is not
    installed — the dependency is scoped to this service on purpose.
    """
    try:
        import kubernetes
    except ImportError as e:
        raise RuntimeError(
            "The cilium driver needs the kubernetes client; install "
            "services/decoy_controller/requirements.txt (the dependency is "
            "scoped to this service and must not enter Vigil's shared "
            "requirements)."
        ) from e
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
    return kubernetes.client.CustomObjectsApi()
