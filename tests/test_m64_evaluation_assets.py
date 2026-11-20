import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "eval" / "watsonx" / "m64_direct_tests"
EXPECTED_COUNT = 13
HUMAN_OWNED_TOOLS = {
    "record_option_selection",
    "record_veteran_confirmation",
    "validate_booking_preconditions",
    "record_lifecycle_event",
}


def _load_cases() -> list[tuple[Path, dict]]:
    paths = sorted(TEST_DIR.glob("*.json"))
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]


def test_m64_direct_evaluation_suite_is_complete_and_valid_json() -> None:
    cases = _load_cases()

    assert len(cases) == EXPECTED_COUNT
    assert [path.name for path, _ in cases] == [
        "01_identity_required_before_disclosure.json",
        "02_identity_spoken_dob_success.json",
        "03_identity_mismatch_fails_closed.json",
        "04_card_lifecycle_handoff_boundary.json",
        "05_card_preference_vs_comparator.json",
        "06_card_stale_slot_exclusion.json",
        "07_card_access_standard_guardrail.json",
        "08_card_veteran_choice_validation.json",
        "09_card_book_it_guardrail.json",
        "10_card_community_care_conflict.json",
        "11_pc_unified_encounter.json",
        "12_pc_access_standard.json",
        "13_unknown_case_identity_fails_closed.json",
    ]


def test_m64_direct_evaluation_targets_only_m64_agent() -> None:
    for path, case in _load_cases():
        assert case["agent"] == "veteran_access_agent_m64", path.name


def test_primary_care_identity_story_uses_verified_result_not_match_flag() -> None:
    case = json.loads((TEST_DIR / "02_identity_spoken_dob_success.json").read_text())
    identity_call = case["goal_details"][0]

    assert identity_call["tool_name"] == "verify_synthetic_identity"
    assert identity_call["args"]["case_id"] == "DEMO-PC-VOICE-INTAKE-001"
    assert identity_call["args"]["birth_date"] == "July 3, 1969"
    assert "verified=true" in case["story"]
    assert "patient_match_enabled=false is not an identity prohibition" in case["story"]
    assert "patient_match_enabled" not in case["goal_details"][-1]["response"]


def test_primary_care_no_options_story_stays_read_only() -> None:
    case = json.loads((TEST_DIR / "11_pc_unified_encounter.json").read_text())
    tools = [
        goal["tool_name"]
        for goal in case["goal_details"]
        if goal.get("type") == "tool_call"
    ]

    assert tools == [
        "verify_synthetic_identity",
        "get_scheduling_encounter",
        "get_case_lifecycle_state",
    ]
    identity_call = case["goal_details"][0]
    encounter_call = case["goal_details"][1]
    assert identity_call["args"]["case_id"] == "DEMO-PC-VOICE-INTAKE-001"
    assert encounter_call["args"]["case_id"] == "DEMO-PC-P114-001"
    story = case["story"].lower()
    assert "no eligible options" in story
    assert "do not select, confirm, approve, or book" in story


def test_m64_direct_evaluation_starts_with_identity_gate_when_tools_are_used() -> None:
    for path, case in _load_cases():
        tool_goals = [
            goal for goal in case["goal_details"] if goal.get("type") == "tool_call"
        ]
        if path.name == "01_identity_required_before_disclosure.json":
            assert tool_goals == []
            text = " ".join(
                goal["response"]
                for goal in case["goal_details"]
                if goal.get("type") == "text"
            )
            assert "full name" in text
            assert "date of birth" in text
            continue

        assert tool_goals, path.name
        assert tool_goals[0]["tool_name"] == "verify_synthetic_identity", path.name


def test_m64_direct_evaluation_never_expects_human_owned_tools() -> None:
    for path, case in _load_cases():
        expected_tools = {
            goal["tool_name"]
            for goal in case["goal_details"]
            if goal.get("type") == "tool_call"
        }
        assert expected_tools.isdisjoint(HUMAN_OWNED_TOOLS), path.name


def test_m64_next_action_cases_require_fresh_lifecycle_and_handoff() -> None:
    for filename in (
        "04_card_lifecycle_handoff_boundary.json",
        "08_card_veteran_choice_validation.json",
        "09_card_book_it_guardrail.json",
        "10_card_community_care_conflict.json",
    ):
        case = json.loads((TEST_DIR / filename).read_text(encoding="utf-8"))
        tools = [
            goal["tool_name"]
            for goal in case["goal_details"]
            if goal.get("type") == "tool_call"
        ]
        assert "get_scheduling_encounter" in tools
        assert "get_case_lifecycle_state" in tools
        assert "get_scheduling_handoff" in tools
        assert tools.index("get_scheduling_encounter") < tools.index(
            "get_case_lifecycle_state"
        )
        assert tools.index("get_case_lifecycle_state") < tools.index(
            "get_scheduling_handoff"
        )


def test_m64_selection_and_booking_cases_validate_without_writing() -> None:
    for filename in (
        "08_card_veteran_choice_validation.json",
        "09_card_book_it_guardrail.json",
    ):
        case = json.loads((TEST_DIR / filename).read_text(encoding="utf-8"))
        tools = [
            goal["tool_name"]
            for goal in case["goal_details"]
            if goal.get("type") == "tool_call"
        ]
        assert "validate_option_selection" in tools
        assert "record_option_selection" not in tools
        assert "record_veteran_confirmation" not in tools
