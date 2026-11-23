import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Aura, Chip, VOICE_META, SLOT_UI } from "@/components/workspace";
import type { VoiceState, SlotStatus } from "@/lib/scenario";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/design-system")({
  head: () => ({
    meta: [
      { title: "Veteran Access Bridge · MSA Operations Design Foundation" },
      {
        name: "description",
        content:
          "Official VA palette, accessible operations shell and synthetic conversation design checkpoint.",
      },
      { property: "og:title", content: "Veteran Access Bridge · MSA Operations Design Foundation" },
      {
        property: "og:description",
        content:
          "Phase 1 MSA design tokens, conversation contrast, voice states and frontend boundaries.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: DesignSystem,
});
const tokens = [
  ["primary", "#005ea2", "Interactive actions"],
  ["primary-dark", "#1a4480", "Avery identity"],
  ["primary-darker", "#162e51", "Operations header"],
  ["primary-lighter", "#d9e8f6", "Selected encounter"],
  ["primary-alt", "#00bde3", "Dark-canvas highlights"],
  ["primary-alt-darkest", "#07648d", "Information on light"],
  ["text", "#1b1b1b", "Default text"],
  ["base-dark", "#565c65", "AA supporting text"],
  ["base-medium", "#71767a", "Secondary borders"],
  ["base-lighter", "#dfe1e2", "Separators"],
  ["base-lightest", "#f0f0f0", "Subtle surface"],
  ["info-darker", "#2e6276", "Information"],
  ["info-lighter", "#e7f6f8", "Information surface"],
  ["success-darker", "#216e1f", "Completed evidence"],
  ["success-lighter", "#ecf3ec", "Success surface"],
  ["warning-darker", "#936f38", "Review attention"],
  ["warning-lighter", "#faf3d1", "Warning surface"],
  ["error-dark", "#b21d38", "Errors / end"],
  ["error-lighter", "#f4e3db", "Error surface"],
];
function DesignSystem() {
  return (
    <div className="min-h-screen">
      <header className="bg-header px-6 py-8 text-header-foreground">
        <div className="mx-auto max-w-6xl">
          <Button
            asChild
            variant="ghost"
            className="mb-5 text-header-foreground hover:bg-header-foreground/10 hover:text-header-foreground"
          >
            <Link to="/">
              <ArrowLeft />
              MSA Operations
            </Link>
          </Button>
          <p className="text-xs">SYNTHETIC DEMO / REPLAY</p>
          <h1 className="mt-2 font-display text-3xl font-semibold">VA design foundation</h1>
          <p className="mt-2 text-sm">Veteran Access Bridge · MSA Operations · Demo</p>
        </div>
      </header>
      <div className="mx-auto max-w-6xl space-y-10 px-6 py-8">
        <section>
          <h2 className="font-display text-xl font-semibold">Official VA palette</h2>
          <p className="mb-4 mt-2 text-sm text-muted-foreground">
            Source:{" "}
            <a
              href="https://design.va.gov/foundation/color-palette"
              className="text-primary underline"
              target="_blank"
              rel="noreferrer"
            >
              VA Design System color palette
            </a>
            . Tokens are reproduced exactly; this prototype is not certified or endorsed by VA.
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {tokens.map(([name, value, usage]) => (
              <div key={name} className="overflow-hidden rounded-md border bg-surface">
                <div className="h-12 border-b" style={{ background: `var(--vads-${name})` }} />
                <div className="p-3">
                  <p className="break-all font-mono text-xs">--vads-{name}</p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{value}</p>
                  <p className="mt-2 text-xs">{usage}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">
            Light operations / dark conversation
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="border bg-surface p-5">
              <h3 className="font-semibold">Encounter context</h3>
              <p className="my-3 text-sm text-muted-foreground">
                Surface → foreground; supporting text uses base-dark.
              </p>
              <Button>Review synthetic proposal</Button>
              <div className="mt-4">
                <Chip tone="verified">Completed fixture</Chip>
              </div>
            </div>
            <div className="rounded-md bg-canvas p-5 text-canvas-text">
              <h3 className="font-semibold">Veteran ↔ Avery</h3>
              <p className="mt-3 text-xs text-canvas-highlight">
                Avery · Voice · Final · synthetic fixture
              </p>
              <p className="mt-2 text-sm leading-6">
                I found morning options with your assigned care team.
              </p>
              <p className="mt-4 text-xs text-canvas-muted">
                High-contrast conversation text. No live connection.
              </p>
            </div>
          </div>
        </section>
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">Typography</h2>
          <div className="space-y-3 border-y py-5">
            <p className="font-display text-2xl">Space Grotesk — workspace hierarchy</p>
            <p>IBM Plex Sans — interface and long-reading conversation</p>
            <p className="font-mono text-xs text-primary">
              IBM Plex Mono — scheduling.verify_slot · 13:42:01
            </p>
          </div>
        </section>
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">Simulated Avery states</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {(Object.keys(VOICE_META) as VoiceState[]).map((state) => (
              <div
                key={state}
                className="flex flex-col items-center rounded-md border bg-surface p-3 text-center"
              >
                <Aura state={state} size={80} />
                <p className="text-xs font-semibold">Simulated {VOICE_META[state].label}</p>
                <p className="mt-1 text-xs text-muted-foreground">{VOICE_META[state].hint}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Aura is a CSS stand-in, not LiveKit telemetry. Reduced-motion preferences disable
            animation.
          </p>
        </section>
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">Scheduling states</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {(Object.keys(SLOT_UI) as SlotStatus[]).map((state) => (
              <div key={state} className={cn("rounded-md border p-3 text-xs", SLOT_UI[state].cls)}>
                <span className="font-mono">08:30</span> · {SLOT_UI[state].label}
              </div>
            ))}
          </div>
        </section>
        <section className="border-t pt-6">
          <h2 className="font-display text-xl font-semibold">Phase 1 checkpoint</h2>
          <ul className="mt-4 space-y-3 text-sm">
            {[
              "Reusable MSA shell: queue, conversation, encounter; overlays on smaller screens.",
              "Role-labeled final turns and separate partial fixture; observational MCP trace, no hidden reasoning.",
              "Successful primary care replay and verification-review candidate are UI-only fixtures.",
              "Scheduling remains locked without successful fixture verification. Morning preference ranks, not excludes.",
              "Appointment approval remains separate from handoff acceptance. Six synthetic handoff scenarios are available in Operations.",
              "Media, ownership, verification and channel are orthogonal; accepted ownership never proves media join. Failed verification hides protected scheduling details.",
              "Canonical Next.js / FastAPI / governed MCP / Avery / LiveKit architecture is untouched.",
            ].map((note) => (
              <li key={note} className="flex gap-2">
                <CheckCircle2 className="size-4 shrink-0 text-primary" />
                {note}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
