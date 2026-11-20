"""Acceptance coverage for Issue #74 Primary Care Demo B."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app


CASE_ID = "DEMO-PC-5000999-001"
ENCOUNTER_ID = "SE-DEMO-PC-5000999-001-REQ-PC-5000999-001"
EARLIER_EXCLUDED_SLOT = "VISTA-SLOT-PC-5000999-002"
EARLIEST_ELIGIBLE_OPTION = "OPT-VISTA-SLOT-PC-5000999-001"


def _headers():
    return {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "msa-demo-b",
        "X-Demo-Case": CASE_ID,
    }


def test_demo_b_chat_explains_earliest_raw_vs_eligible_conflict():
    with TestClient(app) as client:
        created = client.post(
            "/api/interactions",
            headers=_headers(),
            json={
                "case_id": CASE_ID,
                "scheduling_encounter_id": ENCOUNTER_ID,
                "channel": "CHAT",
                "initial_message": "I want the earliest appointment you have.",
            },
        )
        assert created.status_code == 201
        interaction_id = created.json()["interaction_id"]
        assert created.json()["channel"] == "CHAT"

        encounter = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=_headers(),
        )
        assert encounter.status_code == 200
        payload = encounter.json()

        conflict = payload["handoff"]["apparent_conflict"]
        assert conflict is not None
        assert conflict["earliest_raw_slot_id"] == EARLIER_EXCLUDED_SLOT
        assert conflict["earliest_raw_state"] == "EXCLUDED"
        assert conflict["earliest_eligible_option_id"] == EARLIEST_ELIGIBLE_OPTION
        assert conflict["exclusion_reasons"]
        assert "not an eligible option" in conflict["explanation"]
        assert "earliest governed eligible option" in conflict["explanation"]

        # Only governed eligible options are offered by the encounter.
        eligible_option_ids = {
            item["option_id"] for item in payload["encounter"]["eligible_options"]
        }
        assert EARLIEST_ELIGIBLE_OPTION in eligible_option_ids
        assert "OPT-VISTA-SLOT-PC-5000999-002" not in eligible_option_ids

        response = client.post(
            f"/api/interactions/{interaction_id}/messages",
            headers=_headers(),
            json={"message": "I want the earliest appointment you have."},
        )
        assert response.status_code == 200
        agent_event = response.json()
        assert agent_event["event_type"] == "agent_answered"
        assert agent_event["source"] == "watsonx_orchestrate"
        assert agent_event["payload"]["grounded_by"] == (
            "SCHEDULING_ENCOUNTER_ELIGIBILITY"
        )
        assert "not an eligible option" in agent_event["payload"]["text"]

        # The excluded raw slot remains impossible to select.
        rejected = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={
                "action": "SELECT",
                "option_id": "OPT-VISTA-SLOT-PC-5000999-002",
            },
        )
        assert rejected.status_code == 400

        selected = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "SELECT", "option_id": EARLIEST_ELIGIBLE_OPTION},
        )
        assert selected.status_code == 200
        assert selected.json()["demo_a"]["state"] == "SLOT_SELECTED"

        stream = client.get(
            f"/api/interactions/{interaction_id}/events?once=1",
            headers=_headers(),
        ).text
        assert "event: agent_answered" in stream
        assert "SCHEDULING_ENCOUNTER_ELIGIBILITY" in stream
        assert "event: veteran_selected" in stream
