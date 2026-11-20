"""MCP tools — one tool per file."""

from __future__ import annotations

from veteran_access_bridge.mcp.tools import (
    assess_access_standard,
    check_community_care_eligibility,
    crm,
    determine_workflow_state,
    get_case_lifecycle_state,
    get_scheduling_encounter,
    get_scheduling_handoff,
    prepare_scheduling_handoff,
    prepare_veteran_confirmation_request,
    record_lifecycle_event,
    record_option_selection,
    record_veteran_confirmation,
    search_availability,
    va_sandbox_readonly,
    validate_booking_preconditions,
    validate_option_selection,
    verify_synthetic_identity,
)


def register_tools(mcp) -> None:
    from veteran_access_bridge.mcp.session_scope import ScopedRegistration

    mcp = ScopedRegistration(mcp)
    verify_synthetic_identity.register(mcp)
    determine_workflow_state.register(mcp)
    search_availability.register(mcp)
    assess_access_standard.register(mcp)
    check_community_care_eligibility.register(mcp)
    get_case_lifecycle_state.register(mcp)
    get_scheduling_encounter.register(mcp)
    prepare_scheduling_handoff.register(mcp)
    get_scheduling_handoff.register(mcp)
    validate_option_selection.register(mcp)
    record_option_selection.register(mcp)
    prepare_veteran_confirmation_request.register(mcp)
    record_veteran_confirmation.register(mcp)
    validate_booking_preconditions.register(mcp)
    record_lifecycle_event.register(mcp)
    va_sandbox_readonly.register(mcp)
    import os

    if os.getenv("VAB_ENABLE_CRM") == "true":
        crm.register(mcp)
    if os.getenv("VAB_ENABLE_AGENT_SCHEDULING") == "true":
        from veteran_access_bridge.mcp.tools import voice_workflow

        voice_workflow.register(mcp)


__all__ = ["register_tools"]
