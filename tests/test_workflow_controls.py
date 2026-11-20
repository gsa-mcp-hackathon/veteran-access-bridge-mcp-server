import unittest

from veteran_access_bridge.domain import (
    GuardrailSeverity,
    GuardrailTrigger,
    HandoffRequirement,
    HumanControlMode,
    evaluate_guardrails,
    guardrail_matrix,
    guardrail_rule,
)

CTX = {
    "interaction_id": "int-001",
    "case_id": "DEMO-PC-5000999-001",
    "scheduling_encounter_id": "SE-PC-001",
    "correlation_id": "corr-001",
}


class WorkflowControlTests(unittest.TestCase):
    def test_matrix_is_complete(self):
        self.assertEqual(
            {rule.trigger for rule in guardrail_matrix()},
            set(GuardrailTrigger),
        )

    def test_normal_path_allows_progression(self):
        result = evaluate_guardrails((), **CTX)
        self.assertEqual(result.handoff, HandoffRequirement.NONE)
        self.assertEqual(result.human_control_mode, HumanControlMode.AGENT_HANDLING)
        self.assertTrue(result.may_continue_scheduling_progression)

    def test_low_confidence_is_advisory(self):
        result = evaluate_guardrails(
            (GuardrailTrigger.LOW_CONFIDENCE_CONVERSATION_FIELD,),
            **CTX,
        )
        self.assertEqual(result.handoff, HandoffRequirement.ADVISORY)
        self.assertTrue(result.may_continue_scheduling_progression)

    def test_unknown_eligibility_requires_handoff(self):
        rule = guardrail_rule(GuardrailTrigger.UNKNOWN_SLOT_ELIGIBILITY)
        self.assertEqual(rule.handoff, HandoffRequirement.MANDATORY)

    def test_authority_boundary_is_critical(self):
        result = evaluate_guardrails(
            (GuardrailTrigger.ACTION_OUTSIDE_AUTHORITY,),
            **CTX,
        )
        self.assertEqual(result.highest_severity, GuardrailSeverity.CRITICAL)
        self.assertFalse(result.may_continue_scheduling_progression)

    def test_required_rule_dominates_advisory(self):
        result = evaluate_guardrails(
            (
                GuardrailTrigger.LOW_CONFIDENCE_CONVERSATION_FIELD,
                GuardrailTrigger.UNKNOWN_SLOT_ELIGIBILITY,
            ),
            **CTX,
        )
        self.assertEqual(result.handoff, HandoffRequirement.MANDATORY)

    def test_missing_correlation_id_is_rejected(self):
        bad = dict(CTX)
        bad["correlation_id"] = ""
        with self.assertRaises(ValueError):
            evaluate_guardrails(
                (GuardrailTrigger.UNRESOLVED_READINESS,),
                **bad,
            )


if __name__ == "__main__":
    unittest.main()
