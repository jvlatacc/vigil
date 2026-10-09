"""Carbon Black integration descriptor — source of truth for its registry entries."""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

CARBON_BLACK = register_descriptor(
    IntegrationDescriptor(
        id="carbon-black",
        category="EDR/XDR",
        mcp_server_names=("carbon-black",),
        fields=(
            IntegrationField("url"),
            IntegrationField("api_id"),
            IntegrationField("api_key", secret=True),
            IntegrationField("org_key"),
        ),
        # tool.py answers two read tools and one that quarantines a device.
        mutating_tools=("cb_quarantine",),
    )
)
