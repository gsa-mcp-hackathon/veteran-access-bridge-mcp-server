<#
.SYNOPSIS
    Remove obsolete Veteran Access Bridge remote MCP toolkit registrations from
    watsonx Orchestrate while preserving the active M6.3 toolkit and local rollback toolkit.

.DESCRIPTION
    Safe cleanup for the post-M6.3 evaluation checkpoint.

    Removes only:
      - veteran-access-mcp-remote-m61
      - veteran-access-mcp-remote

    Preserves:
      - veteran-access-mcp-remote-m63  (active)
      - veteran-access-mcp             (local development / rollback)
      - all unrelated toolkits

    By default this script is DRY-RUN only. Use -DryRun $false to execute.
#>

param(
    [bool] $DryRun = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command orchestrate -ErrorAction SilentlyContinue)) {
    throw "'orchestrate' was not found. Install or upgrade with: python -m pip install --upgrade ibm-watsonx-orchestrate"
}

$ActiveToolkit = "veteran-access-mcp-remote-m63"
$LocalRollbackToolkit = "veteran-access-mcp"
$ObsoleteToolkits = @(
    "veteran-access-mcp-remote-m61",
    "veteran-access-mcp-remote"
)

function Get-ToolkitNamesFromTable {
    param(
        [Parameter(Mandatory = $true)]
        [string] $TableText
    )

    $names = New-Object System.Collections.Generic.List[string]
    $currentName = ""

    foreach ($line in ($TableText -split "\r?\n")) {
        if ($line -match '^\|[-+]+\|$') {
            if (-not [string]::IsNullOrWhiteSpace($currentName)) {
                $names.Add($currentName.Trim())
                $currentName = ""
            }
            continue
        }

        if ($line -match '^\|\s*(.*?)\s*\|') {
            $segment = $matches[1].Trim()

            if ($segment -eq "Name") {
                continue
            }

            if (-not [string]::IsNullOrWhiteSpace($segment)) {
                $currentName += $segment
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($currentName)) {
        $names.Add($currentName.Trim())
    }

    return $names
}

Write-Host ""
Write-Host "Veteran Access Bridge - Orchestrate Toolkit Cleanup" -ForegroundColor Yellow
Write-Host "  DryRun        : $DryRun"
Write-Host "  Active toolkit: $ActiveToolkit"
Write-Host "  Preserve local: $LocalRollbackToolkit"
Write-Host ""

$toolkits = (& orchestrate toolkits list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list Orchestrate toolkits. Refresh the environment token if needed."
}

Write-Host "Current toolkits:" -ForegroundColor Cyan
Write-Host $toolkits

$toolkitNames = @(Get-ToolkitNamesFromTable -TableText $toolkits)

Write-Host "Parsed toolkit names:" -ForegroundColor Cyan
$toolkitNames | ForEach-Object { Write-Host "  - $_" }

if ($toolkitNames -notcontains $ActiveToolkit) {
    throw "Active M6.3 toolkit '$ActiveToolkit' was not found. Refusing cleanup."
}

foreach ($name in $ObsoleteToolkits) {
    if ($toolkitNames -contains $name) {
        if ($DryRun) {
            Write-Host "[DRY RUN] Would remove obsolete toolkit: $name" -ForegroundColor Magenta
            Write-Host "          orchestrate toolkits remove --name $name" -ForegroundColor Gray
        }
        else {
            Write-Host "Removing obsolete toolkit: $name" -ForegroundColor Cyan
            & orchestrate toolkits remove --name $name
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to remove obsolete toolkit '$name'."
            }
        }
    }
    else {
        Write-Host "Already absent: $name" -ForegroundColor DarkGray
    }
}

if (-not $DryRun) {
    Write-Host ""
    Write-Host "Verifying toolkit inventory after cleanup..." -ForegroundColor Cyan

    $after = (& orchestrate toolkits list 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to verify Orchestrate toolkits after cleanup."
    }

    $afterNames = @(Get-ToolkitNamesFromTable -TableText $after)

    if ($afterNames -notcontains $ActiveToolkit) {
        throw "Active M6.3 toolkit disappeared after cleanup. Stop and investigate."
    }

    foreach ($name in $ObsoleteToolkits) {
        if ($afterNames -contains $name) {
            throw "Obsolete toolkit '$name' is still present after cleanup."
        }
    }

    Write-Host $after
    Write-Host "Cleanup complete. Active M6.3 toolkit preserved." -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "Dry run complete. No Orchestrate resources were changed." -ForegroundColor Green
}
