import { useState } from "react";
import { AlertTriangle, ArrowDownWideNarrow, PhoneIncoming, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { QUEUE, type DemoCase } from "@/lib/scenario";
import type { Live } from "./use-live";
import { cn } from "@/lib/utils";

export function DemoQueue({
  selected,
  onSelect,
  live,
}: {
  selected: DemoCase;
  onSelect: (value: DemoCase) => void;
  live: Live;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [reverse, setReverse] = useState(false);
  const rows = QUEUE.filter(
    (row) =>
      `${row.name} ${row.care}`.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" || row.status === filter),
  );
  const sorted = [...rows].sort((a, b) =>
    reverse ? b.name.localeCompare(a.name) : a.name.localeCompare(b.name),
  );
  return (
    <section className="flex h-full min-h-0 w-full flex-col" aria-label="Synthetic encounter queue">
      <div className="flex items-center justify-between border-b pb-3">
        <h2 className="text-sm font-semibold">Demo queue</h2>
        <span className="font-mono text-xs text-muted-foreground">{QUEUE.length} fixtures</span>
      </div>
      <div className="relative mt-3">
        <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input
          aria-label="Filter demo queue"
          placeholder="Find encounter"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-11 pl-9"
        />
      </div>
      <div className="my-3 grid grid-cols-[minmax(0,1fr)_44px] gap-2">
        <select
          aria-label="Queue status filter"
          className="min-w-0 rounded-md border bg-surface px-2 text-xs"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All demo statuses</option>
          <option value="attention">Needs review</option>
          <option value="incoming">Incoming</option>
          <option value="active">Active fixtures</option>
          <option value="waiting">Waiting</option>
        </select>
        <Button
          variant="outline"
          size="icon"
          className="size-11"
          aria-label="Sort queue by name"
          aria-pressed={reverse}
          onClick={() => setReverse(!reverse)}
          title="Sort queue by name"
        >
          <ArrowDownWideNarrow />
        </Button>
      </div>
      <div className="mb-3 flex items-start gap-2 rounded-md bg-accent px-3 py-2 text-xs text-accent-foreground">
        <PhoneIncoming className="mt-0.5 size-4 shrink-0" />
        <div>
          Incoming fixture
          <span className="mt-0.5 block text-xs">Masked caller · not connected</span>
        </div>
      </div>
      <ul className="min-h-0 flex-1 space-y-1 overflow-auto">
        {sorted.map((row) => {
          const value: DemoCase = row.id === "q3" ? "verification-review" : "success";
          const available = row.id === "q1" || row.id === "q3";
          const active = available && selected === value;
          return (
            <li key={row.id}>
              <Button
                disabled={!available}
                variant="ghost"
                onClick={() => onSelect(value)}
                aria-pressed={active}
                className={cn(
                  "h-auto min-h-20 w-full justify-start whitespace-normal rounded-md border border-transparent px-3 py-3 text-left disabled:opacity-70",
                  active && "border-primary bg-accent text-accent-foreground",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">
                    {row.id === "q3" ? "M. Delgado · review" : row.name}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {row.id === "q3" ? "Verification review candidate" : row.care}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {active
                      ? live.voice === "disconnected"
                        ? "Replay ended"
                        : live.enc.booked
                          ? "Simulated booking complete"
                          : live.voice === "awaiting"
                            ? "Review checkpoint"
                            : live.playing
                              ? "Replaying"
                              : "Paused"
                      : available
                        ? "Ready to replay"
                        : "Queue-only fixture"}{" "}
                    · synthetic
                  </div>
                </div>
                {row.id === "q3" && <AlertTriangle className="shrink-0 text-attention" />}
              </Button>
            </li>
          );
        })}
        {sorted.length === 0 && (
          <li className="p-3 text-xs text-muted-foreground">No matching synthetic encounters.</li>
        )}
      </ul>
      <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">
        2 replayable cases · 4 queue-only fixtures
      </p>
    </section>
  );
}
