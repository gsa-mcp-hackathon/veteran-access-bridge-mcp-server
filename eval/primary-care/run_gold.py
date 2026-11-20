"""Compare fresh MCP responses with the recorded Primary Care answer key."""

import asyncio
import csv
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def fields(data, *paths):
    result = []
    for path in paths:
        value = data
        for key in path.split("."):
            value = value[key]
        result.append(value)
    return result


def excluded_slot(data):
    slot = next(row for row in data["slot_eligibility"] if row["slot_id"] == "VISTA-SLOT-PC-5000999-002")
    return [slot["eligible"], sorted(slot["reasons"])]


# Preserve the field selection and error classifications used for the recorded matrix.
PROJECTIONS = {
    "1": lambda d: fields(d, "patient_classification"),
    "2": lambda d: fields(d, "request.care_category", "request.appointment_intent"),
    "3": lambda d: fields(d, "request.required_modality", "request.required_duration_minutes"),
    "4": lambda d: fields(d, "request.canonical_pid"),
    "5": lambda d: [len(d["slots"]), len(d["eligible_options"])],
    "6": excluded_slot,
    "7": lambda d: fields(d, "access_standard.earliest_eligible_va_option_id", "access_standard.earliest_eligible_va_wait_days"),
    "8": lambda d: fields(d, "preferences_create_eligibility"),
    "9": lambda d: fields(d, "read_only", "booking_created"),
    "10": lambda d: fields(d, "access_standard.earliest_eligible_va_wait_days", "access_standard.standard_days", "access_standard.wait_standard_exceeded"),
    "11": lambda d: fields(d, "access_standard.community_care_review_recommended", "access_standard.community_care_authorization_status", "community_care_authorization_granted", "eps_invoked"),
    "13": lambda d: fields(d, "verified"),
    "14": lambda d: fields(d, "verified"),
}


async def observe(session, row):
    question = row["ID"]
    args = {"case_id": row["Fixture case"]}
    if question in ("13", "14"):
        args.update(full_name="Synthetic Primary Care Veteran", birth_date={"13": "1980-01-01", "14": "1980-01-02"}[question])
    reply = await session.call_tool(row["MCP tool"], args)
    if reply.isError:
        detail = " ".join(part.text for part in reply.content if part.type == "text")
        if not reply.structuredContent:
            if "Unknown synthetic case_id" in detail:
                return "UNKNOWN_CASE"
            if "has no specialty consult" in detail and "use get_scheduling_encounter" in detail:
                return "ROUTE_TO_ENCOUNTER"
        return "UNEXPECTED_ERROR"
    if question not in PROJECTIONS:
        return "UNEXPECTED_SUCCESS"
    data = reply.structuredContent or json.loads(reply.content[0].text)
    return PROJECTIONS[question](data)


async def main():
    with Path(__file__).with_name("questions.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if [row["ID"] for row in rows] != [str(i) for i in range(1, 17)]:
        raise ValueError("Expected all 16 gold questions in ID order")
    params = StdioServerParameters(command=sys.executable, args=["-m", "veteran_access_bridge.mcp.app"], env={"VAB_MCP_TRANSPORT": "stdio"})
    passed = 0
    async with stdio_client(params) as streams, ClientSession(*streams) as session:
        await session.initialize()
        for row in rows:
            observed = await observe(session, row)
            expected = json.loads(row["Expected"])
            matches = json.dumps(observed) == json.dumps(expected)
            passed += matches
            print(f"{'PASS' if matches else 'FAIL'} Q{row['ID']} {row['MCP tool']} | {row['Gold question']}")
            if not matches:
                print(f"  expected {expected!r}, observed {observed!r}")
    print(f"{passed}/{len(rows)} gold answers matched")
    return int(passed != len(rows))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
