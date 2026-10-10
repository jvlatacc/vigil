"""Honey-router integration descriptor — source of truth for its registry entries.

Configured through Settings → Integrations like every other slice. No
secret fields: the Cilium backend talks to the Kubernetes API with the
pod's in-cluster service account (or the operator's kubeconfig), never
with a Vigil-stored credential.
"""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

HONEY_ROUTER = register_descriptor(
    IntegrationDescriptor(
        id="honey_router",
        category="Network Security",
        mcp_server_names=("honey-router",),
        fields=(
            # Which enforcement backend applies routes. Only "cilium" exists;
            # anything else is an honest failure at route time, not a silent
            # no-op.
            IntegrationField("backend", default="cilium"),
            # Namespace the decoy workloads and their redirect policies live
            # in. The policy object is namespaced, so this must be where the
            # decoy pods actually run.
            IntegrationField("namespace", default="default"),
        ),
    )
)
