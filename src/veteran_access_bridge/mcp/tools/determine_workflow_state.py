"""MCP wrapper for the deterministic workflow-state gate."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.domain.workflow import determine_workflow_state
from veteran_access_bridge.mcp.cases import load_demo_case


def run(case_id: str) -> dict[str, Any]:
    patient, consult = load_demo_case(case_id)
    state = determine_workflow_state(patient, consult)
    return {
        "case_id": case_id,
        "patient_id": patient.patient_id,
        "consult_id": consult.consult_id,
        "specialty": consult.specialty,
        "workflow_state": state.value,
        "synthetic": True,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="determine_workflow_state",
        annotations={
            "title": "Determine Workflow State",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def determine_workflow_state_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Return the deterministic scheduling workflow state for a synthetic case."""
        return run(case_id)
