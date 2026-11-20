param()

$ErrorActionPreference = "Stop"

$required = @("WXO_ENV_NAME", "WXO_INSTANCE_URL", "TOOLKIT_NAME")
foreach ($name in $required) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment variable $name is not set."
    }
}

if (-not (Get-Command orchestrate -ErrorAction SilentlyContinue)) {
    throw "'orchestrate' was not found. Install with: python -m pip install --upgrade ibm-watsonx-orchestrate"
}

if ([string]::IsNullOrWhiteSpace($env:WXO_API_KEY)) {
    $secure = Read-Host "watsonx Orchestrate API key" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:WXO_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$stageDir = Join-Path $scriptDir "_stage"
$generatedToolkit = Join-Path $scriptDir "_toolkit.generated.yaml"
$packageName = "veteran_access_bridge"

try {
    $envList = (& orchestrate env list 2>&1 | Out-String)
    if ($envList -notmatch [regex]::Escape($env:WXO_ENV_NAME)) {
        & orchestrate env add --name $env:WXO_ENV_NAME --url $env:WXO_INSTANCE_URL --type ibm_iam
    }

    & orchestrate env activate $env:WXO_ENV_NAME --api-key $env:WXO_API_KEY

    if (Test-Path $stageDir) {
        Remove-Item $stageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageDir | Out-Null

    Copy-Item (Join-Path $repoRoot "src\$packageName") (Join-Path $stageDir $packageName) -Recurse
    Copy-Item (Join-Path $scriptDir "server.py") (Join-Path $stageDir "server.py")
    Copy-Item (Join-Path $scriptDir "requirements.txt") (Join-Path $stageDir "requirements.txt")

    Get-ChildItem $stageDir -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $toolkitText = Get-Content (Join-Path $scriptDir "toolkit.yaml") -Raw
    $escapedStage = $stageDir.Replace("\", "/")
    $toolkitText = $toolkitText -replace '(?m)^name:.*$', "name: $($env:TOOLKIT_NAME)"
    $toolkitText = $toolkitText -replace '(?m)^package_root:.*$', "package_root: $escapedStage"
    Set-Content -Path $generatedToolkit -Value $toolkitText -Encoding UTF8

    $toolkits = (& orchestrate toolkits list 2>&1 | Out-String)
    if ($toolkits -match [regex]::Escape($env:TOOLKIT_NAME)) {
        & orchestrate toolkits remove --name $env:TOOLKIT_NAME
    }

    & orchestrate toolkits import -f $generatedToolkit
    & orchestrate toolkits list
}
finally {
    if (Test-Path $stageDir) {
        Remove-Item $stageDir -Recurse -Force
    }
    if (Test-Path $generatedToolkit) {
        Remove-Item $generatedToolkit -Force
    }
}
