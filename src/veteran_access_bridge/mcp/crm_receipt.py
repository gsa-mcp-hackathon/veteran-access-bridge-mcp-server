"""Minimum-necessary CRM write receipt; never project note or task content."""

from uuid import UUID

WRITE_TOOLS = frozenset(
    {"record_crm_interaction", "create_crm_follow_up", "update_crm_follow_up"}
)


def safe_crm_receipt(value, *, tool, case_id, interaction_id):
    if not isinstance(value, dict) or tool not in WRITE_TOOLS:
        return None
    if (
        value.get("persisted") is not True
        or value.get("synthetic") is not True
        or value.get("booking_created") is not False
        or value.get("operation") != tool
        or value.get("case_id") != case_id
        or value.get("interaction_id") != interaction_id
        or value.get("actor") != "AVERY"
        or type(value.get("version")) is not int
        or value["version"] < 1
        or type(value.get("replayed")) is not bool
    ):
        return None
    try:
        record_id = str(UUID(value["record_id"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    return {
        "persisted": True,
        "synthetic": True,
        "booking_created": False,
        "operation": tool,
        "case_id": case_id,
        "interaction_id": interaction_id,
        "record_id": record_id,
        "version": value["version"],
        "actor": "AVERY",
        "replayed": value["replayed"],
    }
