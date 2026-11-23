<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.
<!-- LOVABLE:END -->

## Prototype architecture
- Keep scripted replay as the default; the only server code is the fail-closed sandbox gateway `/api/msa-monitor`, which proxies two fixed canonical monitor endpoints with server-only keys; the canonical system owns identity, scheduling, MCP and audio.
- Keep authoritative monitor projection pure (`src/lib/live-monitor.ts`) and never mix fixture state into authoritative mode; this prevents cross-case leakage and fabricated bookings.
- Use modular MSA shell/header/queue/conversation/replay modules while preserving existing workspace exports; this separates presentation from fixture state without replacing scheduling contracts.
- Use semantic global tokens and Radix sheet overlays for all shell drawers; this preserves theming and keyboard/focus behavior across viewport sizes.

- Keep handoff ownership/media/verification/channel in a separate pure reducer and project a safe context on every failed-verification view; this prevents appointment approval, acceptance and media join from sharing authorization state.
- Keep appointment replay state above scenario composition remounts and derive historical handoff turns from append-only fixture events; this preserves completed queue projections and transcript history across scenario/media changes.
- Project routine booking only through validated replay prerequisites, keeping exception authorization separate; this prevents routine automation from bypassing identity, eligibility or confirmation.
- Derive per-encounter artifact phases from replay events with separate in-memory save/delivery acknowledgements, and keep the staff copilot browser-only and deterministic; this avoids implying external AI, document delivery or record persistence.
- Keep LiveKit Agents UI files under src/components/agents-ui and src/hooks/agents-ui as verbatim registry copies (ts-nocheck/eslint-disable header only) and load them client-only via lazy import; WebGL shaders break SSR and edits would diverge from upstream.
- Derive MCP execution steps for both the conversation cards and the inspector from one pure projection (`src/lib/mcp-execution.ts`), with an allowlisted tool registry; this prevents duplicate pipelines and fabricated categories, statuses or dataset calls.
- One-click demo auth lives in `src/lib/one-click-gate.ts` (opt-in + loopback backend + Host/Origin allowlist, operator-code fallback); never authorize from browser-supplied credentials or broaden origins.
