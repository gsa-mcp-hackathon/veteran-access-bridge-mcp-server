"""MCP wrapper for deterministic VA access-standard assessment."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.cases import (
    demo_as_of,
    load_demo_access_standard_context,
    load_demo_case,
)
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.services.access_standard import assess_access_standard


def run(case_id: str) -> dict[str, Any]:
    patient, consult = load_demo_case(case_id)
    care_category, patient_indicated_date = load_demo_access_standard_context(case_id)

    result = assess_access_standard(
        case_id=case_id,
        patient=patient,
        consult=consult,
        care_category=care_category,
        patient_indicated_date=patient_indicated_date,
        as_of=demo_as_of(),
    )

    payload = to_jsonable(result)
    payload["patient_indicated_date"] = result.patient_indicated_date.isoformat()
    payload["policy_basis"] = "VA_COMMUNITY_CARE_WAIT_TIME_ACCESS_STANDARD"
    payload["signal_only"] = True
    payload["authorization_granted"] = False
    payload["eps_invoked"] = False
    payload["booking_created"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="assess_access_standard",
        annotations={
            "title": "Assess VA Access Standard",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def assess_access_standard_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Assess internal VA wait time from canonical PID.

        This tool never grants Community Care authorization.
        """
        return run(case_id)
