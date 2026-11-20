"""Primary Care live-interaction field ownership contract.

This module implements Issue #68. It intentionally lives in the domain layer
as frozen dataclasses/enums, matching the existing architecture decision that
Pydantic is used only at adapter/API validation boundaries.

The contract answers two questions:
1. Which fields may be populated from a Veteran conversation?
2. Which fields must come from governed/deterministic/human-owned sources?

It does not perform scheduling, eligibility, verification, authorization, or
booking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class PrimaryCareFieldName(StrEnum):
    """Canonical live Primary Care workspace fields."""

    REQUEST_SOURCE = "request_source"
    CARE_CATEGORY = "care_category"
    REQUEST_INTENT = "request_intent"

    PROVIDER_REQUESTED_DATE = "provider_requested_date"
    VETERAN_PREFERRED_DATE = "veteran_preferred_date"
    VETERAN_PREFERRED_WINDOW = "veteran_preferred_window"
    VETERAN_PREFERRED_DAYPART = "veteran_preferred_daypart"
    VETERAN_PREFERRED_MODALITY = "veteran_preferred_modality"

    PATIENT_CLASSIFICATION = "patient_classification"
    APPOINTMENT_INTENT = "appointment_intent"

    RAW_AVAILABILITY = "raw_availability"
    ELIGIBLE_OPTIONS = "eligible_options"
    EXCLUDED_OPTIONS = "excluded_options"
    ACCESS_COMPARATOR_DATE = "access_comparator_date"
    ACCESS_STANDARD_RESULT = "access_standard_result"

    VETERAN_SELECTED_OPTION = "veteran_selected_option"
    VERIFICATION_STATUS = "verification_status"
    VETERAN_CONFIRMATION = "veteran_confirmation"
    MSA_APPROVAL = "msa_approval"
    BOOKING_STATUS = "booking_status"


class FieldSource(StrEnum):
    """Source authority for a projected scheduling field."""

    CONVERSATION = "conversation"
    GOVERNED_SOURCE = "governed_source"
    DETERMINISTIC_SERVICE = "deterministic_service"
    VETERAN_ACTION = "veteran_action"
    MSA = "msa"
    APPLICATION = "application"


CONVERSATION_WRITABLE_FIELDS = frozenset(
    {
        PrimaryCareFieldName.REQUEST_SOURCE,
        PrimaryCareFieldName.CARE_CATEGORY,
        PrimaryCareFieldName.REQUEST_INTENT,
        PrimaryCareFieldName.VETERAN_PREFERRED_DATE,
        PrimaryCareFieldName.VETERAN_PREFERRED_WINDOW,
        PrimaryCareFieldName.VETERAN_PREFERRED_DAYPART,
        PrimaryCareFieldName.VETERAN_PREFERRED_MODALITY,
    }
)

GOVERNED_SOURCE_FIELDS = frozenset(
    {
        PrimaryCareFieldName.PROVIDER_REQUESTED_DATE,
        PrimaryCareFieldName.PATIENT_CLASSIFICATION,
        PrimaryCareFieldName.APPOINTMENT_INTENT,
        PrimaryCareFieldName.RAW_AVAILABILITY,
    }
)

DETERMINISTIC_FIELDS = frozenset(
    {
        PrimaryCareFieldName.ELIGIBLE_OPTIONS,
        PrimaryCareFieldName.EXCLUDED_OPTIONS,
        PrimaryCareFieldName.ACCESS_COMPARATOR_DATE,
        PrimaryCareFieldName.ACCESS_STANDARD_RESULT,
        PrimaryCareFieldName.VERIFICATION_STATUS,
        PrimaryCareFieldName.BOOKING_STATUS,
    }
)

VETERAN_ACTION_FIELDS = frozenset(
    {
        PrimaryCareFieldName.VETERAN_SELECTED_OPTION,
        PrimaryCareFieldName.VETERAN_CONFIRMATION,
    }
)

MSA_OWNED_FIELDS = frozenset({PrimaryCareFieldName.MSA_APPROVAL})
MSA_CORRECTABLE_FIELDS = CONVERSATION_WRITABLE_FIELDS


def allowed_sources(field_name: PrimaryCareFieldName) -> frozenset[FieldSource]:
    """Return the source authorities permitted to populate field_name."""

    if field_name in CONVERSATION_WRITABLE_FIELDS:
        return frozenset({FieldSource.CONVERSATION, FieldSource.MSA})
    if field_name in GOVERNED_SOURCE_FIELDS:
        return frozenset({FieldSource.GOVERNED_SOURCE})
    if field_name in DETERMINISTIC_FIELDS:
        return frozenset({FieldSource.DETERMINISTIC_SERVICE})
    if field_name in VETERAN_ACTION_FIELDS:
        return frozenset({FieldSource.VETERAN_ACTION})
    if field_name in MSA_OWNED_FIELDS:
        return frozenset({FieldSource.MSA})
    return frozenset()


@dataclass(frozen=True)
class PrimaryCareFieldValue:
    """One field projection with provenance and correction metadata."""

    field_name: PrimaryCareFieldName
    value: Any
    source: FieldSource
    captured_at: datetime
    synthetic: bool = True
    confidence: float | None = None
    source_record_id: str | None = None
    corrected_from_event_id: str | None = None
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        permitted = allowed_sources(self.field_name)
        if self.source not in permitted:
            allowed = ", ".join(sorted(source.value for source in permitted)) or "none"
            raise ValueError(
                f"{self.field_name.value} cannot be populated from "
                f"{self.source.value}; allowed sources: {allowed}."
            )

        if not self.synthetic:
            raise ValueError("Primary Care live-field MVP values must be synthetic.")

        if self.confidence is not None:
            if self.source is not FieldSource.CONVERSATION:
                raise ValueError(
                    "confidence is only permitted for conversation-derived fields."
                )
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError("confidence must be between 0.0 and 1.0.")

        if self.value is None:
            if not self.unknown_reason or not self.unknown_reason.strip():
                raise ValueError(
                    "Unknown field values require a non-empty unknown_reason."
                )
        elif self.unknown_reason is not None:
            raise ValueError(
                "unknown_reason must be omitted when a field value is present."
            )

        if self.source is FieldSource.GOVERNED_SOURCE and not self.source_record_id:
            raise ValueError(
                "Governed-source fields require source_record_id provenance."
            )

        if self.corrected_from_event_id is not None:
            if self.source is not FieldSource.MSA:
                raise ValueError(
                    "Only MSA corrections may set corrected_from_event_id."
                )
            if self.field_name not in MSA_CORRECTABLE_FIELDS:
                raise ValueError(
                    f"{self.field_name.value} is not MSA-correctable through "
                    "the live field contract."
                )


def field_ownership_summary() -> dict[str, tuple[str, ...]]:
    """Stable machine-readable field-to-source map for API/UI projections."""

    return {
        field_name.value: tuple(
            sorted(source.value for source in allowed_sources(field_name))
        )
        for field_name in PrimaryCareFieldName
    }
