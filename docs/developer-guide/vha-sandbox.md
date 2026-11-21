# VHA Lighthouse sandbox

The [VA Developer portal](https://developer.va.gov/) provides published VA API specifications, sandbox-access forms and authorization guidance. **Sandbox credentials are API-specific**; a Facilities API key is different from a patient-health OAuth client. Sandbox access is not production VA system authority.

**Access process:**

1. Select the required API and read its **Sandbox access**, **Authentication**, OpenAPI and sample data documentation at [developer.va.gov](https://developer.va.gov/).
2. Request the applicable sandbox key/client ID through the API's sandbox form. For OAuth Client Credentials Grant (CCG), follow the **API-specific** JWK/public-key registration and sandbox JWT rules; for OAuth authorization-code APIs use the supplied test-user/consent flow.
3. Store the private key, API key and client secret **outside this repository**, in your approved credential manager or local ignored environment.
4. Confirm the permitted sandbox endpoint/paths from the selected API's **current OpenAPI specification**. Do not substitute arbitrary URL paths, production endpoints or live Veteran identifiers.
5. Validate one sandbox read and an expected denied/missing-credential case; record HTTP status, run date and sanitized response, **never** bearer/JWT secrets.

### PowerShell verification templates

```powershell
# Example A: API-key sandbox read, only for an API documented to use x-api-key
$env:VHA_SANDBOX_KEY = '<read from approved local secret store>'
$env:VHA_SANDBOX_TEST_URL = 'https://<documented-sandbox-host>/<documented-read-path>'
Invoke-RestMethod -Uri $env:VHA_SANDBOX_TEST_URL -Headers @{ 'apiKey'=$env:VHA_SANDBOX_KEY } -Method Get

# Example B: OAuth sandbox read, after completing API-specific token grant
$env:VHA_SANDBOX_ACCESS_TOKEN = '<authorized short-lived sandbox token>'
Invoke-WebRequest -Uri $env:VHA_SANDBOX_TEST_URL -Headers @{ Authorization="Bearer $env:VHA_SANDBOX_ACCESS_TOKEN" } -Method Get
```

!!! note "Header varies by API"
    The API-key header above is an *illustrative placeholder* and **must be replaced with the header or query parameter in that API's OpenAPI docs**. Do not execute templates with invented hosts or assume both grant flows apply. Keep JWT/private-key creation under the API's documented secure process. Earlier project notes say VA CCG OAuth/eligibility returned HTTP 200; that is historical user verification, **not a fresh probe for this site**.

**Project integration:** Configure read adapters only for approved sandbox APIs. No VistA, HSRM or EPS production booking is demonstrated. Reference: [VA API onboarding](https://developer.va.gov/onboarding/working-with-lighthouse-apis) · [VA sandbox access guide](https://developer.va.gov/explore/api/va-facilities/sandbox-access) · [OAuth authorization docs](https://developer.va.gov/explore/verification/docs/authorization).

---

[Previous: Prepare Supabase](supabase.md) · [Next: Set up IBM Cloud and Code Engine](avery-ibm-start.md)
