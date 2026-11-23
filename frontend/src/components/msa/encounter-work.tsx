import { useState } from "react";
import { FileText, Eye, Check, Bell, MoreHorizontal } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { ARTIFACTS, artifactState, canSaveArtifact, type ArtifactId } from "@/lib/encounter-work";
import type { Live } from "./use-live";
export function EncounterWork({ live }: { live: Live }) {
  const [saved, setSaved] = useState<Partial<Record<ArtifactId, boolean>>>({});
  const [preview, setPreview] = useState<ArtifactId | null>(null);
  const artifact = ARTIFACTS.find((item) => item.id === preview);
  return (
    <section aria-label="Avery's work" className="bg-surface p-4">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Avery's Work · Current Encounter</h2>
      </div>
      {!live.enc.verified ? (
        <div role="status" className="rounded-md border bg-secondary/40 px-3 py-3 text-sm">
          <p className="font-semibold">Waiting for verification</p>
          <p className="mt-1 text-muted-foreground">
            After verification Avery can prepare documents. Confirmation letter and notification
            await simulated booking.
          </p>
        </div>
      ) : (
        <ul className="divide-y rounded-md border">
          {ARTIFACTS.map((item) => {
            const state = artifactState(item.id, live, saved[item.id]);
            const Icon = item.id === "notification" ? Bell : FileText;
            const canPreview = !["Blocked", "Waiting", "Generating"].includes(state);
            const tone = ["Saved locally", "Recorded locally", "Delivered (simulation)"].includes(
              state,
            )
              ? "bg-verified/10 text-verified"
              : state === "Generating" || state === "Queued"
                ? "bg-attention/10 text-attention"
                : state === "Blocked"
                  ? "bg-destructive/10 text-destructive"
                  : "bg-secondary text-foreground";
            return (
              <li key={item.id} className="flex min-h-14 items-center gap-3 px-3 py-2">
                <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-medium">{item.title}</h3>
                  <p className="truncate text-xs text-muted-foreground" title={item.event}>
                    {state === "Blocked"
                      ? "Identity prerequisite not met"
                      : `Fixture · ${item.event}`}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>
                  {state}
                </span>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-11 shrink-0"
                      aria-label={`${item.title} actions`}
                    >
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem disabled={!canPreview} onSelect={() => setPreview(item.id)}>
                      <Eye />
                      Preview
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!canSaveArtifact(state)}
                      onSelect={() => setSaved((old) => ({ ...old, [item.id]: true }))}
                    >
                      <Check />
                      {item.id === "notification" ? "Simulate delivery" : "Save locally"}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        SANDBOX · scripted artifact states · no external write, send or EHR record.
      </p>
      <Sheet
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          <SheetTitle>{artifact?.title}</SheetTitle>
          <SheetDescription>Safe synthetic preview · not a clinical record</SheetDescription>
          <div className="mt-6 space-y-4 text-sm">
            <p>Status: {preview ? artifactState(preview, live, saved[preview]) : ""}</p>
            <p>
              Primary care scheduling request. Preferences: morning, in person. Verification inputs
              omitted.
            </p>
            {live.enc.booked && (
              <p>
                Simulated appointment: Tue November 10, 2026 · 08:30 · PC Green Team. Reference
                SIM-20261110-0830.
              </p>
            )}
            <p>
              {preview === "note" || preview === "summary"
                ? "Scheduling conversation and captured preferences summarized from local scripted turns. Drafts are not finalized clinical documentation."
                : "Confirmation content prepared from the simulated booking fixture."}
            </p>
            <p className="text-muted-foreground">
              In-memory preview only. No letter sent, EHR updated or real notification delivered.
              Refresh clears local state.
            </p>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
