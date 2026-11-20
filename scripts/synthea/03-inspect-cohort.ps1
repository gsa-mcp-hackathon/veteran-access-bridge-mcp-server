param(
    [string]$OutputRoot = "C:\Users\dsksw\data\synthetic\synthea\raw"
)

$ErrorActionPreference = "Stop"

$latest = Get-ChildItem $OutputRoot -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latest) {
    throw "No Synthea run found."
}

$patientsFile = Join-Path $latest.FullName "csv\patients.csv"
$conditionsFile = Join-Path $latest.FullName "csv\conditions.csv"
$encountersFile = Join-Path $latest.FullName "csv\encounters.csv"

if (-not (Test-Path $patientsFile)) {
    throw "patients.csv not found: $patientsFile"
}

$patients = Import-Csv $patientsFile

Write-Host ""
Write-Host "Cohort size:" $patients.Count
Write-Host ""
Write-Host "Sample patients:"
$patients |
    Select-Object -First 10 Id,BIRTHDATE,GENDER,RACE,ETHNICITY,STATE,COUNTY,CITY |
    Format-Table -AutoSize

if (Test-Path $conditionsFile) {
    $conditions = Import-Csv $conditionsFile
    Write-Host ""
    Write-Host "Most common conditions:"
    $conditions |
        Group-Object DESCRIPTION |
        Sort-Object Count -Descending |
        Select-Object -First 20 Count,Name |
        Format-Table -AutoSize

    Write-Host ""
    Write-Host "Possible cardiovascular/cardiology-relevant records:"
    $conditions |
        Where-Object {
            $_.DESCRIPTION -match "cardio|heart|coronary|hypertension|atrial|infarct|angina|vascular"
        } |
        Select-Object -First 30 PATIENT,START,STOP,CODE,DESCRIPTION |
        Format-Table -AutoSize
}

if (Test-Path $encountersFile) {
    $encounters = Import-Csv $encountersFile
    Write-Host ""
    Write-Host "Encounter classes:"
    $encounters |
        Group-Object ENCOUNTERCLASS |
        Sort-Object Count -Descending |
        Select-Object Count,Name |
        Format-Table -AutoSize
}
