# Solution & Architecture page — corrected image display

Stay on `docs/github-pages-homepage` and extract the `docs/` directory into the repository root. Existing homepage and backend files are untouched. This update contains the Markdown page, the unchanged approved PNG, and a small CSS file.

In `mkdocs.yml`, add `- Solution & Architecture: solution-architecture.md` under `nav:` if absent. Optionally add `- stylesheets/solution-architecture.css` under `extra_css:`. The image uses native Markdown syntax and a path relative to the Markdown page, which MkDocs resolves during site generation.

Run `python -m mkdocs build --strict` and `python -m mkdocs serve`, then open the Solution & Architecture page. The standalone HTML preview contains the image inline so it works without adjacent image files.

Do not merge to `main` until approved. Historical diagram labels were not edited; the later 29/21 tool counts are explained in accompanying text.
