import copy

import pytest
from verify_scope_configuration import PREFIX, verify


def fixture():
    before = [
        {
            "name": PREFIX + name,
            "input_schema": {"properties": {"case_id": {"type": "string"}}},
            "binding": {
                "mcp": {
                    "server_url": "https://example.test/mcp/",
                    "connections": {"existing": "same-id"},
                }
            },
        }
        for name in ["verify_synthetic_identity"] + [f"read_{i}" for i in range(8)]
    ]
    before.append(
        {
            "name": PREFIX + "get_scheduling_handoff",
            "input_schema": {"properties": {"handoff_id": {"type": "string"}}},
        }
    )
    after = copy.deepcopy(before)
    for tool in after[:-1]:
        tool["input_schema"]["properties"]["session_scope"] = {"type": "string"}
    agent = {
        "name": "veteran_access_agent_m64",
        "llm": "existing-model",
        "tools": [t["name"] for t in before],
        "instructions": "candidate",
        "context_variables": ["vab_case_id", "vab_mcp_scope"],
    }
    return before, after, agent, copy.deepcopy(agent)


def test_verified_configuration_is_not_live_acceptance():
    result = verify(*fixture())
    assert result["case_tools_with_scope"] == 9
    assert result["live_browser_acceptance"] == "NOT_RUN_BY_THIS_CHECK"


@pytest.mark.parametrize("change", ["scope", "tools", "model", "connection"])
def test_stale_or_changed_configuration_fails(change):
    before, after, candidate, exported = fixture()
    if change == "scope":
        del after[0]["input_schema"]["properties"]["session_scope"]
    elif change == "tools":
        after.pop()
    elif change == "model":
        exported["llm"] = "different"
    else:
        after[0]["binding"]["mcp"]["connections"] = {"new": "other"}
    with pytest.raises(ValueError):
        verify(before, after, candidate, exported)
