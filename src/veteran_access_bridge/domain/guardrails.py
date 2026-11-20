"""Human-in-the-loop guardrail contract for the synthetic Primary Care MVP.

Issue #76.

Prototype behavior boundaries only. This module does not define clinical
protocols, diagnose conditions, or claim production VHA policy.

Guardrails are orthogonal to scheduling lifecycle state. They control whether
the automated scheduling flow may continue and when MSA review is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class GuardrailTrigger(StrEnum):
    CLINICAL_CONCERN = "clinical_concern"
    UNRESOLVED_READINESS = "unresolved_readiness"
    CONFLICTING_GOVERNED_EVIDENCE = "conflicting_governed_evidence"
    UNKNOWN_SLOT_ELIGIBILITY = "unknown_slot_eligibility"
    VETERAN_REQUESTS_HUMAN = "veteran_requests_human"
    UNSUPPORTED_SCHEDULING_INTENT = "unsupported_scheduling_intent"
    ACCESSIBILITY_OR_LANGUAGE_NEED = "accessibility_or_language_need"
    VERIFICATION_FAILURE = "verification_failure"
    COMMUNITY_CARE_BRANCH = "community_care_branch"
    ACTION_OUTSIDE_AUTHORITY = "action_outside_authority"
    LOW_CONFIDENCE_CONVERSATION_FIELD = "low_confidence_conversation_field"


class GuardrailSeverity(IntEnum):
    ADVISORY = 10
    HIGH = 20
    CRITICAL = 30


class HandoffRequirement(StrEnum):
    NONE = "none"
    ADVISORY = "advisory"
    MANDATORY = "mandatory"


class HumanControlMode(StrEnum):
    AGENT_HANDLING = "AGENT_HANDLING"
    MSA_MONITORING = "MSA_MONITORING"
    ATTENTION_RECOMMENDED = "ATTENTION_RECOMMENDED"
    WARM_TRANSFER_REQUIRED = "WARM_TRANSFER_REQUIRED"
    MSA_JOINED = "MSA_JOINED"


@dataclass(frozen=True)
class GuardrailRule:
    trigger: GuardrailTrigger
    severity: GuardrailSeverity
    handoff: HandoffRequirement
    detection_source: str
    agent_may_say: str
    agent_may_continue: tuple[str, ...]
    must_stop: tuple[str, ...]
    msa_action: str
    audit_event: str
    fail_closed_behavior: str


@dataclass(frozen=True)
class GuardrailAssessment:
    triggers: tuple[GuardrailTrigger, ...]
    highest_severity: GuardrailSeverity
    handoff: HandoffRequirement
    human_control_mode: HumanControlMode
    may_continue_conversation: bool
    may_continue_scheduling_progression: bool
    must_stop_consequential_actions: bool
    msa_action: str
    audit_event: str
    handoff_payload: dict[str, object]


_RULES: dict[GuardrailTrigger, GuardrailRule] = {
    GuardrailTrigger.CLINICAL_CONCERN: GuardrailRule(
        trigger=GuardrailTrigger.CLINICAL_CONCERN,
        severity=GuardrailSeverity.CRITICAL,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="conversation safety signal",
        agent_may_say="Acknowledge that staff attention is required and pause automated scheduling progression.",
        agent_may_continue=("preserve already-collected scheduling context",),
        must_stop=("slot recommendation", "verification", "approval progression", "simulated booking"),
        msa_action="Join or accept the handoff and follow the approved organizational workflow.",
        audit_event="human_attention_required",
        fail_closed_behavior="Pause automated scheduling progression and require staff review.",
    ),
    GuardrailTrigger.UNRESOLVED_READINESS: GuardrailRule(
        trigger=GuardrailTrigger.UNRESOLVED_READINESS,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="governed encounter/readiness service",
        agent_may_say="Explain that required governed information is unresolved.",
        agent_may_continue=("collect non-consequential preferences", "preserve context"),
        must_stop=("eligibility progression", "verification", "simulated booking"),
        msa_action="Review governed readiness evidence and resolve or route the case.",
        audit_event="human_attention_required",
        fail_closed_behavior="Do not infer readiness; remain blocked until resolved.",
    ),
    GuardrailTrigger.CONFLICTING_GOVERNED_EVIDENCE: GuardrailRule(
        trigger=GuardrailTrigger.CONFLICTING_GOVERNED_EVIDENCE,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="governed evidence comparison",
        agent_may_say="Explain that scheduling records conflict and staff review is required.",
        agent_may_continue=("preserve context",),
        must_stop=("choosing a source winner", "eligibility progression", "booking"),
        msa_action="Review the conflicting governed sources through the approved workflow.",
        audit_event="evidence_conflict",
        fail_closed_behavior="Do not reconcile governed evidence automatically.",
    ),
    GuardrailTrigger.UNKNOWN_SLOT_ELIGIBILITY: GuardrailRule(
        trigger=GuardrailTrigger.UNKNOWN_SLOT_ELIGIBILITY,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="deterministic eligibility service",
        agent_may_say="Explain that the slot cannot yet be confirmed as eligible.",
        agent_may_continue=("present already-governed alternatives", "preserve preferences"),
        must_stop=("presenting unknown slot as eligible", "verification of unknown option", "booking"),
        msa_action="Review eligibility evidence or choose an already-governed alternative.",
        audit_event="human_attention_required",
        fail_closed_behavior="Unknown eligibility is not treated as eligible.",
    ),
    GuardrailTrigger.VETERAN_REQUESTS_HUMAN: GuardrailRule(
        trigger=GuardrailTrigger.VETERAN_REQUESTS_HUMAN,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="conversation",
        agent_may_say="Confirm that an MSA is being brought into the interaction.",
        agent_may_continue=("summarize collected context", "maintain connection"),
        must_stop=("automated scheduling progression after handoff request",),
        msa_action="Accept warm transfer with collected context so information is not repeated.",
        audit_event="transfer_requested",
        fail_closed_behavior="Hold consequential progression until the MSA joins or disposes the request.",
    ),
    GuardrailTrigger.UNSUPPORTED_SCHEDULING_INTENT: GuardrailRule(
        trigger=GuardrailTrigger.UNSUPPORTED_SCHEDULING_INTENT,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="intent classification / workflow boundary",
        agent_may_say="Explain that the request is outside the modeled Primary Care workflow.",
        agent_may_continue=("capture a concise handoff reason", "preserve context"),
        must_stop=("forcing request into Primary Care flow", "booking"),
        msa_action="Route the request to an appropriate supported workflow.",
        audit_event="human_attention_required",
        fail_closed_behavior="Do not coerce unsupported intent into a supported path.",
    ),
    GuardrailTrigger.ACCESSIBILITY_OR_LANGUAGE_NEED: GuardrailRule(
        trigger=GuardrailTrigger.ACCESSIBILITY_OR_LANGUAGE_NEED,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="conversation / user preference",
        agent_may_say="Acknowledge the communication/access need and request staff assistance.",
        agent_may_continue=("preserve context", "maintain connection"),
        must_stop=("claiming unsupported accommodations are arranged", "booking before support is resolved"),
        msa_action="Use the approved accessibility or language-support workflow.",
        audit_event="human_attention_required",
        fail_closed_behavior="Do not claim support was arranged unless verified.",
    ),
    GuardrailTrigger.VERIFICATION_FAILURE: GuardrailRule(
        trigger=GuardrailTrigger.VERIFICATION_FAILURE,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="scheduling adapter / verification service",
        agent_may_say="Explain that the selected slot could not be verified.",
        agent_may_continue=("preserve preferences", "offer verified governed alternatives if available"),
        must_stop=("confirmation of failed slot", "approval", "simulated booking"),
        msa_action="Review the failure or restart governed availability search.",
        audit_event="human_attention_required",
        fail_closed_behavior="Failed or inconclusive verification is never treated as verified.",
    ),
    GuardrailTrigger.COMMUNITY_CARE_BRANCH: GuardrailRule(
        trigger=GuardrailTrigger.COMMUNITY_CARE_BRANCH,
        severity=GuardrailSeverity.HIGH,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="access assessment / workflow branch",
        agent_may_say="Explain that the request requires a workflow outside this Primary Care slice.",
        agent_may_continue=("preserve access evidence", "preserve preferences"),
        must_stop=("authorization inference", "external booking", "continuing the internal-care slice"),
        msa_action="Route to the governed Community Care workflow.",
        audit_event="human_attention_required",
        fail_closed_behavior="Do not infer Community Care authorization or perform external booking.",
    ),
    GuardrailTrigger.ACTION_OUTSIDE_AUTHORITY: GuardrailRule(
        trigger=GuardrailTrigger.ACTION_OUTSIDE_AUTHORITY,
        severity=GuardrailSeverity.CRITICAL,
        handoff=HandoffRequirement.MANDATORY,
        detection_source="application authorization boundary",
        agent_may_say="Explain that staff authorization is required before proceeding.",
        agent_may_continue=("preserve context",),
        must_stop=("unauthorized approval", "production booking", "governed-record override"),
        msa_action="Perform or decline the action through the authorized application path.",
        audit_event="human_attention_required",
        fail_closed_behavior="Reject the action and preserve the prior governed state.",
    ),
    GuardrailTrigger.LOW_CONFIDENCE_CONVERSATION_FIELD: GuardrailRule(
        trigger=GuardrailTrigger.LOW_CONFIDENCE_CONVERSATION_FIELD,
        severity=GuardrailSeverity.ADVISORY,
        handoff=HandoffRequirement.ADVISORY,
        detection_source="conversation extraction",
        agent_may_say="Ask the Veteran to clarify the uncertain preference or intent.",
        agent_may_continue=("clarify conversation-derived field", "load governed context"),
        must_stop=(),
        msa_action="Monitor if useful; join if clarification remains unresolved or another mandatory trigger appears.",
        audit_event="human_attention_recommended",
        fail_closed_behavior="Leave the field unknown until clarified; do not guess.",
    ),
}


def guardrail_rule(trigger: GuardrailTrigger) -> GuardrailRule:
    return _RULES[trigger]


def guardrail_matrix() -> tuple[GuardrailRule, ...]:
    return tuple(_RULES[trigger] for trigger in GuardrailTrigger)


def evaluate_guardrails(
    triggers: tuple[GuardrailTrigger, ...],
    *,
    interaction_id: str,
    case_id: str,
    scheduling_encounter_id: str,
    correlation_id: str,
) -> GuardrailAssessment:
    if not all((interaction_id, case_id, scheduling_encounter_id, correlation_id)):
        raise ValueError("All correlation identifiers are required.")

    if not triggers:
        return GuardrailAssessment(
            triggers=(),
            highest_severity=GuardrailSeverity.ADVISORY,
            handoff=HandoffRequirement.NONE,
            human_control_mode=HumanControlMode.AGENT_HANDLING,
            may_continue_conversation=True,
            may_continue_scheduling_progression=True,
            must_stop_consequential_actions=False,
            msa_action="No guardrail action required.",
            audit_event="",
            handoff_payload={
                "interaction_id": interaction_id,
                "case_id": case_id,
                "scheduling_encounter_id": scheduling_encounter_id,
                "correlation_id": correlation_id,
                "triggers": [],
            },
        )

    unique = tuple(dict.fromkeys(triggers))
    rules = tuple(_RULES[trigger] for trigger in unique)
    highest = max(rule.severity for rule in rules)
    mandatory = any(rule.handoff is HandoffRequirement.MANDATORY for rule in rules)

    if mandatory:
        handoff = HandoffRequirement.MANDATORY
        mode = HumanControlMode.WARM_TRANSFER_REQUIRED
        scheduling_progression = False
        stop_consequential = True
        audit_event = "human_attention_required"
    else:
        handoff = HandoffRequirement.ADVISORY
        mode = HumanControlMode.ATTENTION_RECOMMENDED
        scheduling_progression = True
        stop_consequential = False
        audit_event = "human_attention_recommended"

    ordered = sorted(rules, key=lambda rule: (-int(rule.severity), rule.trigger.value))
    primary = ordered[0]

    return GuardrailAssessment(
        triggers=unique,
        highest_severity=highest,
        handoff=handoff,
        human_control_mode=mode,
        may_continue_conversation=True,
        may_continue_scheduling_progression=scheduling_progression,
        must_stop_consequential_actions=stop_consequential,
        msa_action=primary.msa_action,
        audit_event=audit_event,
        handoff_payload={
            "interaction_id": interaction_id,
            "case_id": case_id,
            "scheduling_encounter_id": scheduling_encounter_id,
            "correlation_id": correlation_id,
            "triggers": [rule.trigger.value for rule in ordered],
            "highest_severity": highest.name,
            "handoff": handoff.value,
            "msa_action": primary.msa_action,
            "must_stop": sorted({item for rule in rules for item in rule.must_stop}),
            "synthetic": True,
        },
    )
