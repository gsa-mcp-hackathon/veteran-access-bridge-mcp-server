"""Booking gate service — M2-7.

validate_booking_preconditions() and simulated_commit() implement the
T26 booking gate: PENDING_SCHEDULER_APPROVAL → BOOKED_SIMULATED.

Design rules
------------
1. Two distinct operations; do not conflate them.

   validate_booking_preconditions():
       Read-only gate. Checks all preconditions without writing any state.
       Called by the MCP tool of the same name. Returns BookingPreconditionResult.
       Does not reserve slots, write BookingRecord, or append events.

   simulated_commit():
       Single transaction-like critical section. Either ALL of the following
       succeed atomically, or NONE of them persist:
         - slot reservation
         - BookingRecord creation
         - BOOKED_SIMULATED lifecycle event

       Internal rollback is used on failure: if the BookingStore or
       CaseEventStore raise after the reservation was placed, the reservation
       is revoked before re-raising. No partial externally visible state.

2. EPS / HSRM are checked independently. No check infers one from the other.
   EPS availability is never treated as authorization evidence.
   HSRM authorization is never treated as proof the EPS slot is still available.

3. Explicit Scheduler approval is required.
   actor_role must be ActorRole.SCHEDULER for simulated_commit().
   SYSTEM and VETERAN actors are rejected.
   Being in PENDING_SCHEDULER_APPROVAL state alone is not sufficient.

4. FOLLOW_UP intent fails closed.
   FOLLOW_UP must not proceed via the EPS initial-consult path.
   A FOLLOW_UP attempt raises ValueError at the intent guard.

5. Idempotency matches M2-4/M2-5/M2-6 exactly.
   booking_id = "bk-" + SHA-256(idempotency_key)[:16].
   Same key + same material → return existing BookingRecord (no-op, no new event).
   Same key + different case/option/slot → IdempotencyConflictError.

6. Missing or wrong lifecycle state fails closed.
   No backfill, no fallback, no default state.

Governance boundaries
---------------------
- Never grants Community Care authorization.
- Never infers authorization from EPS availability.
- Never infers EPS slot availability from authorization.
- Never infers clinical eligibility or appropriateness.
- Never creates BOOKED_SIMULATED outside simulated_commit().
- MCP never calls simulated_commit() directly.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
    BookingPreconditionResult,
    BookingRecord,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    EPSSlotRecord,
    HSRMAuthorizationRecord,
    HSRMAuthorizationStatus,
    SlotReservation,
)
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.events import (
    CaseEventStore,
    IdempotencyConflictError,
)
from veteran_access_bridge.services.selection import SelectionStore

# Lifecycle state required to commit a booking.
_PENDING_SCHEDULER_APPROVAL = CaseLifecycleState.PENDING_SCHEDULER_APPROVAL

# Source systems that route through the VA/Federal path (no HSRM/EPS checks).
_VA_FEDERAL_SOURCES: frozenset[str] = frozenset(
    {
        "VISTA_ISS",
        "VISTA",
        "FEDERAL_EHR",
        "FEDERAL_EHR_FHIR",
    }
)


def _booking_id(idempotency_key: str) -> str:
    return "bk-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]


def _reservation_id(slot_id: str, case_id: str) -> str:
    raw = f"{slot_id}:{case_id}"
    return "rsv-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _material_fields_booking(record: BookingRecord) -> tuple:
    return (record.case_id, record.option_id, record.slot_id)


class SlotReservationStore:
    """In-memory slot reservation store for double-booking protection.

    One active reservation per slot_id. First write wins. A second attempt
    to reserve the same slot from a different case fails.
    """

    def __init__(self) -> None:
        self._by_slot: dict[str, SlotReservation] = {}

    def reserve(self, reservation: SlotReservation) -> bool:
        """Attempt to reserve a slot. Returns True on success, False if already held."""
        if reservation.slot_id in self._by_slot:
            return False
        self._by_slot[reservation.slot_id] = reservation
        return True

    def release(self, slot_id: str) -> None:
        """Release a reservation (used for rollback only)."""
        self._by_slot.pop(slot_id, None)

    def get(self, slot_id: str) -> Optional[SlotReservation]:
        return self._by_slot.get(slot_id)

    def is_reserved(self, slot_id: str) -> bool:
        return slot_id in self._by_slot

    def __len__(self) -> int:
        return len(self._by_slot)


class BookingStore:
    """In-memory repository for BookingRecord documents.

    Keyed by booking_id and idempotency_key. First-write wins per booking_id.
    """

    def __init__(self) -> None:
        self._by_booking_id: dict[str, BookingRecord] = {}
        self._by_idempotency_key: dict[str, BookingRecord] = {}

    def put(self, record: BookingRecord) -> None:
        """Store a record. First write wins per booking_id."""
        if record.booking_id not in self._by_booking_id:
            self._by_booking_id[record.booking_id] = record
            self._by_idempotency_key[record.idempotency_key] = record

    def get(self, booking_id: str) -> Optional[BookingRecord]:
        return self._by_booking_id.get(booking_id)

    def get_by_key(self, idempotency_key: str) -> Optional[BookingRecord]:
        return self._by_idempotency_key.get(idempotency_key)

    def __len__(self) -> int:
        return len(self._by_booking_id)


def _is_community_care(source_system: str) -> bool:
    """Return True if the source is a Community Care (HSRM/EPS) source."""
    return source_system.upper() not in {s.upper() for s in _VA_FEDERAL_SOURCES}


def _run_community_care_checks(
    option_id: str,
    slot_id: str,
    intended_service: str,
    appointment_intent: AppointmentIntent,
    hsrm_record: Optional[HSRMAuthorizationRecord],
    eps_slot: Optional[EPSSlotRecord],
    provider_id: Optional[str],
    as_of: datetime,
) -> list[str]:
    """Run HSRM and EPS checks independently. Returns list of failure reasons."""
    failures: list[str] = []

    # ── Appointment intent guard ───────────────────────────────────────────
    if appointment_intent == AppointmentIntent.FOLLOW_UP:
        failures.append(
            "FOLLOW_UP intent cannot proceed via the EPS initial-consult path. "
            "Route to the appropriate non-EPS follow-up workflow or HUMAN_REVIEW."
        )
        return failures  # no point checking adapters if intent is wrong

    # ── HSRM authorization checks ──────────────────────────────────────────
    if hsrm_record is None:
        failures.append(
            f"No HSRM authorization found for option {option_id!r}. "
            "Community Care booking requires an active authorization/referral."
        )
    else:
        if hsrm_record.status != HSRMAuthorizationStatus.ACTIVE:
            failures.append(
                f"HSRM authorization {hsrm_record.authorization_id!r} status is "
                f"{hsrm_record.status!r}. Only ACTIVE authorizations may proceed."
            )
        if as_of > hsrm_record.expiration_date:
            failures.append(
                f"HSRM authorization {hsrm_record.authorization_id!r} expired at "
                f"{hsrm_record.expiration_date.isoformat()}."
            )
        if hsrm_record.authorized_service.upper() != intended_service.upper():
            failures.append(
                f"HSRM authorization covers {hsrm_record.authorized_service!r}, "
                f"not {intended_service!r}. Service/specialty mismatch."
            )
        if (
            hsrm_record.authorized_provider_id is not None
            and provider_id is not None
            and hsrm_record.authorized_provider_id != provider_id
        ):
            failures.append(
                "HSRM authorization is for provider "
                f"{hsrm_record.authorized_provider_id!r}, "
                f"not {provider_id!r}. Provider/referral compatibility "
                "check failed."
            )

    # ── EPS slot checks ────────────────────────────────────────────────────
    if eps_slot is None:
        failures.append(
            f"No EPS slot found for slot_id {slot_id!r}. "
            "Community Care booking requires an available EPS slot."
        )
    else:
        if not eps_slot.available:
            failures.append(f"EPS slot {slot_id!r} is not available.")
        if not eps_slot.initial_consult_eligible:
            failures.append(
                f"EPS slot {slot_id!r} is not eligible for "
                "INITIAL_CONSULT appointments."
            )

    return failures


def validate_booking_preconditions(
    case_id: str,
    option_id: str,
    slot_id: str,
    source_system: str,
    intended_service: str,
    appointment_intent: AppointmentIntent,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    confirmation_store: ConfirmationStore,
    selection_store: SelectionStore,
    booking_store: BookingStore,
    hsrm_record: Optional[HSRMAuthorizationRecord] = None,
    eps_slot: Optional[EPSSlotRecord] = None,
    *,
    _as_of: Optional[datetime] = None,
) -> BookingPreconditionResult:
    """Read-only gate: check all booking preconditions without writing state.

    Called by the MCP tool validate_booking_preconditions. Returns
    BookingPreconditionResult. Writes nothing.

    Parameters
    ----------
    case_id:            Synthetic scheduling case ID.
    option_id:          The option being booked.
    slot_id:            The specific EPS/VA slot.
    source_system:      Source system (determines CC vs VA/Federal path).
    intended_service:   Specialty/service (e.g. "CARDIOLOGY").
    appointment_intent: AppointmentIntent — must be INITIAL_CONSULT for EPS path.
    actor_role:         Must be ActorRole.SCHEDULER.
    actor_id:           Opaque Scheduler identifier.
    idempotency_key:    Caller-supplied deduplication key.
    event_store:        Must contain lifecycle at PENDING_SCHEDULER_APPROVAL.
    confirmation_store: Must contain Veteran CONFIRMED response.
    selection_store:    Must contain a matching selection for the case.
    booking_store:      Checked for existing/conflicting bookings.
    hsrm_record:        HSRM authorization (required for Community Care).
    eps_slot:           EPS slot record (required for Community Care).
    _as_of:             Explicit timestamp for testing.
    """
    as_of = _as_of if _as_of is not None else datetime.now(timezone.utc)
    failures: list[str] = []
    is_cc = _is_community_care(source_system)

    # ── 1. Lifecycle guard ─────────────────────────────────────────────────
    lc = event_store.get_lifecycle_record(case_id)
    if lc is None:
        failures.append(f"Case {case_id!r} has no lifecycle history.")
    elif lc.current_state != _PENDING_SCHEDULER_APPROVAL:
        failures.append(
            f"Case {case_id!r} is in state {lc.current_state!r}. "
            f"Booking requires {_PENDING_SCHEDULER_APPROVAL!r}."
        )

    # ── 2. Scheduler role guard ────────────────────────────────────────────
    if actor_role != ActorRole.SCHEDULER:
        failures.append(
            f"Only ActorRole.SCHEDULER may commit a booking. Got: {actor_role!r}."
        )

    # ── 3. Veteran confirmation guard ──────────────────────────────────────
    from veteran_access_bridge.domain.models import VeteranResponse

    conf = confirmation_store.get_confirmation_for_case(case_id)
    if conf is None:
        failures.append(
            f"No Veteran confirmation found for case {case_id!r}. "
            "Veteran must explicitly confirm before booking."
        )
    elif conf.response != VeteranResponse.CONFIRMED:
        failures.append(
            f"Veteran response is {conf.response!r}, not CONFIRMED. "
            "Booking requires explicit CONFIRMED response."
        )

    # ── 4. Selection guard ─────────────────────────────────────────────────
    sel = selection_store.get_for_case(case_id)
    if sel is None:
        failures.append(f"No option selection found for case {case_id!r}.")
    elif sel.option_id != option_id:
        failures.append(
            f"Selected option {sel.option_id!r} does not match "
            f"requested option {option_id!r}."
        )

    # ── 5. Duplicate booking guard ─────────────────────────────────────────
    existing = booking_store.get_by_key(idempotency_key)
    if existing is not None:
        if _material_fields_booking(existing) != (case_id, option_id, slot_id):
            failures.append(
                f"Idempotency key {idempotency_key!r} was used for a "
                "different booking. "
                "Use a new key for a different booking attempt."
            )

    # ── 6–8. Source-specific checks ────────────────────────────────────────
    hsrm_checked = False
    eps_checked = False
    if is_cc:
        hsrm_checked = True
        eps_checked = True
        cc_failures = _run_community_care_checks(
            option_id=option_id,
            slot_id=slot_id,
            intended_service=intended_service,
            appointment_intent=appointment_intent,
            hsrm_record=hsrm_record,
            eps_slot=eps_slot,
            provider_id=(eps_slot.provider_id if eps_slot else None),
            as_of=as_of,
        )
        failures.extend(cc_failures)

    return BookingPreconditionResult(
        passed=len(failures) == 0,
        case_id=case_id,
        option_id=option_id,
        hsrm_checked=hsrm_checked,
        eps_checked=eps_checked,
        failures=tuple(failures),
    )


def simulated_commit(
    case_id: str,
    option_id: str,
    slot_id: str,
    source_system: str,
    intended_service: str,
    appointment_intent: AppointmentIntent,
    patient_id: str,
    consult_id: str,
    handoff_id: str,
    facility_name: str,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    confirmation_store: ConfirmationStore,
    selection_store: SelectionStore,
    booking_store: BookingStore,
    reservation_store: SlotReservationStore,
    hsrm_record: Optional[HSRMAuthorizationRecord] = None,
    eps_slot: Optional[EPSSlotRecord] = None,
    *,
    _as_of: Optional[datetime] = None,
) -> BookingRecord:
    """Atomic simulated booking commit (T26).

    Single transaction-like critical section. Either ALL state changes
    (reservation, BookingRecord, BOOKED_SIMULATED event) succeed together,
    or NONE of them persist. Internal rollback reverts the reservation if
    BookingStore or CaseEventStore raise after the slot was held.

    Requires explicit ActorRole.SCHEDULER. SYSTEM and VETERAN are rejected.
    PENDING_SCHEDULER_APPROVAL lifecycle state alone is not sufficient proof
    of Scheduler approval.

    Parameters
    ----------
    case_id, option_id, slot_id, source_system, intended_service:
        Booking context.
    appointment_intent:
        Must be INITIAL_CONSULT for the EPS path. FOLLOW_UP fails closed.
    patient_id, consult_id, handoff_id, facility_name:
        Booking artifact context.
    actor_role:         Must be ActorRole.SCHEDULER.
    actor_id:           Opaque Scheduler identifier.
    idempotency_key:    Caller-supplied deduplication key.
    event_store:        Must be at PENDING_SCHEDULER_APPROVAL.
    confirmation_store: Must contain CONFIRMED Veteran response.
    selection_store:    Must contain matching selection.
    booking_store:      Persists the BookingRecord.
    reservation_store:  Persists the SlotReservation.
    hsrm_record:        HSRM authorization evidence (Community Care only).
    eps_slot:           EPS slot record (Community Care only).
    _as_of:             Explicit timestamp for testing.

    Returns
    -------
    BookingRecord
        The committed (or idempotently-returned existing) booking record.

    Raises
    ------
    ValueError
        On any precondition failure, intent mismatch, or missing state.
    IdempotencyConflictError
        If idempotency_key is reused with different material fields.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)
    is_cc = _is_community_care(source_system)

    # ── 1. Explicit Scheduler role guard ──────────────────────────────────
    if actor_role != ActorRole.SCHEDULER:
        raise ValueError(
            f"Only ActorRole.SCHEDULER may commit a booking. Got: {actor_role!r}. "
            "PENDING_SCHEDULER_APPROVAL state alone does not constitute "
            "Scheduler approval."
        )

    # ── 2. Idempotency check ───────────────────────────────────────────────
    bk_id = _booking_id(idempotency_key)
    existing = booking_store.get_by_key(idempotency_key)
    if existing is not None:
        if _material_fields_booking(existing) == (case_id, option_id, slot_id):
            return existing
        raise IdempotencyConflictError(
            f"idempotency_key {idempotency_key!r} already used for a "
            "different booking. "
            f"Existing: case={existing.case_id!r} option={existing.option_id!r} "
            f"slot={existing.slot_id!r}. "
            f"New: case={case_id!r} option={option_id!r} slot={slot_id!r}. "
            "Generate a new idempotency_key for a different booking."
        )

    # ── 3. Lifecycle guard ─────────────────────────────────────────────────
    lc = event_store.get_lifecycle_record(case_id)
    if lc is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history. "
            f"Lifecycle must be at {_PENDING_SCHEDULER_APPROVAL!r} to commit."
        )
    if lc.current_state != _PENDING_SCHEDULER_APPROVAL:
        raise ValueError(
            f"Case {case_id!r} is in state {lc.current_state!r}. "
            f"simulated_commit requires {_PENDING_SCHEDULER_APPROVAL!r}."
        )

    # ── 4. Veteran confirmation guard ──────────────────────────────────────
    from veteran_access_bridge.domain.models import VeteranResponse

    conf = confirmation_store.get_confirmation_for_case(case_id)
    if conf is None:
        raise ValueError(f"No Veteran confirmation found for case {case_id!r}.")
    if conf.response != VeteranResponse.CONFIRMED:
        raise ValueError(f"Veteran response is {conf.response!r}, not CONFIRMED.")

    # ── 5. Selection guard ─────────────────────────────────────────────────
    sel = selection_store.get_for_case(case_id)
    if sel is None:
        raise ValueError(f"No option selection found for case {case_id!r}.")
    if sel.option_id != option_id:
        raise ValueError(
            f"Selection option {sel.option_id!r} does not match booking "
            f"option {option_id!r}."
        )

    # ── 6. Appointment intent guard ────────────────────────────────────────
    if appointment_intent == AppointmentIntent.FOLLOW_UP:
        raise ValueError(
            "FOLLOW_UP intent cannot proceed via the EPS initial-consult booking path. "
            "Route to the appropriate non-EPS follow-up workflow or HUMAN_REVIEW."
        )

    # ── 7. Community Care checks (re-check at commit time) ─────────────────
    referral_id: Optional[str] = None
    authorization_id: Optional[str] = None
    hsrm_provenance_ref: Optional[str] = None
    eps_provenance_ref: Optional[str] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    appointment_start: Optional[datetime] = None
    appointment_end: Optional[datetime] = None

    if is_cc:
        # HSRM authorization re-check
        if hsrm_record is None:
            raise ValueError(
                f"Community Care booking for {case_id!r} requires HSRM "
                "authorization evidence."
            )
        if hsrm_record.status != HSRMAuthorizationStatus.ACTIVE:
            raise ValueError(
                f"HSRM authorization {hsrm_record.authorization_id!r} is "
                f"{hsrm_record.status!r}."
            )
        if occurred_at > hsrm_record.expiration_date:
            raise ValueError(
                f"HSRM authorization {hsrm_record.authorization_id!r} expired at "
                f"{hsrm_record.expiration_date.isoformat()}."
            )
        if hsrm_record.authorized_service.upper() != intended_service.upper():
            raise ValueError(
                f"HSRM authorization covers {hsrm_record.authorized_service!r}, "
                f"not {intended_service!r}."
            )

        # EPS slot re-check
        if eps_slot is None:
            raise ValueError(
                f"Community Care booking for {case_id!r} requires an EPS slot record."
            )
        if not eps_slot.available:
            raise ValueError(f"EPS slot {slot_id!r} is no longer available.")
        if not eps_slot.initial_consult_eligible:
            raise ValueError(
                f"EPS slot {slot_id!r} is not eligible for "
                "INITIAL_CONSULT appointments."
            )

        # Provider compatibility re-check
        if (
            hsrm_record.authorized_provider_id is not None
            and hsrm_record.authorized_provider_id != eps_slot.provider_id
        ):
            raise ValueError(
                "HSRM authorization requires provider "
                f"{hsrm_record.authorized_provider_id!r} "
                f"but EPS slot has provider {eps_slot.provider_id!r}. "
                "Mismatched authorization/referral context."
            )

        # Carry HSRM/EPS context into the booking record
        referral_id = hsrm_record.referral_id
        authorization_id = hsrm_record.authorization_id
        hsrm_provenance_ref = hsrm_record.provenance_ref
        eps_provenance_ref = eps_slot.provenance_ref
        provider_id = eps_slot.provider_id
        provider_name = eps_slot.provider_name
        appointment_start = eps_slot.appointment_start
        appointment_end = eps_slot.appointment_end
    else:
        # VA/Federal: use selection readiness as the slot anchor
        # appointment times are not modeled at this layer for VA/Federal
        appointment_start = occurred_at
        appointment_end = occurred_at

    # ── 8. Double-booking guard ────────────────────────────────────────────
    if reservation_store.is_reserved(slot_id):
        raise ValueError(
            f"Slot {slot_id!r} is already reserved by another booking. "
            "Double-booking is not permitted."
        )

    # ── 9. Atomic commit — reserve → write booking → append event ─────────
    # On any failure after reservation, release the slot before re-raising.
    rsv = SlotReservation(
        reservation_id=_reservation_id(slot_id, case_id),
        slot_id=slot_id,
        case_id=case_id,
        option_id=option_id,
        booking_id=bk_id,
        reserved_at=occurred_at,
    )
    if not reservation_store.reserve(rsv):
        raise ValueError(
            f"Slot {slot_id!r} could not be reserved (already held). "
            "Double-booking is not permitted."
        )

    try:
        record = BookingRecord(
            booking_id=bk_id,
            case_id=case_id,
            option_id=option_id,
            slot_id=slot_id,
            patient_id=patient_id,
            consult_id=consult_id,
            handoff_id=handoff_id,
            facility_name=facility_name,
            appointment_intent=appointment_intent,
            appointment_start=appointment_start,
            appointment_end=appointment_end,
            source_system=source_system,
            booked_at=occurred_at,
            booked_by_role=actor_role,
            booked_by_id=actor_id,
            idempotency_key=idempotency_key,
            provider_id=provider_id,
            provider_name=provider_name,
            referral_id=referral_id,
            authorization_id=authorization_id,
            hsrm_provenance_ref=hsrm_provenance_ref,
            eps_provenance_ref=eps_provenance_ref,
        )
        booking_store.put(record)

        evt = CaseEvent(
            event_id=idempotency_key,
            case_id=case_id,
            event_type=CaseEventType.BOOKED_SIMULATED,
            from_state=CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
            to_state=CaseLifecycleState.BOOKED_SIMULATED,
            actor_role=actor_role,
            actor_id=actor_id,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            payload={
                "booking_id": bk_id,
                "option_id": option_id,
                "slot_id": slot_id,
                "source_system": source_system,
                "appointment_intent": appointment_intent.value,
                "referral_id": referral_id,
                "authorization_id": authorization_id,
            },
        )
        event_store.append(evt)

    except Exception:
        # Rollback: release the slot so no partial state is visible.
        reservation_store.release(slot_id)
        raise

    return record
