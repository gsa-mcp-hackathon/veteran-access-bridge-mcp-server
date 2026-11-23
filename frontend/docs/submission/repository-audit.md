# Frontend repository cleanup review

November 15, 2026. Audited clean baseline `da2c6f3` on `docs/gsa-submission-alignment-20261114`: 183 tracked files. This cleanup updates documentation; no application code, dependencies, deployment or credentials change. The backend audit records its separate inventory.

## Keep

| Priority | Paths | Reason |
|---|---|---|
| P0 | `src/`, `public/` | Current Call in Browser, reviewer gate, server gateways and UI assets |
| P0 | `package.json`, `bun.lock`, `Dockerfile`, configuration files | Reproducible frontend build and CI contracts |
| P0 | `.github/`, `scripts/`, `src/test/` | Active lint/type/test/build and actual-container smoke checks |
| P1 | `.lovable/`, `AGENTS.md` | Connected design workflow and contribution boundaries |
| P1 | `docs/design/`, `docs/plans/`, `roadmap.md` | Earlier design context, labeled historical where appropriate |
| P1 | Earlier acceptance and deployment procedures | Preserve versions and outcome boundaries; link current inventory prominently |

`node_modules`, `.output`, `.tanstack` and `.wrangler` have no tracked matches and are ignored. No repository deletion is warranted for these local generated directories.

## Archive proposal awaiting confirmation

| Current path | Proposed path | Reason |
|---|---|---|
| `final-1440.png` | `docs/design/screenshots/final-1440.png` | Earlier layout capture, unrelated to runtime |
| `final-1648.png` | `docs/design/screenshots/final-1648.png` | Earlier layout capture, unrelated to runtime |
| `final-390.png` | `docs/design/screenshots/final-390.png` | Earlier mobile layout capture, unrelated to runtime |

Total size: 420,351 bytes. A tracked-text reference search before the new documentation index found no filename consumers. These are preserved-image moves, not deletions. If approved, retain identical bytes, update the documentation index and add a screenshot index identifying them as historical layout evidence. No move has been performed in this follow-up.

## Updates completed

- Root README leads with the MCP submission, reviewer login, presentation, evaluation and code map.
- Current frontend source/revision is `f5ae071` / `00019`; superseded README image pins are removed in favor of the deployment inventory.
- New docs index distinguishes current instructions, design history and earlier acceptance snapshots.
- The root roadmap's old blocked state is labeled historical rather than a current live-call failure.
- Caller script now includes private reviewer login before screen recording, matching the backend source.

## Retained boundaries

The `/demo-call` IBM embed is a separate legacy route. Do not remove it, its configuration or tests without a code/reference review. Call in Browser remains the reviewer path. The Lovable preview is a design surface rather than verified deployment evidence. No global URL replacement, new publication, cleanup script execution or branch merge is part of this documentation pass.
