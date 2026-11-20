from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

M63_AGENT_PATH = ROOT / "agents" / "veteran-access-agent.yaml"
M64_AGENT_PATH = ROOT / "agents" / "veteran-access-agent-m64.yaml"

M63_CONFIGURE_PATH = ROOT / "deploy" / "ibm" / "orchestrate" / "configure-m63.ps1"
M64_CONFIGURE_PATH = ROOT / "deploy" / "ibm" / "orchestrate" / "configure-m64.ps1"

M63_TOOLS = (
    "determine_workflow_state",
    "get_scheduling_encounter",
    "search_availability",
    "assess_access_standard",
)

M64_ADDITIONAL_TOOLS = (
    "verify_synthetic_identity",
    "get_case_lifecycle_state",
    "prepare_scheduling_handoff",
    "get_scheduling_handoff",
    "validate_option_selection",
    "prepare_veteran_confirmation_request",
)

HUMAN_OWNED_TOOLS = (
    "record_option_selection",
    "record_veteran_confirmation",
    "validate_booking_preconditions",
    "record_lifecycle_event",
)


def _agent_tool_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("\ntools:\n", 1)[1].split("\nrestrictions:", 1)[0]


def test_m63_agent_remains_validated_four_tool_baseline() -> None:
    tool_block = _agent_tool_block(M63_AGENT_PATH)

    for tool in M63_TOOLS:
        assert f"veteran-access-mcp-remote-m63:{tool}" in tool_block

    for tool in M64_ADDITIONAL_TOOLS + HUMAN_OWNED_TOOLS:
        assert f"veteran-access-mcp-remote-m63:{tool}" not in tool_block


def test_m63_registration_does_not_absorb_m64_tools() -> None:
    script = M63_CONFIGURE_PATH.read_text(encoding="utf-8")

    for tool in M63_TOOLS:
        assert tool in script

    for tool in M64_ADDITIONAL_TOOLS:
        assert tool not in script


def test_m64_candidate_has_safe_autonomy_tools_only() -> None:
    tool_block = _agent_tool_block(M64_AGENT_PATH)

    for tool in M63_TOOLS + M64_ADDITIONAL_TOOLS:
        assert f"veteran-access-mcp-remote-m64:{tool}" in tool_block

    for tool in HUMAN_OWNED_TOOLS:
        assert f"veteran-access-mcp-remote-m64:{tool}" not in tool_block


def test_m64_registration_isolated_from_m63() -> None:
    script = M64_CONFIGURE_PATH.read_text(encoding="utf-8")

    assert "veteran-access-mcp-remote-m64" in script
    assert "veteran_access_agent_m64" in script

    for tool in M63_TOOLS + M64_ADDITIONAL_TOOLS:
        assert tool in script

    for tool in HUMAN_OWNED_TOOLS:
        assert tool not in script


def test_m64_agent_instructions_preserve_human_authority() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Never impersonate a Scheduler or Veteran." in normalized
    assert "Preparing the request is not Veteran consent." in normalized
    assert "Human-owned state changes remain outside this agent's toolset." in normalized


def test_m64_next_action_requires_fresh_lifecycle_and_handoff_evidence() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert (
        "you MUST call get_case_lifecycle_state immediately after "
        "get_scheduling_encounter before deciding what happens next."
        in normalized
    )
    assert (
        "If the fresh Scheduling Encounter contains decision.handoff_id, "
        "call get_scheduling_handoff with that ID before describing the handoff"
        in normalized
    )
    assert (
        "Do not call prepare_scheduling_handoff when an existing handoff_id "
        "is already present."
        in normalized
    )


def test_m64_distinguishes_observed_evidence_from_actions_performed() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Distinguish evidence observed this turn from actions performed this turn." in normalized
    assert "do not imply Avery performed those computations or mutations in this turn." in normalized


def test_m64_separates_option_wait_from_access_standard_wait() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Keep option wait metrics separate from access-standard wait." in normalized
    assert (
        "Never substitute option wait_days for earliest_eligible_va_wait_days."
        in normalized
    )


def test_m64_next_action_gate_forbids_answer_after_encounter_only() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "M6.4 mandatory next-action gate:" in normalized
    assert "get_scheduling_encounter(case_id)" in normalized
    assert "get_case_lifecycle_state(case_id)" in normalized
    assert "Do not produce the final next-action answer after get_scheduling_encounter alone." in normalized
    assert "The lifecycle result is required evidence" in normalized
    assert "fresh lifecycle evidence is unavailable and stop." in normalized


def test_m64_selection_role_and_community_care_conflict_rules() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert (
        "The Veteran owns the preference or choice; the Scheduler/MSA owns recording "
        "that selection into governed lifecycle state."
        in normalized
    )
    assert "Reconcile Community Care evidence conservatively." in normalized
    assert "treat authorization as unresolved" in normalized


def test_m64_validation_does_not_imply_persistence() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "A successful validation does NOT persist the Veteran's choice." in normalized
    assert "never say it was \"captured\", \"recorded\", \"on the record\"" in normalized
    assert "Treat validate_option_selection as read-only evidence." in normalized


def test_m64_uses_option_level_verification_result() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Use the validation result's requires_verification field for the selected option." in normalized
    assert "Do not infer an option-level verification requirement from the handoff-level requires_verification flag" in normalized
    assert "the deterministic SYSTEM routing still must advance the lifecycle to VERIFIED_BOOKABLE" in normalized
    assert "Only after the lifecycle actually reaches VERIFIED_BOOKABLE" in normalized


def test_m64_identity_gate_precedes_all_scheduling_tools() -> None:
    text = M64_AGENT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "M6.4 mandatory identity gate:" in normalized
    assert "Identity verification is the first governed step" in normalized
    assert "ask for the Veteran's full name and date of birth and STOP." in normalized
    assert "call verify_synthetic_identity" in normalized
    assert "Continue to any scheduling tool only when verify_synthetic_identity returns verified=true." in normalized
    assert "A case ID supplied in application context or typed by a user is not identity verification." in normalized


def test_m64_identity_gate_tool_is_attached_but_not_m63() -> None:
    m64_tools = _agent_tool_block(M64_AGENT_PATH)
    m63_tools = _agent_tool_block(M63_AGENT_PATH)

    assert "veteran-access-mcp-remote-m64:verify_synthetic_identity" in m64_tools
    assert "verify_synthetic_identity" not in m63_tools
