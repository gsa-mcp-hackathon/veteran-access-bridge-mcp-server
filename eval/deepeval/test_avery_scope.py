import pytest
from prepare_avery_scope import prepare


def agent():
    return {
        "name": "veteran_access_agent_m64",
        "instructions": "existing",
        "tools": ["veteran-access-mcp-remote-m64-canary:verify_synthetic_identity"],
        "llm": "preserved",
        "skills": ["preserved"],
        "guidelines": [
            {"tool": "veteran-access-mcp-unified-candidate:verify_synthetic_identity"}
        ],
        "context_variables": [],
    }


def test_repair_preserves_authority_and_source():
    before = agent()
    after, changes = prepare(before, "scope rules")
    assert after["tools"] == before["tools"]
    assert after["llm"] == before["llm"]
    assert after["skills"] == before["skills"]
    assert before["context_variables"] == []
    assert after["context_variables"] == ["vab_case_id"]
    assert changes[0]["to"] in before["tools"]
    assert before["guidelines"][0]["tool"].startswith("veteran-access-mcp-unified")


def test_repair_cannot_add_unassigned_tool():
    before = agent()
    before["guidelines"][0]["tool"] = (
        "veteran-access-mcp-unified-candidate:commit_booking"
    )
    with pytest.raises(ValueError, match="Cannot repair"):
        prepare(before, "scope rules")
