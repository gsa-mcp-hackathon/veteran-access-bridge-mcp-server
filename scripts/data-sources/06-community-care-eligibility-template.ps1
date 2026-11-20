param(
    [Parameter(Mandatory=$true)][string]$ClientId,
    [Parameter(Mandatory=$true)][string]$PatientIcn,
    [Parameter(Mandatory=$true)][string]$PrivateKeyPath,
    [ValidateSet("Audiology","Cardiology","Dermatology","Gastroenterology","Gynecology","MentalHealthCare","Nutrition","Ophthalmology","Optometry","Orthopedics","Podiatry","PrimaryCare","Urology","WomensHealth")]
    [string]$ServiceType = "Cardiology",
    [ValidateRange(31,90)][int]$ExtendedDriveMin,
    [string]$OutputRoot = "C:\Users\dsksw\data\external\community_care_eligibility"
)

$ErrorActionPreference = "Stop"

# Synthetic-only safety boundary for the hackathon prototype.
# Never send an arbitrary ICN to the Community Care sandbox and then label
# the resulting payload synthetic. Add new sandbox identities here only after
# they have been explicitly verified as VA sandbox test patients.
$AllowedSyntheticPatientIcns = @(
    "5000335"
)

if ($PatientIcn -notin $AllowedSyntheticPatientIcns) {
    throw "PatientIcn is not an approved synthetic sandbox test identity. Refusing request."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jwtHelper = Join-Path $scriptDir "community-care-ccg-assertion.js"

if (-not (Test-Path $PrivateKeyPath)) {
    throw "Private key not found: $PrivateKeyPath"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required to generate the signed CCG client assertion."
}

if (-not (Test-Path $jwtHelper)) {
    throw "JWT helper not found: $jwtHelper"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$audience = "https://deptva-eval.okta.com/oauth2/aushf3qmfhav6es262p7/v1/token"
$tokenEndpoint = "https://sandbox-api.va.gov/oauth2/community-care/system/v1/token"
$eligibilityEndpoint = "https://sandbox-api.va.gov/services/community-care/v0/eligibility/search"
$scope = "launch patient/CommunityCareEligibility.read"

$assertionJson = & node $jwtHelper $ClientId $PrivateKeyPath $audience
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate CCG client assertion."
}
$assertion = $assertionJson | ConvertFrom-Json

$launchJson = @{ patient = $PatientIcn } | ConvertTo-Json -Compress
$launch = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($launchJson))

$tokenJson = & curl.exe -sS `
    -X POST `
    $tokenEndpoint `
    -H "Accept: application/json" `
    -H "Content-Type: application/x-www-form-urlencoded" `
    --data-urlencode "grant_type=client_credentials" `
    --data-urlencode "client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer" `
    --data-urlencode "client_assertion=$($assertion.clientAssertion)" `
    --data-urlencode "scope=$scope" `
    --data-urlencode "launch=$launch"

$tokenResponse = $tokenJson | ConvertFrom-Json
if (-not $tokenResponse.access_token) {
    $err = $tokenResponse.error
    $desc = $tokenResponse.error_description
    throw "Community Care CCG token request failed. Error=$err Description=$desc"
}

$headers = @{
    Authorization = "Bearer $($tokenResponse.access_token)"
    Accept = "application/json"
}

$uri = "${eligibilityEndpoint}?patient=$([uri]::EscapeDataString($PatientIcn))&serviceType=$([uri]::EscapeDataString($ServiceType))"
if ($PSBoundParameters.ContainsKey("ExtendedDriveMin")) {
    $uri += "&extendedDriveMin=$ExtendedDriveMin"
}

$response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get

$responsePath = Join-Path $OutputRoot "06-community-care-eligibility.json"
$response | ConvertTo-Json -Depth 30 | Out-File $responsePath -Encoding utf8

$provenance = [ordered]@{
    source = "VA Community Care Eligibility API"
    environment = "sandbox"
    authorization_model = "OAuth 2.0 Client Credentials Grant"
    token_endpoint = $tokenEndpoint
    eligibility_endpoint = $eligibilityEndpoint
    service_type = $ServiceType
    synthetic_test_patient = $true
    retrieved_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    response_file = $responsePath
}
$provenancePath = Join-Path $OutputRoot "06-community-care-eligibility-provenance.json"
$provenance | ConvertTo-Json -Depth 10 | Out-File $provenancePath -Encoding utf8

Write-Host "SUCCESS: Community Care eligibility response saved."
Write-Host "Response: $responsePath"
Write-Host "Provenance: $provenancePath"
$response | ConvertTo-Json -Depth 12
