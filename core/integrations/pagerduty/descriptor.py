"""Pagerduty integration descriptor — source of truth for its registry entries."""

from core.integrations._base.descriptor import (
    IntegrationDescriptor,
    IntegrationField,
    register_descriptor,
)

PAGERDUTY = register_descriptor(
    IntegrationDescriptor(
        id="pagerduty",
        category="Communications",
        mcp_server_names=("pagerduty",),
        fields=(
            IntegrationField("api_token", secret=True),
            IntegrationField("integration_key", secret=True),
            IntegrationField("default_urgency"),
        ),
        # The full write half of pagerduty-mcp -- 22 tools, exposed only when
        # the server is started with --enable-write-tools (the 50 read-only
        # ones always ship). None ends in a verb the fail-closed pattern
        # reads, so this declaration is what holds them behind the approval
        # gate when a deployment opts in.
        mutating_tools=(
            "create_alert_grouping_setting",
            "update_alert_grouping_setting",
            "delete_alert_grouping_setting",
            "create_incident",
            "manage_incidents",
            "add_responders",
            "add_note_to_incident",
            "start_incident_workflow",
            "create_service",
            "update_service",
            "create_team",
            "update_team",
            "delete_team",
            "add_team_member",
            "remove_team_member",
            "create_schedule",
            "create_schedule_override",
            "update_schedule",
            "update_event_orchestration_router",
            "append_event_orchestration_router_rule",
            "create_status_page_post",
            "create_status_page_post_update",
        ),
    )
)
