"""Offline acceptance of fresh exports; never changes IBM or issues authority."""

import argparse
import json
import re
import subprocess
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


def unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("Configuration object keys must be strings")
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


class ExportLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return unique_mapping(self.construct_pairs(node, deep=deep))


def load_approved_file(commit, filename):
    """The release owner supplies a reviewed commit independently of both exports."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full reviewed Git commit is required")
    path = f"eval/deepeval/{filename}"
    raw = subprocess.check_output(
        ["git", "show", f"{commit}:{path}"],
        cwd=Path(__file__).resolve().parent,
    )
    return json.loads(raw, object_pairs_hook=unique_mapping)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def metadata(tool):
    """The SDK emits meta=None when the optional MCP field is absent."""
    values = [tool[key] for key in ("meta", "_meta") if key in tool]
    if any(value is not None and not isinstance(value, dict) for value in values):
        raise ValueError("Tool metadata must be an object or null")
    serialized = {canonical(value) for value in values}
    if len(serialized) > 1:
        raise ValueError("Conflicting meta and _meta values")
    return serialized.pop() if serialized else canonical(None)


def scoped_names(policy, definitions):
    if policy.get("version") != "v1" or not isinstance(policy.get("tools"), dict):
        raise ValueError("Missing or unsupported approved scope policy")
    classes = policy["tools"]
    if any(value not in ("case", "no_case") for value in classes.values()) or (
        set(definitions) - classes.keys()
    ):
        raise ValueError("Invalid or missing tool scope classification")
    return {name for name in definitions if classes[name] == "case"}


def verify(
    registry,
    imported,
    before_agent,
    candidate,
    exported,
    *,
    prefix,
    binding,
    approved,
    scope_policy,
):
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
    if prefix != approved["prefix"] or canonical(binding) != canonical(
        approved["binding"]
    ):
        raise ValueError("Toolkit identity or binding differs from approved manifest")
    definitions = approved["tools"]
    source = {t["name"]: t for t in registry}
    if (
        not definitions
        or len(registry) != len(definitions)
        or set(source) != set(definitions)
    ):
        raise ValueError("Live registry differs from the approved manifest")
    selected = [t for t in imported if t["name"].startswith(prefix)]
    catalog = {t["name"][len(prefix) :]: t for t in selected}
    if len(selected) != len(definitions) or set(catalog) != set(definitions):
        raise ValueError("Consolidated catalog is missing, duplicated, or unexpected")
    scoped = scoped_names(scope_policy, definitions)
    for name, tool in catalog.items():
        schema = tool.get("input_schema")
        reference = definitions[name]
        if (
            not isinstance(reference["description"], str)
            or not reference["description"].strip()
        ):
            raise ValueError("Approved description missing: " + name)
        if not isinstance(reference["inputSchema"], dict):
            raise ValueError("Approved input schema missing: " + name)
        approved_meta = metadata(reference)
        for observed, schema_key in (
            (source[name], "inputSchema"),
            (tool, "input_schema"),
        ):
            if observed.get("description") != reference["description"]:
                raise ValueError(
                    "Tool description differs from approved manifest: " + name
                )
            if canonical(observed.get(schema_key)) != canonical(
                reference["inputSchema"]
            ):
                raise ValueError("Tool schema differs from approved manifest: " + name)
            if metadata(observed) != approved_meta:
                raise ValueError(
                    "Tool metadata differs from approved manifest: " + name
                )
            for field in (
                "annotations",
                "securitySchemes",
                "security_schemes",
            ):
                if canonical(observed.get(field)) != canonical(reference.get(field)):
                    raise ValueError(
                        "Tool " + field + " differs from approved manifest: " + name
                    )
        props = schema.get("properties", {})
        scope_fields = ("case_id", "session_scope")
        if name in scoped:
            if schema.get("type") != "object" or not all(
                props.get(field, {}).get("type") == "string" for field in scope_fields
            ):
                raise ValueError("Trusted case scope schema missing: " + name)
        elif any(field in props for field in scope_fields):
            raise ValueError("Schema contradicts no_case scope classification: " + name)
        actual = tool.get("binding", {}).get("mcp", {})
        if canonical(actual) != canonical(binding):
            raise ValueError("Endpoint or credential connection changed: " + name)
    approved_agent_tools = approved["agent_tools"]
    if (
        not approved_agent_tools
        or len(set(approved_agent_tools)) != len(approved_agent_tools)
        or not set(approved_agent_tools) <= set(definitions)
    ):
        raise ValueError("Invalid approved agent tool set")
    expected = {prefix + name for name in approved_agent_tools}
    attached = exported.get("tools", [])
    if len(attached) != len(expected) or set(attached) != expected:
        raise ValueError("Avery must bind exactly the reviewed tools")
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
        "catalog_tools": len(catalog),
        "scoped_catalog_tools": len(scoped),
        "avery_tools": len(attached),
        "scoped_avery_tools": len(scoped.intersection(approved_agent_tools)),
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
    parser.add_argument(
        "--approved-commit",
        required=True,
        help="Reviewed commit containing both the catalog manifest and scope policy",
    )
    args = parser.parse_args()

    def read(path):
        return yaml.load(path.read_text(encoding="utf-8"), Loader=ExportLoader)

    result = verify(
        read(args.registry),
        read(args.imported),
        read(args.before_agent),
        read(args.candidate),
        read(args.exported),
        prefix=args.prefix,
        binding=read(args.binding),
        approved=load_approved_file(args.approved_commit, "approved-catalog.json"),
        scope_policy=load_approved_file(
            args.approved_commit, "catalog-scope-policy.json"
        ),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
