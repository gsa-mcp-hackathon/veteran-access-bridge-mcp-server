"""Veteran confirmation service — M2-6.

prepare_veteran_confirmation_request() and record_veteran_confirmation()
implement the governed Veteran confirmation step of the scheduling lifecycle.

Design rules
------------
1. Two distinct steps; do not conflate them.

   prepare_veteran_confirmation_request():
       A mechanical SYSTEM action that advances VERIFIED_BOOKABLE to
       PENDING_VETERAN_CONFIRMATION and creates a ConfirmationRequest artifact
       for the Veteran to review. No human judgment is applied here.
       The scheduling decision was captured at record_option_selection();
       the verification was performed at record_verification_result().

   record_veteran_confirmation():
       A VETERAN-gated step that records the Veteran's explicit response and
       advances the lifecycle accordingly:
       - CONFIRMED        → PENDING_SCHEDULER_APPROVAL
       - DECLINED         → CANCELLED
       - REQUESTED_CHANGE → HUMAN_REVIEW

2. The Veteran's response must be explicit.
   The service never infers confirmation from silence, prior preferences, or
   the existence of a confirmation request. Preparation is not consent.

3. Idempotency design.
   prepare_veteran_confirmation_request:
       confirmation_request_id is deterministic:
           SHA-256("confirmation:" + case_id + ":" + selection_id + ":" + option_id)[:16]
           prefixed with "cr-"
       Including selection_id prevents reuse if the same option is re-selected
       in a later lifecycle path. On retry: return existing request, no new event.

   record_veteran_confirmation:
       confirmation_id = "conf-" + SHA-256(idempotency_key)[:16].
       Same key + same material fields → return existing record, no new event.
       Same key + different case/confirmation_request_id/response →
           IdempotencyConflictError, no event, no record written.

4. Missing or wrong lifecycle state fails closed.
   No backfill, no fallback, no default state.

5. Exactly one lifecycle event per successful forward transition.
   No event is appended on idempotent retries or failures.

Governance boundaries
---------------------
- Never infers Veteran consent from absence of a response.
- Never grants booking authority.
- Never creates BOOKED_SIMULATED events.
- Does not implement scheduler approval, booking preconditions, or slot reservation.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    ConfirmationRequest,
    VeteranConfirmationRecord,
    VeteranResponse,
)
from veteran_access_bridge.services.events import CaseEventStore, IdempotencyConflictError
from veteran_access_bridge.services.selection import SelectionStore

# Lifecycle state required for preparing a confirmation request.
_VERIFIED_BOOKABLE = CaseLifecycleState.VERIFIED_BOOKABLE

# Lifecycle state required for recording a Veteran response.
_PENDING_VETERAN_CONFIRMATION = CaseLifecycleState.PENDING_VETERAN_CONFIRMATION

# Response → (to_state, event_type)
_RESPONSE_ROUTING: dict[VeteranResponse, tuple[CaseLifecycleState, CaseEventType]] = {
    VeteranResponse.CONFIRMED: (
        CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        CaseEventType.VETERAN_CONFIRMED,
    ),
    VeteranResponse.DECLINED: (
        CaseLifecycleState.CANCELLED,
        CaseEventType.VETERAN_DECLINED,
    ),
    VeteranResponse.REQUESTED_CHANGE: (
        CaseLifecycleState.HUMAN_REVIEW,
        CaseEventType.VETERAN_REQUESTED_CHANGE,
    ),
}


def _confirmation_request_id(case_id: str, selection_id: str, option_id: str) -> str:
    """Derive a deterministic confirmation_request_id.

    Includes selection_id so a new lifecycle path with a re-selected option
    cannot reuse an old confirmation request.
    """
    raw = f"confirmation:{case_id}:{selection_id}:{option_id}"
    return "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _confirmation_id(idempotency_key: str) -> str:
    """Derive a deterministic confirmation_id from the caller-supplied key."""
    return "conf-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]


def _material_fields(record: VeteranConfirmationRecord) -> tuple:
    """Return the fields that constitute 'identical' for idempotency comparison."""
    return (record.case_id, record.confirmation_request_id, record.response)


class ConfirmationStore:
    """In-memory repository for ConfirmationRequest and VeteranConfirmationRecord.

    Parallel to SelectionStore and VerificationStore.

    First-write wins per confirmation_request_id and per confirmation_id.
    """

    def __init__(self) -> None:
        # ConfirmationRequest storage
        self._requests: dict[str, ConfirmationRequest] = {}
        self._request_case_index: dict[str, str] = {}  # case_id → confirmation_request_id

        # VeteranConfirmationRecord storage
        self._confirmations: dict[str, VeteranConfirmationRecord] = {}
        self._confirmations_by_key: dict[str, VeteranConfirmationRecord] = {}
        self._confirmation_case_index: dict[str, str] = {}  # case_id → confirmation_id

    # ------------------------------------------------------------------
    # ConfirmationRequest operations
    # ------------------------------------------------------------------

    def put_request(self, request: ConfirmationRequest) -> None:
        """Store a request. First write wins per confirmation_request_id."""
        if request.confirmation_request_id not in self._requests:
            self._requests[request.confirmation_request_id] = request
            self._request_case_index[request.case_id] = request.confirmation_request_id

    def get_request(self, confirmation_request_id: str) -> Optional[ConfirmationRequest]:
        return self._requests.get(confirmation_request_id)

    def get_request_for_case(self, case_id: str) -> Optional[ConfirmationRequest]:
        rid = self._request_case_index.get(case_id)
        if rid is None:
            return None
        return self._requests[rid]

    def request_count(self) -> int:
        return len(self._requests)

    # ------------------------------------------------------------------
    # VeteranConfirmationRecord operations
    # ------------------------------------------------------------------

    def put_confirmation(self, record: VeteranConfirmationRecord) -> None:
        """Store a confirmation record. First write wins per confirmation_id."""
        if record.confirmation_id not in self._confirmations:
            self._confirmations[record.confirmation_id] = record
            self._confirmations_by_key[record.idempotency_key] = record
            self._confirmation_case_index[record.case_id] = record.confirmation_id

    def get_confirmation(self, confirmation_id: str) -> Optional[VeteranConfirmationRecord]:
        return self._confirmations.get(confirmation_id)

    def get_confirmation_by_key(
        self, idempotency_key: str
    ) -> Optional[VeteranConfirmationRecord]:
        return self._confirmations_by_key.get(idempotency_key)

    def get_confirmation_for_case(self, case_id: str) -> Optional[VeteranConfirmationRecord]:
        cid = self._confirmation_case_index.get(case_id)
        if cid is None:
            return None
        return self._confirmations[cid]

    def confirmation_count(self) -> int:
        return len(self._confirmations)


def prepare_veteran_confirmation_request(
    case_id: str,
    option_id: str,
    selection_id: str,
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    confirmation_store: ConfirmationStore,
    *,
    _as_of: Optional[datetime] = None,
) -> ConfirmationRequest:
    """Advance VERIFIED_BOOKABLE → PENDING_VETERAN_CONFIRMATION.

    This is a mechanical SYSTEM action. No human judgment is applied.
    The confirmation request is an artifact for the Veteran to review;
    its creation does not constitute Veteran consent.

    Parameters
    ----------
    case_id:            Synthetic scheduling case ID.
    option_id:          The AccessOption being confirmed.
    selection_id:       The OptionSelectionRecord that produced this option.
    event_store:        Must contain lifecycle history at VERIFIED_BOOKABLE.
    selection_store:    Must contain an OptionSelectionRecord for selection_id.
    confirmation_store: ConfirmationStore for request persistence.
    _as_of:             Explicit timestamp for deterministic testing.

    Returns
    -------
    ConfirmationRequest
        The stored (or previously stored) confirmation request.

    Raises
    ------
    ValueError
        If lifecycle history is missing, state is wrong, or selection_id is unknown.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Idempotency: check ConfirmationStore first ──────────────────────
    # Must be checked before the lifecycle guard so that a retry after the
    # case has advanced beyond VERIFIED_BOOKABLE still returns the existing
    # request without raising. Mirrors prepare_scheduling_handoff design.
    cr_id = _confirmation_request_id(case_id, selection_id, option_id)
    existing = confirmation_store.get_request(cr_id)
    if existing is not None:
        return existing

    # ── 2. Lifecycle guard ─────────────────────────────────────────────────
    lc_record = event_store.get_lifecycle_record(case_id)
    if lc_record is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history. "
            f"Lifecycle must be at {_VERIFIED_BOOKABLE!r} to prepare a confirmation request."
        )
    if lc_record.current_state != _VERIFIED_BOOKABLE:
        raise ValueError(
            f"Case {case_id!r} is in lifecycle state {lc_record.current_state!r}. "
            f"prepare_veteran_confirmation_request requires {_VERIFIED_BOOKABLE!r}."
        )

    # ── 3. Selection guard ─────────────────────────────────────────────────
    if selection_store.get(selection_id) is None:
        raise ValueError(
            f"selection_id {selection_id!r} not found in SelectionStore. "
            "A valid OptionSelectionRecord must exist before preparing a confirmation request."
        )

    # ── 4. Append lifecycle event ──────────────────────────────────────────
    # Use cr_id as event_id — deterministic and collision-resistant.
    evt = CaseEvent(
        event_id=cr_id,
        case_id=case_id,
        event_type=CaseEventType.VETERAN_CONFIRMATION_REQUESTED,
        from_state=CaseLifecycleState.VERIFIED_BOOKABLE,
        to_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        actor_role=ActorRole.SYSTEM,
        actor_id="system",
        occurred_at=occurred_at,
        idempotency_key=cr_id,
        payload={
            "option_id": option_id,
            "selection_id": selection_id,
            "confirmation_request_id": cr_id,
        },
    )
    event_store.append(evt)

    # ── 5. Build and store ConfirmationRequest ─────────────────────────────
    request = ConfirmationRequest(
        confirmation_request_id=cr_id,
        case_id=case_id,
        option_id=option_id,
        selection_id=selection_id,
        requested_at=occurred_at,
        requested_by_role=ActorRole.SYSTEM,
    )
    confirmation_store.put_request(request)
    return request


def record_veteran_confirmation(
    case_id: str,
    confirmation_request_id: str,
    option_id: str,
    response: VeteranResponse,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    confirmation_store: ConfirmationStore,
    *,
    _as_of: Optional[datetime] = None,
) -> VeteranConfirmationRecord:
    """Record the Veteran's explicit response and advance the lifecycle.

    The Veteran's response is the only action that advances this step.
    Preparation of a confirmation request is not consent.

    Parameters
    ----------
    case_id:                 Synthetic scheduling case ID.
    confirmation_request_id: The ConfirmationRequest this response belongs to.
    option_id:               The AccessOption being confirmed.
    response:                VeteranResponse — must be an explicit enum member.
    actor_role:              Must be ActorRole.VETERAN.
    actor_id:                Opaque Veteran identifier (synthetic/demo only).
    idempotency_key:         Caller-supplied deduplication key.
    event_store:             Must contain lifecycle history at PENDING_VETERAN_CONFIRMATION.
    confirmation_store:      ConfirmationStore — must contain the confirmation request.
    _as_of:                  Explicit timestamp for deterministic testing.

    Returns
    -------
    VeteranConfirmationRecord
        The stored (or previously stored) confirmation record.

    Raises
    ------
    ValueError
        If actor_role is not VETERAN, lifecycle state is wrong, lifecycle history
        is missing, or confirmation_request_id is unknown.
    IdempotencyConflictError
        If idempotency_key is reused with different material fields.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Role guard ─────────────────────────────────────────────────────
    if actor_role != ActorRole.VETERAN:
        raise ValueError(
            f"Only ActorRole.VETERAN may record a Veteran confirmation. "
            f"Got: {actor_role!r}."
        )

    # ── 2. Response guard ─────────────────────────────────────────────────
    if not isinstance(response, VeteranResponse):
        raise ValueError(
            f"response must be a VeteranResponse enum member. Got: {response!r}. "
            f"Allowed values: {[r.value for r in VeteranResponse]}."
        )

    # ── 3. Idempotency: check ConfirmationStore by key ────────────────────
    existing = confirmation_store.get_confirmation_by_key(idempotency_key)
    if existing is not None:
        if _material_fields(existing) == (case_id, confirmation_request_id, response):
            return existing
        raise IdempotencyConflictError(
            f"idempotency_key {idempotency_key!r} already used for a different "
            f"confirmation. Existing: case={existing.case_id!r} "
            f"response={existing.response!r}. "
            f"New: case={case_id!r} response={response!r}. "
            "Generate a new idempotency_key for a different confirmation."
        )

    # ── 4. Lifecycle guard ─────────────────────────────────────────────────
    lc_record = event_store.get_lifecycle_record(case_id)
    if lc_record is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history. "
            f"Lifecycle must be at {_PENDING_VETERAN_CONFIRMATION!r} to record a response."
        )
    if lc_record.current_state != _PENDING_VETERAN_CONFIRMATION:
        raise ValueError(
            f"Case {case_id!r} is in lifecycle state {lc_record.current_state!r}. "
            f"record_veteran_confirmation requires {_PENDING_VETERAN_CONFIRMATION!r}."
        )

    # ── 5. Confirmation request guard ─────────────────────────────────────
    if confirmation_store.get_request(confirmation_request_id) is None:
        raise ValueError(
            f"confirmation_request_id {confirmation_request_id!r} not found. "
            "A ConfirmationRequest must exist before recording a response."
        )

    # ── 6. Map response → lifecycle transition ─────────────────────────────
    to_state, event_type = _RESPONSE_ROUTING[response]

    conf_id = _confirmation_id(idempotency_key)
    evt = CaseEvent(
        event_id=idempotency_key,
        case_id=case_id,
        event_type=event_type,
        from_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        to_state=to_state,
        actor_role=actor_role,
        actor_id=actor_id,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        payload={
            "confirmation_id": conf_id,
            "confirmation_request_id": confirmation_request_id,
            "option_id": option_id,
            "response": response.value,
        },
    )
    event_store.append(evt)

    # ── 7. Build and store VeteranConfirmationRecord ───────────────────────
    record = VeteranConfirmationRecord(
        confirmation_id=conf_id,
        confirmation_request_id=confirmation_request_id,
        case_id=case_id,
        option_id=option_id,
        response=response,
        responded_at=occurred_at,
        actor_role=actor_role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    confirmation_store.put_confirmation(record)
    return record
