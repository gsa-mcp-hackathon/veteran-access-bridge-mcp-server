"""VistA/ISS synthetic source adapter.

Loads a deterministic JSON fixture from the installed package resource and
normalizes each slot record into an AccessOption. Source-specific fields never
leak into the returned AccessOption; they are resolved here before the option
is constructed.

Fixture resolution
------------------
Default fixtures are loaded via importlib.resources from the
``veteran_access_bridge.adapters.fixtures`` package sub-directory, which is
declared as package data in pyproject.toml and therefore available after any
``pip install``.

Pass ``fixture_path`` to override the default — used in tests that supply a
custom or malformed fixture file.

Clock injection
---------------
Pass ``as_of`` to fix the search timestamp for deterministic tests. When
omitted, ``datetime.now(timezone.utc)`` is used at the start of ``search()``.
The same value serves as both ``SourceProvenance.retrieved_at`` and the
reference point for slot expiry evaluation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from veteran_access_bridge.domain.models import (
    AccessOption,
    AppointmentIntent,
    OptionReadiness,
    PatientClinicClassification,
    ResourceType,
    SchedulingSlot,
    SlotAvailability,
    SlotTemplateType,
    SourceProvenance,
    SourceSearchResult,
    SourceSearchStatus,
)

_SOURCE_SYSTEM = "VISTA_ISS"
_FIXTURE_NAME = "vista-slots-cardiology.json"
_PRIMARY_CARE_FIXTURE_NAME = "vista-slots-primary-care.json"


def _default_fixture_text(specialty: str) -> str:
    """Return the source fixture selected by normalized scheduling service."""
    fixture_name = (
        _PRIMARY_CARE_FIXTURE_NAME
        if specialty.strip().upper() == "PRIMARY_CARE"
        else _FIXTURE_NAME
    )
    return (
        files("veteran_access_bridge.adapters.fixtures")
        .joinpath(fixture_name)
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Availability status allow-list — fail-safe validation
# ---------------------------------------------------------------------------


class _SlotAvailabilityStatus(StrEnum):
    """Known availability status values for VistA/ISS slot records.

    Any value not in this list fails Pydantic validation and is never mapped
    to an AccessOption. Unknown, ambiguous, or non-schedulable statuses
    (BOOKED, CANCELLED, HELD, etc.) must not appear as fixture records.
    """

    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Pydantic fixture models (private — not exported)
# ---------------------------------------------------------------------------


class _VistaSlotRecord(BaseModel):
    slot_id: str
    patient_id: str
    specialty: str
    facility_id: str
    facility_name: str
    provider: Optional[str] = None
    clinic_id: Optional[str] = None
    stop_code: Optional[str] = None
    stop_code_group: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    template_type: Optional[SlotTemplateType] = None
    modality: Optional[str] = None
    eligible_patient_classifications: tuple[PatientClinicClassification, ...] = ()
    eligible_appointment_intents: tuple[AppointmentIntent, ...] = ()
    slot_start: datetime
    slot_end: datetime
    availability_status: _SlotAvailabilityStatus
    wait_days: Optional[int] = None
    drive_minutes: Optional[int] = None
    synthetic: Literal[True]  # records with synthetic=false are rejected
    environment: str
    source_system: Literal["VISTA_ISS"]
    freshness: str

    @field_validator("slot_start", "slot_end", mode="before")
    @classmethod
    def _parse_dt(cls, v: str) -> datetime:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

    @model_validator(mode="after")
    def _validate_interval(self) -> "_VistaSlotRecord":
        if self.slot_end <= self.slot_start:
            raise ValueError(
                f"slot_end ({self.slot_end!r}) must be after slot_start "
                f"({self.slot_start!r}) for slot {self.slot_id!r}."
            )
        return self


class _VistaFixtureMeta(BaseModel):
    """Fail-closed identity metadata for this adapter's fixture."""

    synthetic: Literal[True]
    source_system: Literal["VISTA_ISS"]


class _VistaFixture(BaseModel):
    fixture_meta: _VistaFixtureMeta = Field(alias="_fixture_meta")
    slots: list[_VistaSlotRecord]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _readiness_for_status(
    status: _SlotAvailabilityStatus,
    slot_end: datetime,
    as_of: datetime,
) -> OptionReadiness:
    """Determine readiness for a VistA slot.

    Expiry is checked after the fixture status: a slot whose slot_end is at
    or before as_of is mapped to STALE regardless of its declared status,
    preserving source evidence while marking it non-schedulable.
    """
    if status is _SlotAvailabilityStatus.STALE:
        return OptionReadiness.STALE
    if status is _SlotAvailabilityStatus.UNAVAILABLE:
        return OptionReadiness.UNAVAILABLE
    if slot_end <= as_of:
        return OptionReadiness.STALE
    return OptionReadiness.AVAILABLE


def _normalized_slot_availability(
    status: _SlotAvailabilityStatus,
    slot_end: datetime,
    as_of: datetime,
) -> SlotAvailability:
    if status is _SlotAvailabilityStatus.STALE or slot_end <= as_of:
        return SlotAvailability.STALE
    if status is _SlotAvailabilityStatus.UNAVAILABLE:
        return SlotAvailability.UNAVAILABLE
    return SlotAvailability.AVAILABLE


def _normalize_scheduling_slot(
    record: _VistaSlotRecord,
    retrieved_at: datetime,
    as_of: datetime,
) -> SchedulingSlot | None:
    if record.resource_type is None or record.template_type is None:
        return None

    provenance = SourceProvenance(
        source_system=_SOURCE_SYSTEM,
        source_record_id=record.slot_id,
        retrieved_at=retrieved_at,
        synthetic=record.synthetic,
        environment=record.environment,
        freshness=record.freshness,
    )
    duration = int((record.slot_end - record.slot_start).total_seconds() // 60)
    return SchedulingSlot(
        slot_id=record.slot_id,
        source_system=_SOURCE_SYSTEM,
        source_record_id=record.slot_id,
        facility_id=record.facility_id,
        facility_name=record.facility_name,
        clinic_id=record.clinic_id,
        stop_code=record.stop_code,
        stop_code_group=record.stop_code_group,
        service=record.specialty,
        resource_id=record.resource_id,
        resource_name=record.provider,
        resource_type=record.resource_type,
        template_type=record.template_type,
        modality=record.modality,
        slot_start=record.slot_start,
        slot_end=record.slot_end,
        duration_minutes=duration,
        availability=_normalized_slot_availability(
            record.availability_status, record.slot_end, as_of
        ),
        eligible_patient_classifications=record.eligible_patient_classifications,
        eligible_appointment_intents=record.eligible_appointment_intents,
        provenance=provenance,
        synthetic=record.synthetic,
    )


def _normalize(
    record: _VistaSlotRecord,
    retrieved_at: datetime,
    as_of: datetime,
) -> AccessOption:
    provenance = SourceProvenance(
        source_system=_SOURCE_SYSTEM,
        source_record_id=record.slot_id,
        retrieved_at=retrieved_at,
        synthetic=record.synthetic,
        environment=record.environment,
        freshness=record.freshness,
    )
    duration = int(
        (record.slot_end - record.slot_start).total_seconds() // 60
    )
    return AccessOption(
        option_id=f"OPT-{record.slot_id}",
        source_system=_SOURCE_SYSTEM,
        source_record_id=record.slot_id,
        specialty=record.specialty,
        facility_name=record.facility_name,
        facility_id=record.facility_id,
        slot_start=record.slot_start,
        slot_end=record.slot_end,
        availability_status=record.availability_status,
        readiness=_readiness_for_status(record.availability_status, record.slot_end, as_of),
        provenance=provenance,
        provider=record.provider,
        duration_minutes=duration,
        wait_days=record.wait_days,
        drive_minutes=record.drive_minutes,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class VistAAdapter:
    """Synthetic VistA/ISS availability adapter.

    Parameters
    ----------
    simulate_unavailable:
        When True, the adapter returns SOURCE_UNAVAILABLE without reading the
        fixture. Use in tests to verify partial-source failure behaviour.
    fixture_path:
        Override the default fixture path. When set, the file at this path is
        read directly instead of the installed package resource.
    as_of:
        Reference timestamp for slot expiry evaluation and provenance
        retrieved_at. When None, datetime.now(timezone.utc) is used at the
        start of search(). Always supply an explicit value in tests.
    """

    def __init__(
        self,
        simulate_unavailable: bool = False,
        fixture_path: Optional[Path] = None,
        as_of: Optional[datetime] = None,
    ) -> None:
        self._simulate_unavailable = simulate_unavailable
        self._fixture_path = fixture_path
        self._as_of = as_of

    def search_scheduling_slots(
        self,
        patient_id: str,
        specialty: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> tuple[SchedulingSlot, ...]:
        """Return normalized M6.2 SchedulingSlot records for this synthetic source.

        This is a read-only parallel bridge. Existing search()/AccessOption
        behavior remains unchanged.
        """
        as_of = (
            as_of
            if as_of is not None
            else self._as_of
            if self._as_of is not None
            else datetime.now(timezone.utc)
        )

        if self._simulate_unavailable:
            return ()

        try:
            if self._fixture_path is not None:
                text = self._fixture_path.read_text(encoding="utf-8")
            else:
                text = _default_fixture_text(specialty)
            raw = json.loads(text)
            fixture = _VistaFixture.model_validate(raw)
        except Exception:
            return ()

        matching = [
            s
            for s in fixture.slots
            if s.patient_id == patient_id
            and s.specialty.strip().lower() == specialty.strip().lower()
        ]
        normalized = (
            _normalize_scheduling_slot(s, as_of, as_of) for s in matching
        )
        return tuple(slot for slot in normalized if slot is not None)

    def search(
        self,
        patient_id: str,
        specialty: str,
        *,
        as_of: Optional[datetime] = None,
    ) -> SourceSearchResult:
        # A call-level clock overrides the constructor clock so an orchestrated
        # search can use one deterministic timestamp across every source.
        as_of = (
            as_of
            if as_of is not None
            else self._as_of
            if self._as_of is not None
            else datetime.now(timezone.utc)
        )

        if self._simulate_unavailable:
            return SourceSearchResult(
                source_system=_SOURCE_SYSTEM,
                status=SourceSearchStatus.SOURCE_UNAVAILABLE,
                retrieved_at=as_of,
                error_message="VistA/ISS adapter simulated as unavailable.",
            )

        try:
            if self._fixture_path is not None:
                text = self._fixture_path.read_text(encoding="utf-8")
            else:
                text = _default_fixture_text(specialty)
            raw = json.loads(text)
            fixture = _VistaFixture.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            return SourceSearchResult(
                source_system=_SOURCE_SYSTEM,
                status=SourceSearchStatus.SOURCE_UNAVAILABLE,
                retrieved_at=as_of,
                error_message=f"Fixture load error: {type(exc).__name__}",
            )

        matching = [
            s
            for s in fixture.slots
            if s.patient_id == patient_id
            and s.specialty.strip().lower() == specialty.strip().lower()
        ]

        if not matching:
            return SourceSearchResult(
                source_system=_SOURCE_SYSTEM,
                status=SourceSearchStatus.NO_SLOTS,
                retrieved_at=as_of,
            )

        options = tuple(_normalize(s, as_of, as_of) for s in matching)
        return SourceSearchResult(
            source_system=_SOURCE_SYSTEM,
            status=SourceSearchStatus.SUCCESS,
            retrieved_at=as_of,
            options=options,
        )
