# Veteran Access Bridge — Seven-Page Zensical Site

**Scope:** Documentation site only. No MCP backend, Supabase, IBM, frontend or production VA services modified. Includes original architecture figure and evidence with date/version caveats. All requests and records are synthetic.

## Local preview (VS Code / PowerShell)

```powershell
git switch docs/github-pages-homepage
python -m pip install -r requirements-docs.txt
zensical build --strict
zensical serve
```

Open http://127.0.0.1:8000/ (or Codespaces forwarded port). If the build fails, run `zensical build --clean` for cache troubleshooting and review errors. Installation/build was not verified in the package-build container, which has no external Python package downloads; **run these commands in your VS Code environment before pushing**.

## Import into current branch

Extract this ZIP to the repository root. **Keep your existing `.gitignore`, backend code and any files not named in the ZIP.** This package replaces the prior `mkdocs.yml`, `requirements-docs.txt`, `.github/workflows/docs-pages.yml` and website docs files. The architecture image supplied in this package is a visual copy of the user's calling-scenario image; it retains the prior concept and is explicitly marked as a historical 21-tool configuration, not the later 29-tool inventory.

```powershell
zensical build --strict
zensical serve
# After inspecting links/images/markdown:
git status
git add docs mkdocs.yml requirements-docs.txt README-PREVIEW.md .github/workflows/docs-pages.yml
git commit -m "Build complete seven-page Zensical documentation site"
git push origin docs/github-pages-homepage
```

No merge to `main` is needed to preview locally; PR builds and `main` deploy are separate in Actions. **No public publication or GitHub edits occurred in the packaging step.**

## 7 pages

1. Home — MCP + Avery hero, challenge, solution, six live navigation cards
2. Solution & Architecture — original user-supplied diagram and dated inventory caveat
3. MCP Implementation — tool counts, contracts and transport
4. Security & Governance — independent trusted enforcement and limitations
5. Evaluation & Results — static interactive checkpoint viewer and methodology reference
6. Demonstration — accepted historical synthetic booking journey, video placeholder
7. Developer Guide — local, VHA sandbox, Supabase/Postgres/RAG, IBM, DeepEval and Phoenix commands

## Evidence and security caveats

- Linked historical backend/frontend sources may be **private**: judges need permission, or scrubbed/public evidence should be migrated to the GSA submission repository before release.
- The screenshot labeled MCP-AgentBench is **third-party methodology inspiration**, not our run.
- The Developer Guide contains optional setup templates explicitly labeled unverified. It does **not** embed a `.env`, secret, key, real Veteran data, synthetic database dump or production booking path.
- No verified deployment of a dedicated RAG MCP tool or Phoenix trace export is claimed.
- Zensical uses `mkdocs.yml` in `classic` mode so the site may be rebuilt with MkDocs Material if needed; Zensical is the selected default builder.
