param([string]$OutputRoot="C:\Users\dsksw\data\external\va_facilities")
$ErrorActionPreference="Stop"
if(-not $env:VA_FACILITIES_API_KEY){throw "Set `$env:VA_FACILITIES_API_KEY first."}
$h=@{apikey=$env:VA_FACILITIES_API_KEY}
$u="https://sandbox-api.va.gov/services/va_facilities/v1/ids?type=health"
New-Item -ItemType Directory -Force -Path $OutputRoot|Out-Null
$r=Invoke-RestMethod -Uri $u -Headers $h -Method Get
$r|ConvertTo-Json -Depth 20|Out-File "$OutputRoot\05-vha-health-facility-ids.json" -Encoding utf8
Write-Host "Saved VHA health facility IDs."
