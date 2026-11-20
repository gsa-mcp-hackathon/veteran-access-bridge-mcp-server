import copy

import pytest
from verify_consolidated_configuration import ALLOWED, CATALOG, FACILITY_READS, verify


def fixture():
    prefix = "consolidated:"
    binding = {
        "server_url": "https://example.test/mcp/",
        "connections": {"existing": "same"},
    }
    registry = []
    for name in sorted(CATALOG):
        scoped = name not in FACILITY_READS | {"get_scheduling_handoff"}
        props = (
            {"case_id": {"type": "string"}, "session_scope": {"type": "string"}}
            if scoped
            else {}
        )
        registry.append(
            {"name": name, "inputSchema": {"type": "object", "properties": props}}
        )
    imported = [
        {
            "name": prefix + t["name"],
            "input_schema": copy.deepcopy(t["inputSchema"]),
            "binding": {"mcp": copy.deepcopy(binding)},
        }
        for t in registry
    ]
    agent = {
        "name": "veteran_access_agent_m64",
        "llm": "existing-model",
        "tools": sorted(prefix + n for n in ALLOWED),
        "context_variables": ["vab_case_id", "vab_mcp_scope"],
        "instructions": "reviewed",
    }
    return [
        registry,
        imported,
        copy.deepcopy(agent),
        copy.deepcopy(agent),
        copy.deepcopy(agent),
    ], {"prefix": prefix, "binding": binding}


def test_acceptance_is_configuration_only():
    args, kw = fixture()
    assert verify(*args, **kw) == {
        "catalog_tools": 21,
        "scoped_catalog_tools": 17,
        "avery_tools": 13,
        "scoped_avery_tools": 10,
        "live_acceptance": "NOT_RUN_BY_THIS_CHECK",
    }


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "duplicate",
        "schema",
        "connection",
        "restricted",
        "alias",
        "model",
        "context",
        "instruction",
    ],
)
def test_configuration_drift_is_rejected(attack):
    args, kw = fixture()
    registry, imported, before, candidate, exported = args
    if attack == "missing":
        registry.pop()
    elif attack == "duplicate":
        imported.append(copy.deepcopy(imported[0]))
    elif attack == "schema":
        imported[0]["input_schema"]["properties"].pop("session_scope")
    elif attack == "connection":
        imported[0]["binding"]["mcp"]["connections"] = {}
    elif attack == "restricted":
        exported["tools"][0] = kw["prefix"] + "record_veteran_confirmation"
    elif attack == "alias":
        exported["tools"][0] = "old:" + exported["tools"][0].split(":")[1]
    elif attack == "model":
        exported["llm"] = "other"
    elif attack == "context":
        exported["context_variables"].remove("vab_mcp_scope")
    else:
        exported["instructions"] = "unreviewed"
    with pytest.raises(ValueError):
        verify(*args, **kw)
