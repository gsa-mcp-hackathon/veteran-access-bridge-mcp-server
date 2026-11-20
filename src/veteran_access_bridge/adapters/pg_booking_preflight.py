"""Read-only diagnostic preflight for synthetic EPS scheduling options.

The reported blockers are informational, never authority to book.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from veteran_access_bridge.adapters.pg_scheduling_options import read_scheduling_options


def evaluate_booking_blockers(
    option: dict, *, now: datetime, requested_service: str
) -> list[str]:
    """Explain missing gates, without asserting actor approval or changing state."""
    blockers = []
    if option["fixture_status"] != "AVAILABLE":
        blockers.append("SLOT_NOT_AVAILABLE")
    if not option["initial_consult_eligible"]:
        blockers.append("NOT_INITIAL_CONSULT_ELIGIBLE")
    try:
        start = datetime.fromisoformat(option["starts_at"])
    except (TypeError, ValueError):
        blockers.append("INVALID_SLOT_START")
    else:
        if start <= now:
            blockers.append("SLOT_START_NOT_FUTURE")
    verified = option.get("verified_at")
    if verified is None:
        blockers.append("EPS_NOT_FRESHLY_VERIFIED")
    else:
        try:
            checked = datetime.fromisoformat(verified)
        except (TypeError, ValueError):
            blockers.append("INVALID_EPS_VERIFICATION")
        else:
            if checked > now or checked < now - timedelta(minutes=15):
                blockers.append("EPS_NOT_FRESHLY_VERIFIED")
    exact = [
        a
        for a in option["authorizations"]
        if a["slot_bound"] and a["association"] == "EXACT_SLOT"
    ]
    if not exact:
        blockers.append("NO_EXACT_SLOT_HSRM_BINDING")
    elif not any(
        a["status"] == "ACTIVE"
        and a["synthetic"]
        and a["service_scope"].strip().upper() == requested_service.strip().upper()
        and a["valid_from"] is not None
        and a["valid_until"] is not None
        and datetime.fromisoformat(a["valid_from"])
        <= now
        <= datetime.fromisoformat(a["valid_until"])
        for a in exact
    ):
        blockers.append("NO_CURRENT_MATCHING_HSRM_AUTHORIZATION")
    blockers.append("VETERAN_CONFIRMATION_NOT_VERIFIED")
    blockers.append("SCHEDULER_APPROVAL_NOT_VERIFIED")
    blockers.append("TRUSTED_ACTOR_SESSION_NOT_CONNECTED")
    return blockers


def read_booking_preflight(case_id: str, *, connect=None, now=None) -> dict:
    """Use SQL case projection and explain blockers without granting readiness."""
    at = now or datetime.now(timezone.utc)
    projection = read_scheduling_options(case_id, connect=connect)
    options = [
        {
            "slot_id": option["slot_id"],
            "option_id": option["option_id"],
            "provider_id": option["provider_id"],
            "blockers": evaluate_booking_blockers(
                option, now=at, requested_service=projection["requested_service"]
            ),
            "booking_ready": False,
        }
        for option in projection["eps_options"]
    ]
    return {
        "case_id": projection["case_id"],
        "request_id": projection["request_id"],
        "options": options,
        "synthetic": True,
        "read_only": True,
        "can_commit": False,
        "source": "postgresql_dev_preflight",
    }
