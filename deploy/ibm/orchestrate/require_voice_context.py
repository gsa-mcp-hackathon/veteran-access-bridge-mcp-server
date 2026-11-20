"""Draft pre-invoke gate; does not authenticate or issue MCP capabilities.

Only platform context is inspected. Caller messages never establish authority.
The MCP server still validates the live, case-bound capability on every call.
"""

import re

from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.agent_builder.tools.types import (
    AgentPreInvokePayload,
    AgentPreInvokeResult,
    PluginContext,
    PythonToolKind,
)


def has_application_context(state):
    if not isinstance(state, dict):
        return False
    context = state.get("context")
    if not isinstance(context, dict):
        return False
    case = context.get("vab_case_id")
    scope = context.get("vab_mcp_scope")
    return (
        isinstance(case, str)
        and 0 < len(case) <= 128
        and (
            case.startswith(("DEMO-", "VAB-DEMO-"))
            or re.fullmatch(
                r"VAB-CALL-[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                case,
            )
            is not None
        )
        and isinstance(scope, str)
        and re.fullmatch(r"vab_scope_[A-Za-z0-9_-]{43}", scope) is not None
    )


@tool(
    description="Require application context before Avery processes a turn.",
    kind=PythonToolKind.AGENTPREINVOKE,
)
def vab_require_voice_context(
    plugin_context: PluginContext,
    agent_pre_invoke_payload: AgentPreInvokePayload,
) -> AgentPreInvokeResult:
    # Recheck every turn, including SKIP_RBAC: turn capabilities are short-lived.
    allowed = has_application_context(plugin_context.state)
    if allowed:
        return AgentPreInvokeResult(
            continue_processing=True, modified_payload=agent_pre_invoke_payload
        )
    return AgentPreInvokeResult(
        continue_processing=False,
        violation={
            "reason": "Verified call session required",
            "description": "A verified call session is required. Contact your facility's scheduling team for help.",
            "code": "VAB_APPLICATION_CONTEXT_REQUIRED",
            "details": {},
        },
    )
