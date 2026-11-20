"""Prepare only the isolated read-only agent candidate; no network mutations."""

from copy import deepcopy


def prepare_candidate(baseline, supplement):
    if baseline.get("name") != "vab_latency_eval_agent":
        raise ValueError("Only the isolated evaluation agent is allowed")
    expected = {
        "vab-latency-eval-mcp:get_va_patient_health_sandbox_summary",
        "vab-latency-eval-mcp:search_call_appointments",
        "vab-latency-eval-mcp:search_call_knowledge",
    }
    if set(baseline.get("tools", [])) != expected:
        raise ValueError("Expected the three isolated read tools")
    old = (
        "1. On the first verified voice turn, independently call\n"
        "   get_va_patient_health_sandbox_summary for the current case BEFORE any"
    )
    if baseline["instructions"].count(old) != 1:
        raise ValueError("Expected the reviewed baseline instruction exactly once")
    candidate = deepcopy(baseline)
    candidate["context_variables"] = list(
        dict.fromkeys(
            baseline["context_variables"]
            + ["vab_patient_source_verified", "vab_demo_facility"]
        )
    )
    candidate["instructions"] = (
        baseline["instructions"].replace(
            old,
            "1. Check the application-supplied patient-source value. "
            "If it is exactly true,\n"
            "   the prerequisite is complete: SKIP "
            "get_va_patient_health_sandbox_summary and\n"
            "   use the tool needed for the current request directly. "
            "Otherwise independently\n"
            "   call get_va_patient_health_sandbox_summary "
            "for the current case BEFORE any",
            1,
        )
        + "\n\n"
        + supplement
    )
    return candidate
