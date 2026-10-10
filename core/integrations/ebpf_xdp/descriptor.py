"""eBPF/XDP enforcement descriptor — source of truth for its registry entries."""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

EBPF_XDP = register_descriptor(
    IntegrationDescriptor(
        id="ebpf-xdp",
        category="Network Security",
        mcp_server_names=("ebpf-xdp",),
        fields=(
            # Where the per-host enforcement daemon (services/enforcement) serves
            # its loopback-only API. Loopback default: the API can move kernel
            # state, so it must never face a network.
            IntegrationField("enforcement_url"),
            # ADR-0014 shared-secret model — the daemon refuses to serve without
            # this token and every /v1 route checks it (Bearer).
            IntegrationField("enforcement_token", secret=True),
            # Host interface the daemon's XDP program attaches to; the daemon
            # reads its own VIGIL_ENFORCEMENT_INTERFACE, this is the Vigil-side
            # record of what this integration targets.
            IntegrationField("default_interface"),
            # Containment lifetime the MCP surface proposes when a caller omits
            # ttl_seconds. Matches the daemon's own 1h default; the daemon
            # enforces the floor regardless.
            IntegrationField("default_ttl_seconds", value_type="int", default=3600),
        ),
    )
)
