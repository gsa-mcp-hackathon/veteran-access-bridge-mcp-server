"""Evaluation-only watsonx Orchestrate tool definitions for M6.3.

These wrappers expose the same four governed tool names used by the live remote MCP
toolkit, while delegating execution to Veteran Access Bridge's existing deterministic
backend functions. They exist only so the watsonx evaluation generator can inspect and
exercise concrete Python tool definitions. They do not replace the MCP server.
"""

from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool

from veteran_access_bridge.mcp.tools.assess_access_standard import run as run_access
from veteran_access_bridge.mcp.tools.determine_workflow_state import run as run_state
from veteran_access_bridge.mcp.tools.get_scheduling_encounter import run as run_encounter
from veteran_access_bridge.mcp.tools.search_availability import run as run_search


@tool(permission=ToolPermission.READ_ONLY)
def get_scheduling_encounter(case_id: str) -> dict:
    """Return the governed synthetic M6.3 Scheduling Encounter.

    Args:
        case_id (str): Approved synthetic scheduling case identifier.
    Returns:
        dict: Unified read-only scheduling encounter evidence.
    """
    return run_encounter(case_id)


@tool(permission=ToolPermission.READ_ONLY)
def assess_access_standard(case_id: str) -> dict:
    """Assess the synthetic VA wait-time access standard without granting authorization.

    Args:
        case_id (str): Approved synthetic scheduling case identifier.
    Returns:
        dict: Deterministic access-standard evidence and guardrail flags.
    """
    return run_access(case_id)


@tool(permission=ToolPermission.READ_ONLY)
def determine_workflow_state(case_id: str) -> dict:
    """Return the deterministic workflow state for a synthetic scheduling case.

    Args:
        case_id (str): Approved synthetic scheduling case identifier.
    Returns:
        dict: Current deterministic workflow-state evidence.
    """
    return run_state(case_id)


@tool(permission=ToolPermission.READ_ONLY)
def search_availability(case_id: str) -> dict:
    """Return the legacy raw synthetic multi-source availability view.

    Args:
        case_id (str): Approved synthetic scheduling case identifier.
    Returns:
        dict: Synthetic cross-source availability evidence.
    """
    return run_search(case_id)
