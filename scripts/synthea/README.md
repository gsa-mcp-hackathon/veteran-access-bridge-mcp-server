# Veteran Access Bridge — Synthea Veteran Cohort Pack

This pack generates a reproducible synthetic Veteran cohort for the Veteran Access Bridge project.

## What this produces
- FHIR R4 patient bundles
- VHA CDW-style CSV files
- standard Synthea CSV files
- hospital/practitioner FHIR resources
- provenance metadata documenting seed, geography, Synthea commit, Java version, and run time

## Architecture boundary
Synthea provides synthetic Veteran/patient and clinical-history data.

It is **not** the source for the project's operational scheduling truth. Create the following separately as controlled fixtures:
- ClinicalConsult
- AppointmentRequest
- VistA/ISS Schedule and CareSlot
- Federal EHR Schedule and Slot
- CommunityCareReferral
- Authorization
- EPS-like community provider Slot
- verification and booking state

## Requirements
- Windows PowerShell
- Git
- Java JDK 17 or 25 recommended
- Internet access for the first clone

Check Java:
```powershell
java -version
javac -version
git --version
```

## Generate the first cohort
```powershell
powershell -ExecutionPolicy Bypass -File ".\01-setup-and-generate-synthea.ps1" `
  -State "Kansas" `
  -Population 50 `
  -Seed 20261010
```

Optional city:
```powershell
powershell -ExecutionPolicy Bypass -File ".\01-setup-and-generate-synthea.ps1" `
  -State "Kansas" `
  -City "Topeka" `
  -Population 50 `
  -Seed 20261010
```

The script defaults to:
```text
C:\Users\dsksw\tools\synthea
C:\Users\dsksw\data\synthetic\synthea\raw
```

## Validate the output
```powershell
powershell -ExecutionPolicy Bypass -File ".\02-validate-synthea-output.ps1"
```

## Important
The population seed is fixed by default so the cohort can be regenerated. Keep the generated provenance JSON with the dataset.
