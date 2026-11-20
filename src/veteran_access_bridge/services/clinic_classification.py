"""Clinic-context New/Established classification for M6.2b."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime

from veteran_access_bridge.domain.models import (
    PatientClinicClassification,
    PatientClinicRelationship,
)


def _subtract_years(value: datetime, years: int) -> datetime:
    """Return value shifted back by whole calendar years.

    February 29 is clamped to February 28 when the target year is not leap.
    """
    target_year = value.year - years
    target_day = min(value.day, monthrange(target_year, value.month)[1])
    return value.replace(year=target_year, day=target_day)


def classify_patient_clinic_relationship(
    relationship: PatientClinicRelationship,
) -> PatientClinicClassification:
    """Classify a synthetic patient as NEW, ESTABLISHED, or UNKNOWN.

    Rules:
    - clinic context must contain a stop_code or stop_code_group;
      otherwise classification fails closed to UNKNOWN.
    - a future last_completed_visit is inconsistent evidence and returns UNKNOWN.
    - a qualifying completed visit on or after the 36-month lookback boundary
      is ESTABLISHED.
    - no completed visit, or a completed visit older than 36 months, is NEW.

    This function does not infer stop-code equivalence. The relationship input
    must already represent the same clinic specialty stop code or an approved
    stop-code grouping.
    """
    has_clinic_context = bool(
        (relationship.stop_code and relationship.stop_code.strip())
        or (relationship.stop_code_group and relationship.stop_code_group.strip())
    )
    if not has_clinic_context:
        return PatientClinicClassification.UNKNOWN

    last_visit = relationship.last_completed_visit
    if last_visit is None:
        return PatientClinicClassification.NEW

    if last_visit > relationship.as_of:
        return PatientClinicClassification.UNKNOWN

    lookback_boundary = _subtract_years(relationship.as_of, 3)
    if last_visit >= lookback_boundary:
        return PatientClinicClassification.ESTABLISHED

    return PatientClinicClassification.NEW
