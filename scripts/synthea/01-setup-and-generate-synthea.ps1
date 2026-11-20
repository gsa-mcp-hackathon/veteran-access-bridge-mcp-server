param(
    [Parameter(Mandatory=$true)]
    [string]$State,
    [string]$City = "",
    [ValidateRange(1,10000)]
    [int]$Population = 50,
    [long]$Seed = 20261010,
    [string]$SyntheaRepo = "C:\Users\dsksw\tools\synthea",
    [string]$OutputRoot = "C:\Users\dsksw\data\synthetic\synthea\raw",
    [switch]$SkipBuild,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "Veteran Access Bridge - Synthea Setup"
Write-Host "========================================"

Require-Command "git"
Require-Command "java"
Require-Command "javac"

Write-Host ""
Write-Host "Java:"
java -version 2>&1 | ForEach-Object { Write-Host $_ }

$javaVersionLine = (& java -version 2>&1 | Select-Object -First 1).ToString()
if ($javaVersionLine -match '"(\d+)(?:\.|")') {
    $major = [int]$Matches[1]
    if ($major -lt 17) {
        throw "Synthea requires JDK 17 or newer. Detected: $javaVersionLine"
    }
}

$repoParent = Split-Path -Parent $SyntheaRepo
New-Item -ItemType Directory -Force -Path $repoParent | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

if (-not (Test-Path $SyntheaRepo)) {
    Write-Host ""
    Write-Host "Cloning official Synthea repository..."
    git clone https://github.com/synthetichealth/synthea.git $SyntheaRepo
}
else {
    Write-Host ""
    Write-Host "Synthea repository already exists: $SyntheaRepo"
    Write-Host "Updating the current branch..."
    Push-Location $SyntheaRepo
    try {
        git pull --ff-only
    }
    finally {
        Pop-Location
    }
}

Push-Location $SyntheaRepo
try {
    if (-not $SkipBuild) {
        Write-Host ""
        Write-Host "Building and testing Synthea..."
        & ".\gradlew.bat" build check test
        if ($LASTEXITCODE -ne 0) {
            throw "Synthea build/test failed with exit code $LASTEXITCODE."
        }
    }

    $commit = (git rev-parse HEAD).Trim()
    $generatedAt = (Get-Date).ToUniversalTime().ToString("o")

    $runName = "veterans-$($State.Replace(' ','_'))-$Population-seed-$Seed"
    if ($City) {
        $runName = "veterans-$($State.Replace(' ','_'))-$($City.Replace(' ','_'))-$Population-seed-$Seed"
    }

    $runOutput = Join-Path $OutputRoot $runName

    if (Test-Path $runOutput) {
        if (-not $Overwrite) {
            throw (
                "Run directory already exists and -Overwrite was not specified.`n" +
                "Existing run: $runOutput`n" +
                "To overwrite and lose the existing provenance, re-run with -Overwrite.`n" +
                "To preserve it, choose a different -Seed, -Population, or -City."
            )
        }
        Write-Host ""
        Write-Host "WARNING: -Overwrite specified. Removing existing run directory:"
        Write-Host $runOutput
        Remove-Item -Recurse -Force $runOutput
    }

    New-Item -ItemType Directory -Force -Path $runOutput | Out-Null

    Write-Host ""
    Write-Host "Generating synthetic Veteran cohort..."
    Write-Host "State:      $State"
    if ($City) { Write-Host "City:       $City" }
    Write-Host "Population: $Population"
    Write-Host "Seed:       $Seed"
    Write-Host "Output:     $runOutput"

    $syntheaArgs = @(
        "-s", "$Seed",
        "-p", "$Population",
        "--exporter.baseDirectory=$runOutput",
        "--generate.veteran_population_override=true",
        "--exporter.fhir.export=true",
        "--exporter.fhir.use_us_core_ig=true",
        "--exporter.hospital.fhir.export=true",
        "--exporter.practitioner.fhir.export=true",
        "--exporter.cdw.export=true",
        "--exporter.csv.export=true",
        "--exporter.metadata.export=true",
        "--exporter.fhir.bulk_data=false"
    )

    $syntheaArgs += $State
    if ($City) {
        $syntheaArgs += $City
    }

    & ".\run_synthea.bat" @syntheaArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Synthea generation failed with exit code $LASTEXITCODE."
    }

    $metadataDir = Join-Path $runOutput "vab_metadata"
    New-Item -ItemType Directory -Force -Path $metadataDir | Out-Null

    $provenance = [ordered]@{
        project = "Veteran Access Bridge"
        dataset_role = "synthetic Veteran and clinical-history cohort"
        source = "Synthea"
        repository = "https://github.com/synthetichealth/synthea"
        synthea_commit = $commit
        generated_at_utc = $generatedAt
        state = $State
        city = $(if ($City) { $City } else { $null })
        population_requested = $Population
        random_seed = $Seed
        veteran_population_override = $true
        fhir_r4_enabled = $true
        us_core_enabled = $true
        hospital_fhir_enabled = $true
        practitioner_fhir_enabled = $true
        cdw_export_enabled = $true
        csv_export_enabled = $true
        bulk_fhir_enabled = $false
        java = $javaVersionLine
        operational_scheduling_truth = $false
        note = "Consult, slot, referral, authorization, verification, and booking state must be supplied by separate Veteran Access Bridge fixtures."
    }

    $provenance |
        ConvertTo-Json -Depth 10 |
        Out-File (Join-Path $metadataDir "provenance.json") -Encoding utf8

    Write-Host ""
    Write-Host "Generation complete."
    Write-Host "Synthea commit: $commit"
    Write-Host "Provenance: $(Join-Path $metadataDir 'provenance.json')"
    Write-Host ""
    Write-Host "Top-level output folders/files:"
    Get-ChildItem $runOutput | Format-Table Name, Mode, Length -AutoSize
}
finally {
    Pop-Location
}
