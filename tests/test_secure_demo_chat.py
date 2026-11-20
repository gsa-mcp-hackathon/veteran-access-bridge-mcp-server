"""Synthetic chat authorization and session-scoping regression tests."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app


def _headers(role: str, case: str) -> dict[str, str]:
    return {
        "X-Demo-Role": role,
        "X-Demo-Actor": "synthetic-chat-test",
        "X-Demo-Case": case,
    }


def test_veteran_demo_chat_rejects_msa_wrong_case_and_invalid_payload():
    case_id = "DEMO-PC-CHAT-GATE-001"
    with TestClient(app) as client:
        created = client.post(
            "/api/interactions",
            headers=_headers("SCHEDULER", case_id),
            json={
                "case_id": case_id,
                "scheduling_encounter_id": "SE-PC-CHAT-GATE-001",
                "channel": "CHAT",
            },
        )
        assert created.status_code == 201, created.text
        interaction_id = created.json()["interaction_id"]
        endpoint = f"/api/interactions/{interaction_id}/veteran-messages"

        assert client.post(
            endpoint,
            headers=_headers("SCHEDULER", case_id),
            json={"message": "Hello"},
        ).status_code == 403
        assert client.post(
            endpoint,
            headers=_headers("VETERAN", "DEMO-PC-OTHER-001"),
            json={"message": "Hello"},
        ).status_code == 403
        assert client.post(endpoint, json={"message": "Hello"}).status_code == 403
        assert client.post(
            endpoint,
            headers=_headers("VETERAN", case_id),
            json={"message": " "},
        ).status_code == 400
        assert client.post(
            endpoint,
            headers=_headers("VETERAN", case_id),
            json={"message": "x" * 4001},
        ).status_code == 400

        sent = client.post(
            endpoint,
            headers=_headers("VETERAN", case_id),
            json={"message": "I prefer mornings."},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["interaction_id"] == interaction_id
        assert sent.json()["event_type"] == "agent_answered"


def test_veteran_demo_message_rejects_phone_interaction():
    case_id = "DEMO-PC-CHAT-GATE-002"
    with TestClient(app) as client:
        created = client.post(
            "/api/interactions",
            headers=_headers("SCHEDULER", case_id),
            json={
                "case_id": case_id,
                "scheduling_encounter_id": "SE-PC-CHAT-GATE-002",
                "channel": "PHONE",
            },
        )
        assert created.status_code == 201, created.text
        response = client.post(
            f"/api/interactions/{created.json()['interaction_id']}/veteran-messages",
            headers=_headers("VETERAN", case_id),
            json={"message": "Hello"},
        )
        assert response.status_code == 400
