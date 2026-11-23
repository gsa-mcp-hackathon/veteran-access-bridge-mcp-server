import { useState } from "react";
import { ChevronDown, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { HandoffState } from "@/lib/handoff";
export function HandoffTimeline({ state, className }: { state: HandoffState; className?: string }) {
  const [open, setOpen] = useState<string>();
  return (
    <section
      className={`panel flex min-h-0 flex-col p-4 ${className ?? ""}`}
      aria-label="Observed handoff activity"
    >
      <h2 className="text-sm font-semibold">Observed handoff activity</h2>
      <p className="mb-4 mt-2 text-xs text-muted-foreground">
        Synthetic UI projection events · not MCP calls · no private reasoning
      </p>
      <ol className="min-h-0 flex-1 overflow-y-auto">
        {state.audit.map((entry) => (
          <li key={entry.id} className="relative border-l pb-5 pl-5">
            <CheckCircle2 className="absolute -left-2 top-1 size-4 bg-surface text-primary" />
            <div className="grid grid-cols-[minmax(0,1fr)_44px] items-start gap-2">
              <div className="min-w-0">
                <h3 className="break-all font-mono text-xs">{entry.event}</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{entry.detail}</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-11"
                aria-label={`Inspect ${entry.event}`}
                aria-expanded={open === entry.id}
                onClick={() => setOpen(open === entry.id ? undefined : entry.id)}
              >
                <ChevronDown />
              </Button>
            </div>
            {open === entry.id && (
              <dl className="mt-2 grid grid-cols-[88px_minmax(0,1fr)] gap-2 border-y py-3 text-xs">
                <dt>Source</dt>
                <dd>Local synthetic reducer; no server execution</dd>
                <dt>Timestamp</dt>
                <dd>{entry.time} (fixture)</dd>
                <dt>Correlation</dt>
                <dd className="break-all">
                  {state.requestId ?? state.scenario} / {entry.id}
                </dd>
                <dt>Observed</dt>
                <dd>{entry.event}</dd>
                <dt>Result</dt>
                <dd>{entry.detail}</dd>
                <dt>Persistence</dt>
                <dd>None · reset or refresh clears local mock audit</dd>
              </dl>
            )}
          </li>
        ))}
      </ol>
      {state.audit.length === 0 && (
        <p className="text-xs text-muted-foreground">No synthetic events yet.</p>
      )}
    </section>
  );
}
