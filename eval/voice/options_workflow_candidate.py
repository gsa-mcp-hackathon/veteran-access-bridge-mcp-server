"""Development sequence, not an imported IBM workflow or registered MCP tool.

The runner must supply an executor that invokes the existing MCP boundary with
the active host-issued scope. This module never issues scopes or booking grants.
"""


async def prepare_options(
    execute_scoped, *, case_id, date_from="", date_to="", time_preference="ANY"
):
    if not callable(execute_scoped) or not isinstance(case_id, str) or not case_id:
        raise PermissionError("Active scoped executor and case required")
    patient = await execute_scoped(
        "get_va_patient_health_sandbox_summary", {"case_id": case_id}
    )
    if not isinstance(patient, dict) or (
        patient.get("case_id") != case_id
        or patient.get("source_verified") is not True
        or patient.get("identity_matches") is not True
    ):
        raise PermissionError("Verified patient evidence required before options")
    return await execute_scoped(
        "search_call_appointments",
        {
            "case_id": case_id,
            "date_from": date_from,
            "date_to": date_to,
            "time_preference": time_preference,
        },
    )
