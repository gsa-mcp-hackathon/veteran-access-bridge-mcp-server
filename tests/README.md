# Run the backend checks

From the repository root, run `uv sync --locked --group dev`, then `uv run --no-sync pytest -q tests`. To run just one suite, append its file path in place of `tests`. These checks use local test data.

| What you want to verify | Test source |
| --- | --- |
| Primary Care scheduling scenarios | [Scheduling scenarios](test_m6_2_primary_care_scenarios.py) |
| Which scheduling fields are returned | [Field contract](test_primary_care_field_contract.py) |
| Consent for a synthetic Veteran | [Consent checks](test_synthetic_veteran_consent.py) |
| Which requests may create a booking | [Private booking endpoint](test_private_primary_care_booking.py) and [trusted booking checks](test_trusted_primary_care.py) |
| What gets recorded after booking and which receipts are accepted | [CRM booking](test_booking_crm.py) and [CRM receipt validation](test_crm_receipt.py) |

[Read the recorded results and inspect the evidence files](../docs/evaluation/reviewer-index.md).
