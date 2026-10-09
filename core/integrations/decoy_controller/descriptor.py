"""Decoy-controller integration descriptor — source of truth for its registry entries.

The ``api_token`` is the bearer credential the reference controller
(``services/decoy_controller/``) denies every request without: it resolves
through the encrypted store as ``DECOY_CONTROLLER_API_TOKEN``. ``base_url``
points at the controller's API — e.g. ``http://decoy-controller:8801`` on the
compose profile — and stays a plain (non-secret) field because it names an
endpoint, not a credential.
"""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

DECOY_CONTROLLER = register_descriptor(
    IntegrationDescriptor(
        id="decoy_controller",
        category="Network Security",
        mcp_server_names=("decoy_controller",),
        fields=(
            IntegrationField("base_url"),
            IntegrationField("api_token", secret=True),
        ),
    )
)
