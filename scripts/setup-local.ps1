$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12+ is required and was not found on PATH."
}

$VersionText = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$Parts = $VersionText.Split(".")
if ([int]$Parts[0] -lt 3 -or ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -lt 12)) {
    throw "Python 3.12+ is required. Found $VersionText."
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Pip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"

Write-Host "Upgrading pip..."
& $Python -m pip install --upgrade pip

Write-Host "Installing Veteran Access Bridge + dev dependencies..."
& $Pip install -e ".[dev]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example."
} else {
    Write-Host ".env already exists; leaving it unchanged."
}

Write-Host "Verifying import..."
& $Python -c "import veteran_access_bridge; print('Veteran Access Bridge import OK')"

Write-Host ""
Write-Host "Setup complete."
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
Write-Host "Run tests with: pytest"
Write-Host "Start the demo with: veteran-access-demo"
