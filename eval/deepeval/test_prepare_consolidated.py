import copy

import pytest
from prepare_consolidated_agent import prepare


def test_candidate_preserves_voice_model_and_unrelated_config():
    before = {
        "name": "veteran_access_agent_m64",
        "llm": "existing",
        "tools": ["veteran-access-mcp-remote-m64-canary:verify_synthetic_identity"],
        "guidelines": [{"tool": "old:handoff"}],
        "voice_config": {"id": "same"},
        "context_variables": ["existing"],
        "memory_enabled": False,
    }
    original = copy.deepcopy(before)
    after, summary = prepare(before, "revision 5 {vab_case_id} {vab_mcp_scope}", "new:")
    assert before == original
    assert after["voice_config"] == before["voice_config"]
    assert after["llm"] == before["llm"]
    assert after["memory_enabled"] is False
    assert after["context_variables"] == ["existing", "vab_case_id", "vab_mcp_scope"]
    assert after["guidelines"] == []
    assert summary["new_tools"] == 13


def test_unknown_binding_prevents_replacement():
    with pytest.raises(ValueError, match="Unexpected existing tools"):
        prepare(
            {"name": "veteran_access_agent_m64", "tools": ["unrelated:tool"]},
            "revision 5 {vab_case_id} {vab_mcp_scope}",
            "new:",
        )


def test_reviewed_legacy_kb_and_ccg_bindings_are_explicitly_reconciled():
    before = {
        "name": "veteran_access_agent_m64",
        "tools": [
            "veteran-access-mcp-unified-candidate:get_kb_evidence",
            "veteran-access-mcp-m64-ccg-canary:check_community_care_eligibility",
        ],
    }
    after, summary = prepare(before, "revision 5 {vab_case_id} {vab_mcp_scope}", "new:")
    assert "new:check_community_care_eligibility" in after["tools"]
    assert summary["retired_out_of_catalog_bindings"] == [before["tools"][0]]
    before["tools"] = ["veteran-access-mcp-unified-candidate:record_option_selection"]
    with pytest.raises(ValueError, match="Unexpected existing tools"):
        prepare(before, "revision 5 {vab_case_id} {vab_mcp_scope}", "new:")
