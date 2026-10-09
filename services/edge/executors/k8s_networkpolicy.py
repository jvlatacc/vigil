"""Cluster-mode containment: reversible egress-deny NetworkPolicy objects.

Kubernetes NetworkPolicy is allowlist-based — there is no native "deny one
IP". The reversible shape this executor applies is an egress policy that
allows every destination *except* the target (`ipBlock` with an `except`
entry) for every pod in the managed namespace. One tradeoff is inherent to
the object model: a pod selected by an existing, stricter egress policy
gains the wider allowance, because a pod may egress anywhere any selecting
policy permits. Scoped RBAC (NetworkPolicy verbs in managed namespaces
only) and the TTL reaper bound the blast radius; the alternative — a
CNI-specific deny CRD — is a new dependency the design spec excludes for
v1.

Policy names are deterministic (`vigil-edge-block-<digest of target>`), so
apply is create-or-update: re-applying the same block rewrites the same
object instead of accumulating siblings. Every object carries the
``vigil.ai/edge-managed`` label so operators can see and audit what the
edge daemon owns.

Targets come from observations — untrusted input. They are parsed through
``ipaddress`` before anything is built; anything that is not a bare IP
address fails the action without a request ever leaving the process.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from services.edge.executors.registry import ActionResult
from services.edge.gate.gate import Action

logger = logging.getLogger(__name__)

GROUP = "networking.k8s.io"
VERSION = "v1"
LABEL_MANAGED = "vigil.ai/edge-managed"
ANNOTATION_TARGET = "vigil.ai/edge-target"
ANNOTATION_TTL = "vigil.ai/edge-ttl-seconds"
ANNOTATION_APPLIED_AT = "vigil.ai/edge-applied-at"
NAME_PREFIX = "vigil-edge-block-"


@dataclass(frozen=True)
class K8sExecutorConfig:
    api_url: str
    token_file: Path
    ca_file: Path


def policy_name(target: str) -> str:
    """DNS-1123 name derived from the target IP — same target, same name,
    so re-apply rewrites instead of accumulating."""
    digest = hashlib.sha256(target.encode()).hexdigest()[:12]
    return f"{NAME_PREFIX}{digest}"


def policy_body(
    namespace: str, target: str, ttl_seconds: int, *, now: datetime
) -> dict[str, Any]:
    """The egress-allow-all-except-target NetworkPolicy for one namespace."""
    ip = ipaddress.ip_address(target)  # callers parse first; kept total
    # The base CIDR is the whole address space (allow all destinations);
    # the except entry is the target at its full prefix length (deny it).
    base = "::/0" if ip.version == 6 else "0.0.0.0/0"
    return {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": policy_name(str(ip)),
            "namespace": namespace,
            "labels": {LABEL_MANAGED: "true"},
            "annotations": {
                ANNOTATION_TARGET: str(ip),
                ANNOTATION_TTL: str(ttl_seconds),
                ANNOTATION_APPLIED_AT: now.isoformat(),
            },
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "ipBlock": {
                                "cidr": base,
                                "except": [f"{ip}/{ip.max_prefixlen}"],
                            }
                        }
                    ]
                }
            ],
        },
    }


class K8sNetworkPolicyExecutor:
    """Applies and removes egress NetworkPolicies through the API server.

    The HTTP transport is injectable: tests pass ``httpx.MockTransport`` and
    never need a cluster. Auth is the pod's service-account token read fresh
    per apply (mounted tokens rotate); no other credential kind is spoken.
    """

    name = "k8s_networkpolicy"
    action_types = frozenset({"block_ip"})

    def __init__(
        self,
        config: K8sExecutorConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    async def apply(
        self, action: Action, ttl_seconds: int, *, namespaces: tuple[str, ...] = ()
    ) -> ActionResult:
        try:
            ip = ipaddress.ip_address(action.target)
        except ValueError:
            return ActionResult(
                success=False, error=f"invalid_target:{action.target!r}"
            )
        if not namespaces:
            # Nothing signed names this executor's scope: acting on an
            # unstated namespace would widen the bundle.
            return ActionResult(success=False, error="no_namespaces_in_scope")

        token = self._read_token()
        if token is None:
            return ActionResult(success=False, error="token_unreadable")

        now = datetime.now(UTC)
        applied: list[str] = []
        try:
            async with httpx.AsyncClient(
                base_url=self._config.api_url.rstrip("/"),
                transport=self._transport,
                headers={"Authorization": f"Bearer {token}"},
                verify=str(self._config.ca_file) if self._transport is None else False,
                timeout=10.0,
            ) as client:
                for namespace in namespaces:
                    body = policy_body(namespace, str(ip), ttl_seconds, now=now)
                    response = await client.put(
                        f"/apis/{GROUP}/{VERSION}/namespaces/{namespace}"
                        f"/networkpolicies/{body['metadata']['name']}",
                        json=body,
                    )
                    if response.status_code not in (200, 201):
                        return ActionResult(
                            success=False,
                            error=(
                                f"api_error:{response.status_code}:"
                                f"{namespace}/{body['metadata']['name']}"
                            ),
                        )
                    applied.append(f"{namespace}/{body['metadata']['name']}")
        except httpx.HTTPError as exc:
            logger.error("k8s executor apply failed: %s", exc)
            return ActionResult(success=False, error=f"api_unreachable:{exc}")
        return ActionResult(
            success=True,
            ref=json.dumps({"networkpolicies": applied}, sort_keys=True),
        )

    async def revert(self, ref: str) -> ActionResult:
        try:
            data = json.loads(ref)
            namespaced = list(data["networkpolicies"])
        except (ValueError, KeyError, TypeError):
            return ActionResult(success=False, error=f"unreadable_ref:{ref!r}")

        token = self._read_token()
        if token is None:
            return ActionResult(success=False, error="token_unreadable")

        try:
            async with httpx.AsyncClient(
                base_url=self._config.api_url.rstrip("/"),
                transport=self._transport,
                headers={"Authorization": f"Bearer {token}"},
                verify=str(self._config.ca_file) if self._transport is None else False,
                timeout=10.0,
            ) as client:
                for ns_name in namespaced:
                    namespace, _, name = str(ns_name).partition("/")
                    if not namespace or not name:
                        return ActionResult(
                            success=False, error=f"unreadable_ref:{ref!r}"
                        )
                    response = await client.delete(
                        f"/apis/{GROUP}/{VERSION}/namespaces/{namespace}"
                        f"/networkpolicies/{name}"
                    )
                    if response.status_code in (200, 202, 404):
                        # 404 = already gone: revert is idempotent by design.
                        continue
                    return ActionResult(
                        success=False,
                        error=f"api_error:{response.status_code}:{ns_name}",
                    )
        except httpx.HTTPError as exc:
            logger.error("k8s executor revert failed: %s", exc)
            return ActionResult(success=False, error=f"api_unreachable:{exc}")
        return ActionResult(success=True, ref=ref)

    def _read_token(self) -> str | None:
        try:
            token = self._config.token_file.read_text().strip()
        except OSError:
            return None
        return token or None
