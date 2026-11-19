# Veteran Access Bridge — GitHub Pages homepage

Documentation-only prototype; no application backend or frontend is included.

## Preview locally

```sh
python -m pip install -r requirements-docs.txt
mkdocs serve
```

Open the local address printed by MkDocs (usually http://127.0.0.1:8000/).

## Submit for review

Create a new feature branch in the GSA repository, copy these files to the repository root, push it, and open a draft PR to `main`. The GitHub Actions workflow builds PRs without deployment. It deploys only after a merge to `main` or an explicitly triggered main-branch workflow dispatch.

This is a first-homepage design. Evidence links and supporting technical pages are intentionally deferred until the backend migration.

## Color and typography design

The public design uses the exact web values from the supplied VA Tier 1 Graphic Standards (August 2012), page 18: Navy `#003F72`, Light Blue `#0083BE`, Red `#C4262E`, and Dark Red `#772432`. Secondary Gold `#F3CF45` and Light Gray `#DCDDDE` appear on page 19. Georgia headlines and Calibri body text follow the supplied guide's typography direction. No VA seal, signature, or proprietary font file is included. Veteran Access Bridge is an independent hackathon prototype, not an official VA website.


## Avery orb revision — hollow waveform
The homepage now uses a lightweight SVG rendering of Avery's **hollow lavender waveform ring**, based on the supplied reference image. It is an intentionally decorative, subtly animated illustration with no WebGL, no microphone access, no LiveKit dependency, and no misleading claim of live agent state. The tiny Avery node in the architecture uses a matching hollow ring while the MCP server retains a separate server symbol. Animation respects `prefers-reduced-motion`.

The official frontend still uses LiveKit AgentAudioVisualizerAura, but its code and dependencies are **not** migrated to this backend submission. The SVG illustration is a visual recreation, not the real-time audio-reactive component.
