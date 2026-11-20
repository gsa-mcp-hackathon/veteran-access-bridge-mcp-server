param([string]$FacilityId="vha_402",[string]$OutputRoot="C:\Users\dsksw\data\external\va_facilities")
$ErrorActionPreference="Stop"
if(-not $env:VA_FACILITIES_API_KEY){throw "Set `$env:VA_FACILITIES_API_KEY first."}
$h=@{apikey=$env:VA_FACILITIES_API_KEY}
$u="https://sandbox-api.va.gov/services/va_facilities/v1/facilities/$FacilityId/services/cardiology"
New-Item -ItemType Directory -Force -Path $OutputRoot|Out-Null
$r=Invoke-RestMethod -Uri $u -Headers $h -Method Get
$r|ConvertTo-Json -Depth 30|Out-File "$OutputRoot\03-$FacilityId-cardiology.json" -Encoding utf8
$r|ConvertTo-Json -Depth 12
