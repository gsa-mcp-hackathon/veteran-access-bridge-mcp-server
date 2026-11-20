"""Offline acceptance of fresh exports; never changes IBM or issues authority."""

import argparse
import json
from pathlib import Path

import yaml

CASE_READS = {
    "determine_workflow_state",
    "search_availability",
    "assess_access_standard",
    "check_community_care_eligibility",
    "get_case_lifecycle_state",
    "get_scheduling_encounter",
    "get_va_community_care_case_summary",
    "get_va_patient_health_sandbox_summary",
    "get_va_clinical_health_case_summary",
}
FACILITY_READS = {
    "get_va_sandbox_health_facility",
    "search_va_sandbox_health_facilities",
    "get_va_sandbox_health_facility_service",
}
RESTRICTED = {
    "prepare_scheduling_handoff",
    "get_scheduling_handoff",
    "validate_option_selection",
    "prepare_veteran_confirmation_request",
    "record_option_selection",
    "record_veteran_confirmation",
    "validate_booking_preconditions",
    "record_lifecycle_event",
}
ALLOWED = CASE_READS | FACILITY_READS | {"verify_synthetic_identity"}
CATALOG = ALLOWED | RESTRICTED


def verify(registry, imported, before_agent, candidate, exported, *, prefix, binding):
    """Require exact discovery/schema/binding and prepared-agent agreement.

    registry: fresh MCP list_tools model_dump output; imported: IBM tool export.
    binding: reviewed existing mcp server_url + connections (no secret values).
    A matching candidate is not proof its instructions are semantically safe.
    """
    if (
        not prefix.endswith(":")
        or not binding.get("server_url")
        or not binding.get("connections")
    ):
        raise ValueError("Explicit toolkit prefix and authenticated binding required")
    source = {t["name"]: t for t in registry}
    if len(registry) != 21 or set(source) != CATALOG:
        raise ValueError("Live registry differs from the approved 21 tools")
    selected = [t for t in imported if t["name"].startswith(prefix)]
    catalog = {t["name"][len(prefix) :]: t for t in selected}
    if len(selected) != 21 or set(catalog) != CATALOG:
        raise ValueError("Consolidated catalog is missing, duplicated, or unexpected")
    scoped = CATALOG - FACILITY_READS - {"get_scheduling_handoff"}
    for name, tool in catalog.items():
        schema = tool.get("input_schema")
        if schema != source[name].get("inputSchema"):
            raise ValueError("Imported schema differs from live discovery: " + name)
        if name in scoped:
            props = schema.get("properties", {})
            if (
                props.get("session_scope", {}).get("type") != "string"
                or "case_id" not in props
            ):
                raise ValueError("Trusted case scope schema missing: " + name)
        actual = tool.get("binding", {}).get("mcp", {})
        if any(
            actual.get(key) != binding[key] for key in ("server_url", "connections")
        ):
            raise ValueError("Endpoint or credential connection changed: " + name)
    expected = {prefix + name for name in ALLOWED}
    attached = exported.get("tools", [])
    if len(attached) != 13 or set(attached) != expected:
        raise ValueError("Avery must bind exactly the 13 reviewed tools")
    for key in ("name", "llm"):
        if before_agent.get(key) != exported.get(key):
            raise ValueError("Agent identity or model changed")
    if exported.get("name") != "veteran_access_agent_m64":
        raise ValueError("Wrong agent")
    if not {"vab_case_id", "vab_mcp_scope"} <= set(
        exported.get("context_variables", [])
    ):
        raise ValueError("Trusted application context variables missing")
    if candidate != exported:
        raise ValueError("Applied agent differs from reviewed candidate")
    return {
        "catalog_tools": 21,
        "scoped_catalog_tools": 17,
        "avery_tools": 13,
        "scoped_avery_tools": 10,
        "live_acceptance": "NOT_RUN_BY_THIS_CHECK",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "registry",
        "imported",
        "before-agent",
        "candidate",
        "exported",
        "binding",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()

    def read(path):
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    result = verify(
        read(args.registry),
        read(args.imported),
        read(args.before_agent),
        read(args.candidate),
        read(args.exported),
        prefix=args.prefix,
        binding=read(args.binding),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
