"""Atomic Red Team integration descriptor — source of truth for its registry entries."""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

ATOMIC_RED_TEAM = register_descriptor(
    IntegrationDescriptor(
        id="atomic-red-team",
        category="Forensics & Analysis",
        mcp_server_names=("atomic-red-team",),
        fields=(
            IntegrationField("runner_path"),
            IntegrationField("atomics_path"),
        ),
        # Runs ATT&CK techniques against a target. The name rides the
        # fail-closed pattern too (_execute); the declaration says so at the
        # vendor's source of truth rather than leaving it to the name.
        mutating_tools=("atomic_red_team_execute",),
    )
)

# Engine tool id from tool.py. MCPRegistry.get_all_tools flattens to
# {server}_{tool}, so a connected server declares the second spelling.
EXECUTE_TOOL = "atomic_red_team_execute"
MCP_EXECUTE_TOOL = f"{ATOMIC_RED_TEAM.mcp_server_names[0]}_{EXECUTE_TOOL}"
EXECUTE_IDS = frozenset({EXECUTE_TOOL, MCP_EXECUTE_TOOL})
