param(
    [string]$OutputRoot = "C:\Users\dsksw\data\synthetic\synthea\raw"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $OutputRoot)) {
    throw "Output root does not exist: $OutputRoot"
}

$latest = Get-ChildItem $OutputRoot -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latest) {
    throw "No Synthea run directory found under $OutputRoot"
}

$run = $latest.FullName

Write-Host ""
Write-Host "Validating latest run:"
Write-Host $run
Write-Host ""

$expected = @("fhir","csv","cdw","vab_metadata")
foreach ($folder in $expected) {
    $path = Join-Path $run $folder
    if (Test-Path $path) {
        Write-Host "[OK] $folder"
    } else {
        Write-Warning "[MISSING] $folder"
    }
}

$fhirPath = Join-Path $run "fhir"
if (Test-Path $fhirPath) {
    $patientFiles = Get-ChildItem $fhirPath -Filter "*.json" -File -ErrorAction SilentlyContinue
    Write-Host "FHIR JSON files:" $patientFiles.Count
}

$csvPath = Join-Path $run "csv"
if (Test-Path $csvPath) {
    $patientsCsv = Join-Path $csvPath "patients.csv"
    if (Test-Path $patientsCsv) {
        $patientRows = (Import-Csv $patientsCsv).Count
        Write-Host "CSV patient rows:" $patientRows
    }
}

$cdwPath = Join-Path $run "cdw"
if (Test-Path $cdwPath) {
    $cdwFiles = Get-ChildItem $cdwPath -File -Recurse
    Write-Host "CDW files:" $cdwFiles.Count
    $cdwFiles |
        Select-Object -First 20 Name,Length |
        Format-Table -AutoSize
}

$prov = Join-Path $run "vab_metadata\provenance.json"
if (Test-Path $prov) {
    Write-Host ""
    Write-Host "Provenance:"
    Get-Content $prov -Raw
}

Write-Host ""
Write-Host "Validation complete."
