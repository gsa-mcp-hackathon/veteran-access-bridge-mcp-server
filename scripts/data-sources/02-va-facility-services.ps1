param([string]$FacilityId="vha_402",[string]$OutputRoot="C:\Users\dsksw\data\external\va_facilities")
$ErrorActionPreference="Stop"
if(-not $env:VA_FACILITIES_API_KEY){throw "Set `$env:VA_FACILITIES_API_KEY first."}
$h=@{apikey=$env:VA_FACILITIES_API_KEY}
$u="https://sandbox-api.va.gov/services/va_facilities/v1/facilities/$FacilityId/services?per_page=100"
New-Item -ItemType Directory -Force -Path $OutputRoot|Out-Null
$r=Invoke-RestMethod -Uri $u -Headers $h -Method Get
$r|ConvertTo-Json -Depth 30|Out-File "$OutputRoot\02-$FacilityId-services.json" -Encoding utf8
$r.data|Select-Object @{n="ServiceId";e={$_.serviceInfo.serviceId}},@{n="Name";e={$_.serviceInfo.name}},@{n="NewWaitDays";e={$_.waitTime.new}},@{n="EstablishedWaitDays";e={$_.waitTime.established}},@{n="ReferralRequired";e={$_.serviceLocations[0].referralRequired}},@{n="OnlineScheduling";e={$_.serviceLocations[0].onlineSchedulingAvailable}}|Export-Csv "$OutputRoot\02-$FacilityId-services-summary.csv" -NoTypeInformation
Write-Host "Services:" $r.meta.pagination.totalEntries
