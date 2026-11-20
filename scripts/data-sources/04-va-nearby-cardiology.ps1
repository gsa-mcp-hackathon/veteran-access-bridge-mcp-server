param(
 [Parameter(Mandatory=$true)][double]$Latitude,
 [Parameter(Mandatory=$true)][double]$Longitude,
 [ValidateSet(10,20,30,40,50,60,70,80,90)][int]$DriveTime=60,
 [string]$OutputRoot="C:\Users\dsksw\data\external\va_facilities"
)
$ErrorActionPreference="Stop"
if(-not $env:VA_FACILITIES_API_KEY){throw "Set `$env:VA_FACILITIES_API_KEY first."}
$h=@{apikey=$env:VA_FACILITIES_API_KEY}
$u="https://sandbox-api.va.gov/services/va_facilities/v1/nearby?lat=$Latitude&long=$Longitude&drive_time=$DriveTime&services%5B%5D=cardiology&per_page=100"
New-Item -ItemType Directory -Force -Path $OutputRoot|Out-Null
$r=Invoke-RestMethod -Uri $u -Headers $h -Method Get
$r|ConvertTo-Json -Depth 30|Out-File "$OutputRoot\04-nearby-cardiology.json" -Encoding utf8
$r|ConvertTo-Json -Depth 12
