"""Acceptance coverage for Issue #73 Primary Care Demo A."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app


CASE_ID = "DEMO-PC-5000999-001"
ENCOUNTER_ID = "SE-DEMO-PC-5000999-001-REQ-PC-5000999-001"
ELIGIBLE_OPTION = "OPT-VISTA-SLOT-PC-5000999-001"
EXCLUDED_OPTION = "OPT-VISTA-SLOT-PC-5000999-002"


def _headers():
    return {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "msa-demo-a",
        "X-Demo-Case": CASE_ID,
    }


def test_demo_a_phone_happy_path_end_to_end():
    with TestClient(app) as client:
        created = client.post(
            "/api/interactions",
            headers=_headers(),
            json={
                "case_id": CASE_ID,
                "scheduling_encounter_id": ENCOUNTER_ID,
                "channel": "PHONE",
                "initial_message": (
                    "I need to make an appointment with my primary care team. "
                    "Mornings work best."
                ),
            },
        )
        assert created.status_code == 201
        interaction_id = created.json()["interaction_id"]

        # The direct Primary Care encounter remains deterministic/governed.
        encounter = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=_headers(),
        )
        assert encounter.status_code == 200
        payload = encounter.json()
        assert payload["encounter"]["patient_classification"] == "ESTABLISHED"
        assert payload["encounter"]["request"]["preferred_time_of_day"] == ["MORNING"]
        assert len(payload["calendar"]) == 3
        assert len(
            [item for item in payload["calendar"] if item["state"] == "ELIGIBLE"]
        ) == 2

        # Raw/incompatible capacity cannot be selected.
        rejected = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "SELECT", "option_id": EXCLUDED_OPTION},
        )
        assert rejected.status_code == 400

        selected = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "SELECT", "option_id": ELIGIBLE_OPTION},
        )
        assert selected.status_code == 200
        assert selected.json()["demo_a"]["state"] == "SLOT_SELECTED"

        verified = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "VERIFY", "option_id": ELIGIBLE_OPTION},
        )
        assert verified.status_code == 200
        assert verified.json()["demo_a"]["state"] == "SLOT_VERIFIED"

        confirmed = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "CONFIRM"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["demo_a"]["veteran_confirmed"] is True
        assert confirmed.json()["demo_a"]["state"] == "MSA_APPROVAL_PENDING"

        approved = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "APPROVE"},
        )
        assert approved.status_code == 200
        assert approved.json()["demo_a"]["msa_approved"] is True
        assert approved.json()["demo_a"]["state"] == "MSA_APPROVED"

        booked = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "BOOK"},
        )
        assert booked.status_code == 200
        body = booked.json()
        assert body["production_write"] is False
        assert body["demo_a"]["state"] == "SIMULATED_BOOKED"
        assert body["demo_a"]["booking_id"].startswith("sim-book-")
        assert body["demo_a"]["synthetic"] is True

        refreshed = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=_headers(),
        ).json()
        selected_slot = next(
            item
            for item in refreshed["calendar"]
            if item["option_id"] == ELIGIBLE_OPTION
        )
        assert selected_slot["state"] == "SIMULATED_BOOKED"
        assert refreshed["handoff"]["next_permitted_action"] == (
            "NO_FURTHER_BOOKING_ACTION"
        )

        events = client.get(
            f"/api/interactions/{interaction_id}/events?once=1",
            headers=_headers(),
        ).text
        for event_name in (
            "intent_captured",
            "preference_captured",
            "veteran_selected",
            "slot_verified",
            "veteran_confirmed",
            "msa_approved",
            "simulated_booking_recorded",
        ):
            assert f"event: {event_name}" in events


def test_demo_a_rejects_out_of_order_booking():
    with TestClient(app) as client:
        created = client.post(
            "/api/interactions",
            headers=_headers(),
            json={
                "case_id": CASE_ID,
                "scheduling_encounter_id": ENCOUNTER_ID,
                "channel": "PHONE",
            },
        )
        interaction_id = created.json()["interaction_id"]

        fresh = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=_headers(),
        ).json()
        assert fresh["demo_a"]["state"] == "OPTIONS_READY"
        assert fresh["demo_a"]["booking_id"] is None

        # A booking cannot be created merely because the interaction exists.
        response = client.post(
            f"/api/primary-care/{interaction_id}/actions",
            headers=_headers(),
            json={"action": "BOOK"},
        )
        assert response.status_code == 400
