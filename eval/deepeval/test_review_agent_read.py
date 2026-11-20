import copy

import pytest
from review_agent_read import review


def evidence():
    events = []
    for i, name in enumerate(
        [
            "verify_synthetic_identity",
            "get_scheduling_encounter",
            "get_scheduling_encounter",
        ]
    ):
        payload = {"tool_name": name, "tool_call_id": str(i)}
        events.append(
            {
                "event_type": "mcp_tool_called",
                "source": "watsonx_orchestrate",
                "payload": payload,
            }
        )
        events.append(
            {
                "event_type": "mcp_tool_result",
                "source": "application",
                "payload": {
                    **payload,
                    "evidence": "server_scope_receipt",
                    "invoked_by": "agent",
                    "scope_verified": True,
                    "verified_case_id": "case-A",
                    "status": "succeeded",
                    "verified": True,
                },
            }
        )
    return {
        "activity": {"events": events},
        "voice_session_id": "voice-A",
        "interaction_id": "interaction-A",
    }


def test_requires_real_correlated_read_and_followup():
    result = review(evidence(), expected_case="case-A")
    assert result["verified_agent_reads"] == 2 and result["followup_read_verified"]


@pytest.mark.parametrize(
    "fault",
    [
        "host",
        "wrong_case",
        "missing_receipt",
        "duplicate",
        "failed_identity",
        "model_receipt",
        "booking",
    ],
)
def test_rejects_incomplete_or_misattributed_evidence(fault):
    data = copy.deepcopy(evidence())
    events = data["activity"]["events"]
    if fault == "host":
        events[0]["source"] = "application"
    elif fault == "wrong_case":
        events[3]["payload"]["verified_case_id"] = "case-B"
    elif fault == "missing_receipt":
        events[:] = events[:2]
    elif fault == "duplicate":
        events.append(events[3])
    elif fault == "failed_identity":
        events[1]["payload"]["verified"] = False
    elif fault == "model_receipt":
        events[3]["source"] = "watsonx_orchestrate"
    else:
        events.append({"event_type": "simulated_booking_recorded"})
    with pytest.raises(ValueError):
        review(data, expected_case="case-A")
