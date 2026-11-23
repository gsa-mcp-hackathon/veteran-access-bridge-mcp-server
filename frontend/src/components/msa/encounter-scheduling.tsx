import { useState } from "react";
import { Check, Search, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Live } from "./use-live";
export function EncounterScheduling({ live }: { live: Live }) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const enc = live.enc;
  const selected = enc.verified ? live.slots.find((slot) => slot.id === enc.selectedId) : undefined;
  const workflow = [
    ["Verify", enc.verified],
    ["Search", enc.evaluated],
    ["Select", !!enc.selectedId && enc.verifiedSlot && enc.veteranConfirmed],
    ["Book", enc.booked],
    ["Complete", live.events.some((event) => event.id === "work-notification-queued")],
  ] as const;
  return (
    <section aria-label="Scheduling encounter" className="bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Scheduling Encounter</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">Synthetic fixture</p>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${enc.verified ? "bg-verified/10 text-verified" : "bg-attention/10 text-attention"}`}
        >
          <ShieldCheck className="size-3.5" />
          {enc.booked
            ? "Verified · booked (simulated)"
            : enc.verified
              ? "Verified · in progress"
              : "Verification in progress"}
        </span>
      </div>
      <ol
        className="my-3 flex items-center justify-between gap-1 border-y py-2"
        aria-label="Scheduling progress"
      >
        {workflow.map(([label, done], index) => (
          <li key={label} className="flex flex-1 flex-col items-center gap-1 text-xs">
            <span
              className={
                done
                  ? "grid size-6 place-items-center rounded-full bg-verified text-primary-foreground"
                  : "grid size-6 place-items-center rounded-full border bg-muted text-muted-foreground"
              }
            >
              {done ? <Check className="size-3.5" /> : index + 1}
            </span>
            <span>
              {label}
              <span className="sr-only">{done ? " complete" : " pending"}</span>
            </span>
          </li>
        ))}
      </ol>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {[
          [
            "Veteran",
            enc.verified ? "Synthetic Veteran (verified)" : "Hidden until identity match",
          ],
          ["Care Category", enc.careCategory ?? "Not captured yet"],
          ["Selected Slot", selected ? `${selected.dayLabel} · ${selected.time}` : "None selected"],
          ["Provider", selected ? selected.provider : "—"],
          [
            "Facility",
            selected
              ? `${enc.facility ?? "Synthetic clinic"} · ${selected.clinic}`
              : (enc.facility ?? "—"),
          ],
          ["Preferences", enc.prefs.length ? enc.prefs.join(" · ") : "Not captured yet"],
        ].map(([term, value]) => (
          <div key={term} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{term}</dt>
            <dd className="break-words font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      {enc.booked ? (
        <div role="status" className="mt-3 rounded-md border border-verified/30 bg-verified/10 p-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-verified">
            <Check className="size-4" />
            Appointment Booked · Simulated
          </h3>
          <p className="mt-1 text-xs">
            SIM-20261110-0830 · no production write · no MSA action required
          </p>
        </div>
      ) : (
        <p role="status" className="mt-3 rounded-md bg-secondary p-2.5 text-sm">
          {enc.veteranConfirmed
            ? "Confirmed · awaiting simulated booking event"
            : "Avery is progressing the routine encounter. No MSA approval gate."}
        </p>
      )}
      <details className="mt-3">
        <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-medium">
          <Search className="size-4" />
          Eligibility evidence & options
        </summary>
        <label className="sr-only" htmlFor="slot-search">
          Search fixture options
        </label>
        <input
          id="slot-search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search fixture options"
          disabled={!enc.verified}
          className="min-h-11 w-full rounded-md border bg-background px-3 text-sm"
        />
        {!enc.verified ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Protected availability hidden until identity is matched.
          </p>
        ) : !live.slots.length ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Waiting for availability and eligibility evidence.
          </p>
        ) : (
          <ul
            className="mt-3 max-h-28 space-y-2 overflow-y-auto"
            aria-label="Eligible and excluded fixture options"
            tabIndex={0}
          >
            {live.slots
              .filter((slot) =>
                `${slot.dayLabel} ${slot.time} ${slot.provider} ${slot.status}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              )
              .map((slot) => (
                <li key={slot.id}>
                  <Button
                    variant="ghost"
                    aria-expanded={expanded === slot.id}
                    className="h-auto min-h-11 w-full justify-between gap-2 whitespace-normal rounded-md border p-2 text-left text-sm"
                    onClick={() => setExpanded(expanded === slot.id ? null : slot.id)}
                  >
                    <span className="min-w-0">
                      <span className="font-medium">
                        {slot.dayLabel} · {slot.time}
                      </span>
                      <br />
                      <span className="text-xs text-muted-foreground">{slot.provider}</span>
                    </span>
                    <span
                      className={slot.status === "excluded" ? "text-attention" : "text-verified"}
                    >
                      {slot.status}
                    </span>
                  </Button>
                  {expanded === slot.id && (
                    <p className="p-2 text-sm text-muted-foreground">
                      {slot.reason ??
                        `${slot.clinic} · ${slot.daysOut} days out. Morning preference ranks, not excludes.`}{" "}
                      Source: synthetic eligibility fixture.
                    </p>
                  )}
                </li>
              ))}
          </ul>
        )}
        {enc.evaluated && (
          <p className="mt-3 text-xs text-muted-foreground">
            5 eligible · 2 excluded. Morning preference does not exclude afternoon options. Slot
            verification and Veteran confirmation precede simulated booking.
          </p>
        )}
      </details>
    </section>
  );
}
