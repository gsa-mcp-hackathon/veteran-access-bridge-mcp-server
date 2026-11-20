# data/fixtures/demo — Scheduling Fixture Reference Copies

These JSON files are the **human-readable, reviewer-facing copies** of the
deterministic synthetic scheduling fixtures for the Veteran Access Bridge demo case.

## Runtime location

The adapters (`VistAAdapter`, `FederalEHRAdapter`, `CommunityAdapter`) read their
fixtures from the installed package resource:

```
src/veteran_access_bridge/adapters/fixtures/
```

That directory is declared as package data in `pyproject.toml` and is included in
any `pip install` (editable or non-editable).

## Sync contract

Any edit to a fixture file **must be applied to both locations**:

| Location | Purpose |
|---|---|
| `data/fixtures/demo/<file>.json` | Human-readable repository reference |
| `src/veteran_access_bridge/adapters/fixtures/<file>.json` | Installed package resource (runtime) |

A future CI step may enforce sync with a diff check.

## Files

| File | Source system |
|---|---|
| `vista-slots-cardiology.json` | VistA/ISS |
| `federal-ehr-slots-cardiology.json` | Federal EHR / FHIR |
| `community-slots-cardiology.json` | Community Care / EPS |

All records have `"synthetic": true`. Do not add records with `"synthetic": false`.
