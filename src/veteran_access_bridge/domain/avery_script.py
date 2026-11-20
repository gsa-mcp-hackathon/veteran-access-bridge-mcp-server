"""Canonical Avery script content for live call conversations."""

from __future__ import annotations

AVERY_OPENING_GREETING = (
    "Thank you for calling Department of Veterans Affairs, my name is Avery. "
    "How can I help you?"
)

AVERY_PRIMARY_CARE_VERIFICATION_PROMPT = (
    "Yes, I can assist you with scheduling an appointment. "
    "For verification purposes, can I have your last name, last4, "
    "and date of birth?"
)

_VERIFICATION_FIELD_LABELS: dict[str, str] = {
    "last_name": "last name",
    "last4": "last4",
    "date_of_birth": "date of birth",
}


def build_agent_opening_instruction() -> str:
    """Return the internal instruction used for Avery's first live-call turn."""

    return (
        "[APPLICATION EVENT - INTERNAL]\n"
        "A Primary Care phone call has connected.\n"
        f'Use this opening exactly: "{AVERY_OPENING_GREETING}"\n'
        "If the Veteran asks to schedule a Primary Care appointment, use this "
        f'verification prompt exactly: "{AVERY_PRIMARY_CARE_VERIFICATION_PROMPT}"\n'
        "Use that opening exactly once when the call starts.\n"
        "Do not restart the call or repeat the opening greeting in later turns.\n"
        "Ask for all verification fields in one prompt.\n"
        "If the Veteran provides partial verification details, ask only for the "
        "missing fields.\n"
        "Keep most responses to 1-3 sentences unless explaining options or "
        "confirming details.\n"
        "Use calm, natural conversational pacing and brief pauses between turns.\n"
        "Wait for the Veteran to finish speaking before responding.\n"
        "Continue the conversation naturally until the call is complete.\n"
        "You may offer to end the call after resolution, but do not end it until "
        "the Veteran confirms.\n"
        "Do not ask for any internal case, encounter, patient, run, or "
        "correlation IDs.\n"
        "[END APPLICATION EVENT]"
    )


def build_unselected_incoming_call_instruction() -> str:
    """Never preselect a caller in a synthetic incoming voice session."""
    return (
        "[APPLICATION EVENT - INTERNAL]\n"
        "An incoming synthetic call has started. This event describes the "
        "opening only; current identity and case scope come exclusively from "
        "registered application context variables on each turn.\n"
        f'Open exactly once: "{AVERY_OPENING_GREETING}"\n'
        "If they request scheduling, ask for their FULL NAME and DATE OF BIRTH. "
        "Follow the agent's identity policy and current application context. "
        "Do not repeat verification when that context says it is complete.\n"
        "If verified=false, do not disclose or guess any patient details or "
        "move into scheduling; ask for clarification or recommend human review.\n"
        "If verified=true, use only the returned matched_case_id for subsequent "
        "case-scoped scheduling MCP tool calls. This is local synthetic fixture "
        "verification only, not VA production identity proof. The returned "
        "patient_match_enabled flag is a fixture property, not authentication.\n"
        "Do not fabricate a tool result or claim a completed booking. "
        "Do not ask the caller for case IDs, correlation IDs or tokens.\n"
        "Wait for a complete Veteran turn before responding. Speak naturally, "
        "in concise responses.\n"
        "[END APPLICATION EVENT]"
    )


def format_missing_verification_prompt(missing_fields: list[str]) -> str:
    """Build a deterministic reprompt for missing verification fields only."""

    normalized = [
        _VERIFICATION_FIELD_LABELS[field]
        for field in missing_fields
        if field in _VERIFICATION_FIELD_LABELS
    ]
    if not normalized:
        return AVERY_PRIMARY_CARE_VERIFICATION_PROMPT
    if len(normalized) == 1:
        needed = normalized[0]
    elif len(normalized) == 2:
        needed = f"{normalized[0]} and {normalized[1]}"
    else:
        needed = ", ".join(normalized[:-1]) + f", and {normalized[-1]}"
    return "Thank you. For verification, I still need your " + needed + "."
