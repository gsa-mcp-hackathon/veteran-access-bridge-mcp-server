"""Read-only EPS booking preflight remains fail-closed."""

from datetime import datetime, timedelta, timezone

from veteran_access_bridge.adapters.pg_booking_preflight import (
    evaluate_booking_blockers,
)

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def sample_option(*, association="EXACT_SLOT", status="AVAILABLE"):
    return {
        "slot_id": "synthetic-slot",
        "provider_id": "synthetic-provider",
        "option_id": "synthetic-option",
        "fixture_status": status,
        "initial_consult_eligible": True,
        "starts_at": (NOW + timedelta(days=8)).isoformat(),
        "verified_at": None,
        "authorizations": [
            {
                "slot_bound": association == "EXACT_SLOT",
                "association": association,
                "status": "ACTIVE",
                "synthetic": True,
                "service_scope": "CARDIOLOGY",
                "valid_from": (NOW - timedelta(days=1)).isoformat(),
                "valid_until": (NOW + timedelta(days=30)).isoformat(),
            }
        ],
    }


def test_preflight_does_not_accept_unbound_authorization():
    reasons = evaluate_booking_blockers(
        sample_option(association="OPTION_PROVIDER_ONLY"),
        now=NOW,
        requested_service="Cardiology",
    )
    assert "NO_EXACT_SLOT_HSRM_BINDING" in reasons
    assert "TRUSTED_ACTOR_SESSION_NOT_CONNECTED" in reasons


def test_preflight_blocks_stale_and_unavailable_slot():
    option = sample_option(status="BLOCKED")
    option["verified_at"] = (NOW - timedelta(hours=1)).isoformat()
    reasons = evaluate_booking_blockers(option, now=NOW, requested_service="Cardiology")
    assert "SLOT_NOT_AVAILABLE" in reasons
    assert "EPS_NOT_FRESHLY_VERIFIED" in reasons


def test_preflight_blocks_wrong_service():
    reasons = evaluate_booking_blockers(
        sample_option(), now=NOW, requested_service="Dermatology"
    )
    assert "NO_CURRENT_MATCHING_HSRM_AUTHORIZATION" in reasons


def test_preflight_is_never_authority_to_book():
    option = sample_option()
    option["verified_at"] = NOW.isoformat()
    reasons = evaluate_booking_blockers(option, now=NOW, requested_service="Cardiology")
    assert "EPS_NOT_FRESHLY_VERIFIED" not in reasons
    assert "VETERAN_CONFIRMATION_NOT_VERIFIED" in reasons
    assert "SCHEDULER_APPROVAL_NOT_VERIFIED" in reasons
    assert "TRUSTED_ACTOR_SESSION_NOT_CONNECTED" in reasons
