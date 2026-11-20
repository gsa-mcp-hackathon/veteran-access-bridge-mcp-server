"""Deterministic workflow gates for the first cardiology vertical slice."""

from __future__ import annotations

from .models import ClinicalConsult, PatientContext, WorkflowState


_APPROVED_SYNTHETIC_CONSULT_SOURCES = {"SYNTHETIC_DEMO_FIXTURE"}


def determine_workflow_state(
    patient: PatientContext,
    consult: ClinicalConsult | None,
) -> WorkflowState:
    """Return the scheduling workflow state without LLM judgment.

    A specialty scheduling search cannot begin without a valid consult for the
    same patient. Clinical context may support explanation, but it never creates
    or substitutes for the consult.
    """
    if consult is None:
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    # Synthetic-only MVP boundary: never advance real or unapproved source
    # records into scheduling search.
    if any(not item.synthetic for item in patient.provenance):
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if consult.source not in _APPROVED_SYNTHETIC_CONSULT_SOURCES:
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if any(not item.synthetic for item in consult.provenance):
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if consult.patient_id != patient.patient_id:
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if consult.specialty.strip().lower() != "cardiology":
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if not consult.valid:
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if consult.blockers:
        return WorkflowState.CONSULT_PENDING

    if not consult.ready_for_search:
        return WorkflowState.CONSULT_PENDING

    return WorkflowState.READY_TO_SEARCH
