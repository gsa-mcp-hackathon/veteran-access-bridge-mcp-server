import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

path = Path(__file__).parents[1] / "deploy/ibm/evaluation/prepare_answer_candidate.py"
spec = importlib.util.spec_from_file_location("answer_candidate", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def baseline():
    return {
        "name": "vab_latency_eval_agent",
        "tools": [
            "vab-latency-eval-mcp:" + x
            for x in (
                "get_va_patient_health_sandbox_summary",
                "search_call_appointments",
                "search_call_knowledge",
            )
        ],
        "context_variables": ["vab_case_id", "vab_mcp_scope"],
        "plugins": {"agent_pre_invoke": [{"plugin_name": "vab_require_voice_context"}]},
        "instructions": (
            "1. On the first verified voice turn, independently call\n"
            "   get_va_patient_health_sandbox_summary for the current case BEFORE any"
            " other operation. Keep identity and consent controls."
        ),
    }


def test_candidate_preserves_tools_guard_and_original_object():
    original = baseline()
    saved = deepcopy(original)
    result = module.prepare_candidate(original, "Current-turn context only.")
    assert original == saved
    assert result["tools"] == original["tools"]
    assert result["plugins"] == original["plugins"]
    assert "Keep identity and consent controls." in result["instructions"]
    assert "Otherwise independently" in result["instructions"]
    assert "vab_patient_source_verified" in result["context_variables"]


@pytest.mark.parametrize(
    "change",
    [
        {"name": "veteran_access_agent_m64"},
        {"tools": ["book_call_appointment"]},
        {"instructions": "A different unreviewed prompt"},
    ],
)
def test_candidate_refuses_live_or_unreviewed_configuration(change):
    with pytest.raises(ValueError):
        module.prepare_candidate({**baseline(), **change}, "supplement")
