"""Read-only VA sandbox contracts; missing source configuration fails closed.

Facility metadata may use the explicitly enabled VA Facilities adapter.
No facility result establishes patient assignment or booking authority.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from fastmcp import FastMCP


def _unavailable(tool: str, lookup: str) -> dict[str, Any]:
    if not isinstance(lookup, str) or not lookup.strip():
        raise ValueError("Non-empty sandbox lookup identifier required")
    return {
        "tool": tool,
        "lookup": lookup,
        "status": "UNAVAILABLE",
        "source": "none_configured",
        "source_verified": False,
        "synthetic": True,
        "read_only": True,
        "authoritative_va_result": False,
        "community_care_eligibility_status": "UNVERIFIED",
        "authorization_granted": False,
        "booking_created": False,
        "message": (
            "No verified VA sandbox source adapter is configured; "
            "no clinical or scheduling facts inferred."
        ),
    }


# Explicitly invented demo records, never sourced from a VA system.
_DEMO_FACILITY = {
    "facility_id": "DEMO-FACILITY-001",
    "name": "Fictional Demo Medical Center",
    "services": ["PRIMARY_CARE", "SPECIALTY_CARE"],
}
_DEMO_CASE = {
    "case_id": "DEMO-CASE-001",
    "request_kind": "PRIMARY_CARE",
    "lifecycle_state": "REQUESTED",
}


def _lookup(tool: str, lookup: str) -> dict[str, Any]:
    """Return fictional fixtures only with explicit opt-in; otherwise fail closed."""
    unavailable = _unavailable(tool, lookup)
    if (
        tool == "get_va_sandbox_health_facility"
        and os.getenv("VA_FACILITIES_READ_ENABLED", "").lower() == "true"
    ):
        from veteran_access_bridge.adapters.va_facilities import read_health_facility

        try:
            facility = read_health_facility(lookup)
        except (PermissionError, ValueError, RuntimeError):
            return unavailable
        return {
            **unavailable,
            **facility,
            "status": "AVAILABLE",
            "message": "Facility metadata only; no patient assignment or availability.",
        }
    if os.getenv("VAB_VA_SANDBOX_SOURCE_MODE", "unavailable") != "demo_fixture":
        return unavailable

    key = lookup.strip()
    fixture: dict[str, Any] | None = None
    if tool == "get_va_sandbox_health_facility":
        if key == _DEMO_FACILITY["facility_id"]:
            fixture = dict(_DEMO_FACILITY)
    elif tool == "search_va_sandbox_health_facilities":
        if key.casefold() in {"demo", "fictional", "primary care", "specialty care"}:
            fixture = {"facilities": [dict(_DEMO_FACILITY)]}
    elif tool == "get_va_sandbox_health_facility_service":
        if key == "DEMO-SERVICE-001":
            fixture = {
                "facility_service_id": key,
                "facility_id": _DEMO_FACILITY["facility_id"],
                "service": "PRIMARY_CARE",
            }
    elif tool in {
        "get_va_community_care_case_summary",
        "get_va_patient_health_sandbox_summary",
        "get_va_clinical_health_case_summary",
    }:
        if key == _DEMO_CASE["case_id"]:
            fixture = dict(_DEMO_CASE)
            fixture["clinical_data"] = "NOT_PROVIDED"
            fixture["community_care_eligibility_status"] = "UNVERIFIED"
    if fixture is None:
        return unavailable
    return {
        **unavailable,
        **fixture,
        "status": "DEMO_FIXTURE",
        "source": "local_fictional_fixture",
        "source_verified": False,
        "authoritative_va_result": False,
        "authorization_granted": False,
        "booking_created": False,
        "message": "Fictional local fixture; not VA sandbox or patient data.",
    }


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="get_va_sandbox_health_facility",
        annotations={
            "title": "get va sandbox health facility",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_va_sandbox_health_facility_tool(
        facility_id: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Read a VA sandbox facility; never infer patient assignment or slots."""
        return await asyncio.to_thread(
            _lookup, "get_va_sandbox_health_facility", facility_id
        )

    @mcp.tool(
        name="search_va_sandbox_health_facilities",
        annotations={
            "title": "search va sandbox health facilities",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_va_sandbox_health_facilities_tool(
        query: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Return unavailable status until a verified source is configured."""
        return _lookup("search_va_sandbox_health_facilities", query)

    @mcp.tool(
        name="get_va_sandbox_health_facility_service",
        annotations={
            "title": "get va sandbox health facility service",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_va_sandbox_health_facility_service_tool(
        facility_service_id: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Return unavailable status until a verified source is configured."""
        return _lookup("get_va_sandbox_health_facility_service", facility_service_id)

    @mcp.tool(
        name="get_va_community_care_case_summary",
        annotations={
            "title": "get va community care case summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_va_community_care_case_summary_tool(
        case_id: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Return unavailable status until a verified source is configured."""
        return _lookup("get_va_community_care_case_summary", case_id)

    @mcp.tool(
        name="get_va_patient_health_sandbox_summary",
        annotations={
            "title": "get va patient health sandbox summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_va_patient_health_sandbox_summary_tool(
        case_id: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Return unavailable status until a verified source is configured."""
        return _lookup("get_va_patient_health_sandbox_summary", case_id)

    @mcp.tool(
        name="get_va_clinical_health_case_summary",
        annotations={
            "title": "get va clinical health case summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_va_clinical_health_case_summary_tool(
        case_id: Annotated[str, "Synthetic/sandbox lookup key; no PHI."],
    ) -> dict[str, Any]:
        """Return unavailable status until a verified source is configured."""
        return _lookup("get_va_clinical_health_case_summary", case_id)
