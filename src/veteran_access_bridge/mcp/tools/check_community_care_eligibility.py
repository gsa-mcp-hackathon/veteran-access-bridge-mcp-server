"""Read-only Community Care eligibility *verification status*.

Access-standard exceedance is a review signal, NOT an eligibility decision.
No VA eligibility network authority or clinical authorization is configured.
This tool deliberately returns UNVERIFIED instead of guessing eligibility.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.tools.assess_access_standard import (
    run as assess_access_standard,
)


def run(case_id: str) -> dict[str, Any]:
    """Return a bounded access-standard signal and unverified eligibility status."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("Synthetic case ID is required")
    assessment = assess_access_standard(case_id)
    return {
        "case_id": case_id,
        "synthetic": True,
        "read_only": True,
        "community_care_eligibility_status": "UNVERIFIED",
        "authoritative_eligibility_checked": False,
        "authorization_granted": False,
        "appointment_created": False,
        "review_signal": assessment,
        "next_action": (
            "Obtain verified VA Community Care eligibility and separately "
            "issued referral/HSRM authorization before any EPS booking."
        ),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="check_community_care_eligibility",
        annotations={
            "title": "Check Community Care Eligibility Evidence",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def check_community_care_eligibility_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Provide access-standard context without claiming VA eligibility.

        This synthetic-only status check is not a VA eligibility API call.
        Eligibility remains UNVERIFIED and cannot authorize an appointment.
        """
        return run(case_id)
