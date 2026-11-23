# Caller experience release checks — November 15, 2026

Status: deployment and browser expiry verified; revised agent follow-up acceptance
is in progress. This is not a declaration that the complete evaluation passed.

## Release pins

- Backend source/image: `1e4b26c24643bfbe9ba57c4b1d367b468c58144f`,
  existing `veteran-access-bridge-m64-canary`, revision `00028`.
- Frontend source/image: `92cd0569063b8ff1d5d205a04648146fcc3e292d`,
  existing `vab-avery-callcenter`, revision `00018`.
- Both services report ready and 100% traffic on the new revision. Their
  environment-variable maps match the pre-deployment backups. Worker unchanged.
- Agent instruction v10 imported and read back; v11 subsequently imported after
  the failed follow-up below. V11 export differs only in trailing instruction
  whitespace; every other exported field matches its input. No added tools,
  permissions, identity bypass, or new server.

## Build and automated evidence

| Check | Result | Evidence |
|---|---|---|
| Full backend suite | 1,337 passed; 19 skipped; 11 warnings | [Backend CI](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/ci/ci-run-43741985816.md) |
| Focused voice checks | 81 passed | Private test log |
| Frontend suite | 132 passed across 19 files | Local run; CI |
| Frontend deployment packaging | Passed | Packaging |
| Backend image publication | Passed | [Image build](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/ci/ci-run-43742315209.md) |
| Frontend image publication | Passed | Image build |

Skipped tests are not passes. Automated counts are not attack counts or proof of
production readiness.

## Browser expiry — observed PASS

An actual Call in Browser session connected to Avery, was muted, and remained
open to its server-owned five-minute deadline. The 30-second warning appeared;
the call then disconnected, the observer disconnected, and Call in Browser
returned with the completed-expiry notice. No end-call error appeared. No
identity verification, protected read, or booking occurred in this idle test.

The five-minute authorization limit remains unchanged. A one-minute grace
period permits only teardown of the already-bound call; it does not renew
activity access or permit a new call. Unit tests cover foreign-call denial,
expired activity denial, teardown replay denial, and grace-period expiry.

!Observed browser expiry, not a booking receipt

## V10 read trial — retained FAIL

Voice `vs-7bc981d9-4af6-4184-b058-cbe5b10253f1`, interaction
`int-cb841a6d55784057`, 217.37 seconds; end acknowledged successfully.

IBM selected successful identity verification and an initial encounter read.
On the follow-up, IBM attempted identity verification again despite receiving
the server-owned verified flag as `true`. The scope gate denied this operation.
The caller heard an identity/scope refusal; the test stopped without guessing
another identity. No booking was requested.

Native trace `2739f873da3740dfc69a05e526b7ed86` contains the first two calls;
`376aeb389c9d4e6cf337f5e1cc117dfc` contains the denied repeat. The failure is a
tool-selection problem, not evidence that the server allowed an unauthorized
operation. The first answer also exceeded the requested 60-word length.

V11 clarifies that historical name/date utterances must not restart intake,
and that the current verified flag controls follow-up selection. Its live
acceptance subsequently passed: one identity verification and two IBM-selected,
server-authorized reads, including the follow-up. See the
[current release report](release-closeout-20261115.md) for trace IDs, model
scoring, adversarial controls and remaining limitations. The v10 failure above
remains part of the evidence.

## Spoken wording boundary

The backend replaces a bounded set of unsupported first-person transfer claims
with a supported staff-contact instruction. It preserves the original IBM
event and labels any replacement as application-owned. This is a delivery
guard, not a universal language guarantee or an agent-quality score. The v10
live answer contained no unsupported transfer offer.

Raw service exports and trace credentials remain private under
`eval/results/release-closeout-20261115/`; do not publish that directory.
