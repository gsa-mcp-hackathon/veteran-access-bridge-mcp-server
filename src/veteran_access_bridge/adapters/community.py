"""Community Care / EPS synthetic source adapter.

Loads a deterministic JSON fixture from the installed package resource and
normalizes each slot record into an AccessOption. Authorization readiness is
determined explicitly:

- No authorization_id present  → AVAILABLE_NOT_AUTHORIZED
- authorization_id present     → AUTHORIZED_NOT_VERIFIED
- Stale availability_status    → STALE
- slot_end <= as_of            → STALE (expiry takes precedence over auth status)

A community option without authorization must never be represented as
VERIFIED_BOOKABLE. Community Care eligibility evidence is not equivalent
to authorization.

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
    OptionReadiness,
    SourceProvenance,
    SourceSearchResult,
    SourceSearchStatus,
)

_SOURCE_SYSTEM = "COMMUNITY_CARE_EPS"
_FIXTURE_NAME = "community-slots-cardiology.json"


def _default_fixture_text() -> str:
    """Return the fixture JSON text from the installed package resource."""
    return (
        files("veteran_access_bridge.adapters.fixtures")
        .joinpath(_FIXTURE_NAME)
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Availability status allow-list — fail-safe validation
# ---------------------------------------------------------------------------


class _SlotAvailabilityStatus(StrEnum):
    """Known availability status values for Community Care/EPS slot records.

    Any value not in this list fails Pydantic validation and is never mapped
    to an AccessOption.
    """

    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Pydantic fixture models (private — not exported)
# ---------------------------------------------------------------------------


class _CommunitySlotRecord(BaseModel):
    slot_id: str
    patient_id: str
    specialty: str
    facility_id: str
    facility_name: str
    provider: Optional[str] = None
    slot_start: datetime
    slot_end: datetime
    availability_status: _SlotAvailabilityStatus
    authorization_id: Optional[str] = None
    referral_id: Optional[str] = None
    wait_days: Optional[int] = None
    drive_minutes: Optional[int] = None
    synthetic: Literal[True]  # records with synthetic=false are rejected
    environment: str
    source_system: Literal["COMMUNITY_CARE_EPS"]
    freshness: str
    note: Optional[str] = None

    @field_validator("slot_start", "slot_end", mode="before")
    @classmethod
    def _parse_dt(cls, v: str) -> datetime:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

    @field_validator("authorization_id", mode="before")
    @classmethod
    def _normalize_authorization_id(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @model_validator(mode="after")
    def _validate_interval(self) -> "_CommunitySlotRecord":
        if self.slot_end <= self.slot_start:
            raise ValueError(
                f"slot_end ({self.slot_end!r}) must be after slot_start "
                f"({self.slot_start!r}) for slot {self.slot_id!r}."
            )
        return self


class _CommunityFixtureMeta(BaseModel):
    """Fail-closed identity metadata for this adapter's fixture."""

    synthetic: Literal[True]
    source_system: Literal["COMMUNITY_CARE_EPS"]


class _CommunityFixture(BaseModel):
    fixture_meta: _CommunityFixtureMeta = Field(alias="_fixture_meta")
    slots: list[_CommunitySlotRecord]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _readiness_for_record(
    record: _CommunitySlotRecord,
    as_of: datetime,
) -> OptionReadiness:
    """Determine readiness for a community slot.

    Ordering:
    1. Fixture status STALE  → STALE
    2. slot_end <= as_of     → STALE (expiry takes precedence over auth status)
    3. Fixture status UNAVAILABLE → UNAVAILABLE
    4. No authorization_id   → AVAILABLE_NOT_AUTHORIZED
    5. authorization_id present → AUTHORIZED_NOT_VERIFIED

    Authorization status is explicit. Eligibility evidence is never treated as
    a substitute for authorization. An expired slot is STALE regardless of
    whether authorization is present, because the appointment window is closed.
    """
    if record.availability_status is _SlotAvailabilityStatus.STALE:
        return OptionReadiness.STALE
    if record.slot_end <= as_of:
        return OptionReadiness.STALE
    if record.availability_status is _SlotAvailabilityStatus.UNAVAILABLE:
        return OptionReadiness.UNAVAILABLE
    if not record.authorization_id:
        return OptionReadiness.AVAILABLE_NOT_AUTHORIZED
    return OptionReadiness.AUTHORIZED_NOT_VERIFIED


def _normalize(
    record: _CommunitySlotRecord,
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
    readiness = _readiness_for_record(record, as_of)
    warnings: tuple[str, ...] = ()
    if not record.authorization_id and readiness not in (
        OptionReadiness.STALE,
        OptionReadiness.UNAVAILABLE,
    ):
        warnings = (
            "No Community Care authorization on file. "
            "Scheduler review required before this option can be booked.",
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
        readiness=readiness,
        provenance=provenance,
        provider=record.provider,
        duration_minutes=duration,
        wait_days=record.wait_days,
        drive_minutes=record.drive_minutes,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CommunityAdapter:
    """Synthetic Community Care / EPS availability adapter.

    Parameters
    ----------
    simulate_unavailable:
        When True, returns SOURCE_UNAVAILABLE without reading the fixture.
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
                error_message="Community Care/EPS adapter simulated as unavailable.",
            )

        try:
            if self._fixture_path is not None:
                text = self._fixture_path.read_text(encoding="utf-8")
            else:
                text = _default_fixture_text()
            raw = json.loads(text)
            fixture = _CommunityFixture.model_validate(raw)
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
