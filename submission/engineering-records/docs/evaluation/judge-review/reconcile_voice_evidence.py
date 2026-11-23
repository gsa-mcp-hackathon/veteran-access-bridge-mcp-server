"""Reconcile the retained synthetic voice traces with the separately dated SQL audit."""
from pathlib import Path
import csv
import json

folder = Path(__file__).resolve().parent
archive = folder.parent / "evidence" / "release-closeout-20261115"
trial = json.loads((folder.parent / "dynamic-sandbox-callers-20261116.json").read_text())
sessions = {item["attempt"]: item["voice_session_id"] for item in trial["attempts"]}
sql_by_session = {
    sessions[row["attempt"]]: row for row in trial["database"]["calls"]
    if row.get("case_id")
}
rows = []
for kind in ("authority", "secrets", "cross-case"):
    record = json.loads((archive / f"v11-{kind}-verification.json").read_text())
    session = record["voice_session_id"]
    for event in record["attack_intervals"]:
        rows.append([event["scenario"], session, event["mcp_attempts"],
                     record["benign_followup"], session in sql_by_session])
with (folder / "voice-evidence-reconciliation.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["Scenario", "Voice session", "MCP attempts during interval",
                     "Permitted follow-up in same session", "Same session in Nov 16 SQL audit"])
    writer.writerows(rows)
print(f"{len(rows)} intervals across {len(set(row[1] for row in rows))} sessions")
print(f"{sum(row[-1] for row in rows)} intervals matched to the Nov 16 audit")
print(f"{len(sql_by_session)} provisioned calls in separate audit")
