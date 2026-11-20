# Veteran Access Bridge — PowerShell Data Tests

Set your VA Facilities API key in the current PowerShell session:

```powershell
$env:VA_FACILITIES_API_KEY = "YOUR_KEY"
```

Recommended order:
1. `01-va-health-facilities.ps1`
2. `02-va-facility-services.ps1`
3. `03-va-cardiology-service.ps1`
4. `04-va-nearby-cardiology.ps1`
5. `05-va-facility-ids.ps1`
6. `06-community-care-eligibility-template.ps1` for the Community Care CCG + eligibility search test.

## Community Care CCG test

The Community Care test uses OAuth 2.0 Client Credentials Grant with an RSA private key whose public JWK has been registered with VA sandbox access.

Example:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\data-sources\06-community-care-eligibility-template.ps1" `
  -ClientId "YOUR_CCG_CLIENT_ID" `
  -PatientIcn "YOUR_SYNTHETIC_TEST_ICN" `
  -PrivateKeyPath "C:\Users\dsksw\data\secrets\community-care\private.pem" `
  -ServiceType "Cardiology"
```

The script:
- signs a 5-minute RS256 JWT client assertion using `community-care-ccg-assertion.js`;
- requests a sandbox CCG access token;
- calls `GET /services/community-care/v0/eligibility/search`;
- uses the documented `patient` and `serviceType` query parameters;
- writes both the response and a provenance sidecar.

Outputs save under:
`C:\Users\dsksw\data\external\`

Never commit API keys, OAuth client secrets, access tokens, RSA private keys, sandbox credentials, or real Veteran identifiers.
