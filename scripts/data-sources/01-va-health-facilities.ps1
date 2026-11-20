param([string]$OutputRoot="C:\Users\dsksw\data\external\va_facilities")
$ErrorActionPreference="Stop"
if(-not $env:VA_FACILITIES_API_KEY){throw "Set `$env:VA_FACILITIES_API_KEY first."}
$h=@{apikey=$env:VA_FACILITIES_API_KEY}
$u="https://sandbox-api.va.gov/services/va_facilities/v1/facilities?type=health&page=1&per_page=100"
New-Item -ItemType Directory -Force -Path $OutputRoot|Out-Null
$r=Invoke-RestMethod -Uri $u -Headers $h -Method Get
$r|ConvertTo-Json -Depth 30|Out-File "$OutputRoot\01-vha-health-facilities.json" -Encoding utf8
$r.data|Select-Object @{n="ID";e={$_.id}},@{n="Name";e={$_.attributes.name}},@{n="City";e={$_.attributes.address.physical.city}},@{n="State";e={$_.attributes.address.physical.state}},@{n="Latitude";e={$_.attributes.lat}},@{n="Longitude";e={$_.attributes.long}}|Export-Csv "$OutputRoot\01-vha-health-facilities-summary.csv" -NoTypeInformation
Write-Host "Returned:" $r.data.Count " Total:" $r.meta.pagination.totalEntries
