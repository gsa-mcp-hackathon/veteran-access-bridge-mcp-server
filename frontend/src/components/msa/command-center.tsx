import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  CircleDashed,
  Loader2,
  RotateCw,
  ShieldAlert,
  UserRound,
  AudioLines,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { friendlyToolName } from "@/lib/avery-tool-labels";
import type { Message, Slot } from "@/lib/scenario";
import {
  CATEGORY_LABEL,
  calendarFromSlots,
  coverage,
  type ExecutionStep,
  type StepStatus,
} from "@/lib/mcp-execution";

export const TRANSCRIPT_UNAVAILABLE = "Voice transcript unavailable from authoritative source";
export const AWAITING_AVAILABILITY = "Awaiting authorized availability evidence";

const STATUS: Record<StepStatus, { label: string; cls: string; Icon: typeof Check }> = {
  running: { label: "Running", cls: "bg-attention/10 text-attention", Icon: Loader2 },
  result_received: {
    label: "Result received · outcome unverified",
    cls: "bg-secondary text-foreground",
    Icon: CircleDashed,
  },
  succeeded: { label: "Succeeded", cls: "bg-verified/10 text-verified", Icon: Check },
  blocked: { label: "Blocked", cls: "bg-destructive/10 text-destructive", Icon: ShieldAlert },
  failed: { label: "Failed", cls: "bg-destructive/10 text-destructive", Icon: XCircle },
  retry: { label: "Retry", cls: "bg-attention/10 text-attention", Icon: RotateCw },
};

export function StatusPill({ status }: { status: StepStatus }) {
  const s = STATUS[status];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
        s.cls,
      )}
    >
      <s.Icon
        className={cn("size-3", status === "running" && "motion-safe:animate-spin")}
        aria-hidden="true"
      />
      {s.label}
    </span>
  );
}

export function ProvenanceBadge({ authoritative }: { authoritative: boolean }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        authoritative ? "bg-primary/10 text-primary" : "bg-sandbox text-sandbox-foreground",
      )}
    >
      {authoritative ? "Authoritative event" : "Scripted replay"}
    </span>
  );
}

/* ----------------------------- MCP card (inline) ---------------------------- */
function McpCard({ step, onFocus }: { step: ExecutionStep; onFocus: (id: string) => void }) {
  const p = step.params ?? {};
  return (
    <button
      type="button"
      onClick={() => onFocus(step.id)}
      aria-label={`MCP ${friendlyToolName(step.tool)}, ${STATUS[step.status].label}. Open in inspector`}
      className="w-full rounded-md border border-border bg-secondary/40 px-3 py-2 text-left text-sm hover:bg-secondary focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">{friendlyToolName(step.tool)}</span>
        <StatusPill status={step.status} />
        <ProvenanceBadge authoritative={step.provenance === "authoritative"} />
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {CATEGORY_LABEL[step.category]}
        {p["window"] ? ` · window ${p["window"]}` : ""}
        {p["care"] ? ` · ${p["care"]}` : ""}
        {p["clinic"] ? ` · ${p["clinic"]}` : ""}
        {p["modality"] ? ` · ${p["modality"]}` : ""}
      </p>
    </button>
  );
}

/* ------------------------------ Mini calendar ------------------------------ */
export function MiniCalendar({ slots, from }: { slots: Slot[]; from: Date }) {
  const days = useMemo(() => calendarFromSlots(slots, from), [slots, from]);
  const [open, setOpen] = useState<number | null>(null);
  const selected = slots.find((s) =>
    ["selected", "verified", "confirmed", "booked"].includes(s.status),
  );
  return (
    <section
      aria-label="Five business day availability (scripted replay)"
      className="rounded-md border bg-surface p-3"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <CalendarDays className="size-4 text-primary" aria-hidden="true" />
        <h3 className="font-semibold">Morning availability · 5 business days</h3>
        <ProvenanceBadge authoritative={false} />
      </div>
      <ul className="grid grid-cols-5 gap-1">
        {days.map((d, i) => {
          const shown = d.slots.slice(0, 1);
          const more = d.slots.length - shown.length;
          return (
            <li key={d.label} className="min-w-0 rounded border bg-background p-1 text-center">
              <p className="text-[11px] font-semibold">{d.weekday}</p>
              <p className="text-[11px] text-muted-foreground">{d.label}</p>
              <div className="mt-1 flex flex-col gap-1">
                {shown.length === 0 && <span className="text-[11px] text-muted-foreground">—</span>}
                {shown.map((s) => (
                  <span
                    key={s.id}
                    aria-label={`${d.weekday} ${d.label} ${s.time}${s === selected ? ", selected option" : ""}`}
                    className={cn(
                      "rounded px-1 py-0.5 font-mono text-[11px]",
                      s === selected
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary text-foreground",
                    )}
                  >
                    {s.time}
                  </span>
                ))}
                {more > 0 && (
                  <button
                    type="button"
                    className="min-h-6 rounded text-[11px] text-primary underline"
                    aria-expanded={open === i}
                    aria-label={`${more} more times on ${d.weekday} ${d.label}`}
                    onClick={() => setOpen(open === i ? null : i)}
                  >
                    +{more} more
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {open !== null && days[open] && (
        <div
          className="mt-2 rounded border bg-background p-2 text-xs"
          role="region"
          aria-label="Alternative times"
        >
          <p className="font-semibold">
            {days[open].weekday} {days[open].label} · all options
          </p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {days[open].slots.map((s) => (
              <li key={s.id} className="rounded bg-secondary px-1.5 py-0.5 font-mono">
                {s.time} · {s.provider}
              </li>
            ))}
          </ul>
        </div>
      )}
      {selected && (
        <p className="mt-2 text-xs text-muted-foreground">
          {selected.status === "booked"
            ? "Booking confirmed (simulated replay)."
            : "Selection recorded — not a booking."}
        </p>
      )}
    </section>
  );
}

/* ---------------------------- Live Conversation ---------------------------- */
type Item =
  { kind: "msg"; at: string; msg: Message } | { kind: "mcp"; at: string; step: ExecutionStep };

export function LiveConversation({
  authoritative,
  messages,
  steps,
  slots,
  showCalendar,
  calendarFrom,
  onFocusStep,
  emptyLabel,
}: {
  authoritative: boolean;
  messages: Message[];
  steps: ExecutionStep[];
  slots: Slot[];
  showCalendar: boolean;
  calendarFrom: Date;
  onFocusStep: (id: string) => void;
  emptyLabel: string;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const items: Item[] = useMemo(() => {
    const list: Item[] = [
      ...(authoritative
        ? []
        : messages.map((msg) => ({ kind: "msg" as const, at: msg.time, msg }))),
      ...steps.map((step) => ({ kind: "mcp" as const, at: step.startedAt, step })),
    ];
    return list.sort((a, b) => a.at.localeCompare(b.at));
  }, [authoritative, messages, steps]);
  const calendarAfter = steps.find(
    (s) => s.tool === "search_availability" && s.status === "succeeded",
  )?.id;
  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "auto" });
  }, [items.length]);
  return (
    <section
      aria-label="Live Conversation"
      className="console-card flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
        <h2 className="font-semibold">Live Conversation</h2>
        <ProvenanceBadge authoritative={authoritative} />
      </header>
      <div
        ref={viewport}
        tabIndex={0}
        aria-label="Conversation history"
        className="encounter-transcript min-h-0 flex-1 space-y-3 overflow-y-auto p-4"
      >
        {authoritative && (
          <p role="status" className="rounded-md border bg-secondary/40 p-3 text-sm font-medium">
            {TRANSCRIPT_UNAVAILABLE}
          </p>
        )}
        {items.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">{emptyLabel}</p>
        )}
        {items.map((item) =>
          item.kind === "msg" ? (
            <article key={item.msg.id} className="grid grid-cols-[28px_minmax(0,1fr)] gap-2.5">
              <div
                className={cn(
                  "grid size-7 place-items-center rounded-full",
                  item.msg.speaker === "veteran" ? "avatar-caller" : "avatar-agent",
                )}
                aria-hidden="true"
              >
                {item.msg.speaker === "veteran" ? (
                  <UserRound className="size-3.5" />
                ) : (
                  <AudioLines className="size-3.5" />
                )}
              </div>
              <div className="min-w-0">
                <p className="flex flex-wrap items-baseline gap-2 text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    {item.msg.speaker === "veteran"
                      ? "Veteran"
                      : item.msg.speaker === "msa"
                        ? "MSA (demo)"
                        : "Avery"}
                  </span>
                  <time className="font-mono">{item.msg.time}</time>
                  <span>Scripted replay</span>
                </p>
                <p className="mt-0.5 whitespace-pre-wrap break-words text-sm leading-6">
                  {item.msg.text}
                </p>
              </div>
            </article>
          ) : (
            <div key={item.step.id} className="space-y-2 pl-9">
              <McpCard step={item.step} onFocus={onFocusStep} />
              {!authoritative && showCalendar && item.step.id === calendarAfter && (
                <MiniCalendar slots={slots} from={calendarFrom} />
              )}
            </div>
          ),
        )}
        {authoritative && (
          <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
            <CalendarDays className="size-3.5" aria-hidden="true" />
            {AWAITING_AVAILABILITY}
          </p>
        )}
      </div>
    </section>
  );
}

/* --------------------------- MCP Execution Inspector -------------------------- */
const TABS = ["Execution Timeline", "Tool Details", "Evidence", "Audit"] as const;

export function McpInspector({
  steps,
  authoritative,
  focusId,
  correlationId,
  caseId,
}: {
  steps: ExecutionStep[];
  authoritative: boolean;
  focusId: string | null;
  correlationId: string | null;
  caseId: string;
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Execution Timeline");
  const [selected, setSelected] = useState<string | null>(null);
  const cov = coverage(steps);
  useEffect(() => {
    if (!focusId) return;
    setTab("Execution Timeline");
    setSelected(focusId);
    requestAnimationFrame(() => {
      const el = document.getElementById(`mcp-step-${focusId}`);
      el?.scrollIntoView({ block: "nearest" });
      el?.focus();
    });
  }, [focusId]);
  const current = steps.find((s) => s.id === selected) ?? steps[steps.length - 1];
  const na = <span className="text-muted-foreground">Unavailable</span>;
  return (
    <section
      aria-label="MCP Execution Inspector"
      className="console-card flex min-h-0 flex-1 flex-col"
    >
      <header className="border-b px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">MCP Execution Inspector</h2>
          <ProvenanceBadge authoritative={authoritative} />
        </div>
        <ul aria-label="MCP category coverage" className="mt-2 grid grid-cols-3 gap-1.5 text-xs">
          {(["dataset", "read", "write"] as const).map((c) => (
            <li key={c} className="rounded border px-2 py-1">
              <p className="truncate font-medium" title={CATEGORY_LABEL[c]}>
                {CATEGORY_LABEL[c]}
              </p>
              <p
                className={cn(
                  "font-semibold",
                  cov[c] === "observed"
                    ? "text-verified"
                    : cov[c] === "implemented"
                      ? "text-primary"
                      : "text-muted-foreground",
                )}
              >
                {cov[c] === "observed"
                  ? "Observed"
                  : cov[c] === "implemented"
                    ? "Implemented · not run"
                    : "Planned · not run"}
              </p>
            </li>
          ))}
        </ul>
      </header>
      <div
        role="tablist"
        aria-label="Inspector views"
        className="flex overflow-x-auto border-b px-2"
      >
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              "min-h-11 shrink-0 border-b-2 px-2.5 text-sm",
              tab === t ? "border-primary font-semibold text-primary" : "border-transparent",
            )}
          >
            {t}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        aria-label={tab}
        className="min-h-[260px] flex-1 overflow-y-auto p-3 text-sm"
      >
        {steps.length === 0 && tab !== "Audit" ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <CircleDashed className="size-4" aria-hidden="true" /> Awaiting MCP events
          </p>
        ) : tab === "Execution Timeline" ? (
          <ol className="relative space-y-2 border-l pl-4">
            {steps.map((s) => (
              <li key={s.id}>
                <button
                  id={`mcp-step-${s.id}`}
                  type="button"
                  onClick={() => setSelected(s.id)}
                  aria-current={current?.id === s.id ? "step" : undefined}
                  className={cn(
                    "w-full rounded-md border px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-ring",
                    current?.id === s.id ? "border-primary bg-primary/5" : "bg-surface",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold">{friendlyToolName(s.tool)}</span>
                    <StatusPill status={s.status} />
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {CATEGORY_LABEL[s.category]} · {s.startedAt}
                    {s.durationMs !== undefined ? ` · ${s.durationMs} ms` : ""}
                    {s.label ? ` · ${s.label}` : ""}
                  </p>
                </button>
              </li>
            ))}
            {!authoritative && cov.dataset === "planned" && (
              <li className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
                {CATEGORY_LABEL.dataset} · Planned · illustrative only, not run
              </li>
            )}
          </ol>
        ) : tab === "Tool Details" && current ? (
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5">
            <dt className="text-muted-foreground">Tool</dt>
            <dd>{friendlyToolName(current.tool)}</dd>
            <dt className="text-muted-foreground">Technical tool ID</dt>
            <dd className="break-all font-mono text-xs">{current.tool}</dd>
            <dt className="text-muted-foreground">Category</dt>
            <dd>{CATEGORY_LABEL[current.category]}</dd>
            <dt className="text-muted-foreground">Server ID</dt>
            <dd>{na}</dd>
            <dt className="text-muted-foreground">Source</dt>
            <dd>{current.source}</dd>
            <dt className="text-muted-foreground">Started</dt>
            <dd>{current.startedAt || na}</dd>
            <dt className="text-muted-foreground">Finished</dt>
            <dd>{current.finishedAt ?? na}</dd>
            <dt className="text-muted-foreground">Duration</dt>
            <dd>{current.durationMs !== undefined ? `${current.durationMs} ms` : na}</dd>
            <dt className="text-muted-foreground">Status</dt>
            <dd>
              <StatusPill status={current.status} />
            </dd>
            <dt className="text-muted-foreground">Policy outcome</dt>
            <dd>{na}</dd>
            {current.errorCode && (
              <>
                <dt className="text-muted-foreground">Error</dt>
                <dd>{current.errorCode}</dd>
              </>
            )}
          </dl>
        ) : tab === "Evidence" && current ? (
          <div className="space-y-2">
            {current.params ? (
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
                {Object.entries(current.params).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="font-mono text-muted-foreground">{k}</dt>
                    <dd className="break-all font-mono">{v}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-muted-foreground">
                Parameters unavailable from source (redacted).
              </p>
            )}
            <p className="text-xs">
              <span className="text-muted-foreground">Redacted readback: </span>
              {current.result ?? "Unavailable"}
            </p>
            <p className="text-xs text-muted-foreground">Idempotency key: unavailable</p>
          </div>
        ) : (
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted-foreground">Case</dt>
            <dd className="break-all font-mono">{caseId}</dd>
            <dt className="text-muted-foreground">Correlation</dt>
            <dd className="break-all font-mono">{correlationId ?? "Unavailable"}</dd>
            <dt className="text-muted-foreground">Event IDs</dt>
            <dd className="break-all font-mono">
              {steps.flatMap((s) => s.eventIds).join(", ") || "None"}
            </dd>
            <dt className="text-muted-foreground">Provenance</dt>
            <dd>
              {authoritative ? "Authoritative sanitized projection" : "Scripted replay fixture"}
            </dd>
          </dl>
        )}
      </div>
    </section>
  );
}

/* --------------------------- Autonomous workflow --------------------------- */
export function WorkflowSteps({
  verified,
  searched,
  selected,
  booked,
  authoritative,
}: {
  verified: boolean;
  searched: boolean;
  selected: boolean;
  booked: boolean;
  authoritative: boolean;
}) {
  const rows: [string, boolean, string][] = [
    ["Verify", verified, "Identity matched"],
    ["Search", searched, "Availability retrieved"],
    ["Select", selected, "Selection recorded — not a booking"],
    [
      "Book",
      booked,
      authoritative ? "Awaiting canonical booking evidence" : "Booking confirmed (simulated)",
    ],
  ];
  return (
    <section aria-label="Autonomous workflow" className="px-4 pt-3">
      <h3 className="text-sm font-semibold">Avery's Work · Autonomous Workflow</h3>
      <p className="text-xs text-muted-foreground">Routine path · no MSA approval required</p>
      <ol className="mt-2 grid grid-cols-4 gap-1 text-xs">
        {rows.map(([name, done, detail]) => (
          <li
            key={name}
            title={detail}
            aria-label={`${name}: ${done ? detail : "pending"}`}
            className={cn(
              "rounded border px-1.5 py-1 text-center",
              done ? "border-verified/40 bg-verified/10 text-verified" : "text-muted-foreground",
            )}
          >
            {done ? (
              <Check className="mx-auto size-3.5" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mx-auto size-3.5 opacity-40" aria-hidden="true" />
            )}
            <span className="font-semibold">{name}</span>
          </li>
        ))}
      </ol>
      {selected && !booked && (
        <p className="mt-1 text-xs text-muted-foreground">Selection recorded — not a booking.</p>
      )}
    </section>
  );
}

export function AwaitingEvidence({ label }: { label: string }) {
  return (
    <p role="status" className="px-4 py-3 text-sm text-muted-foreground">
      {label}
    </p>
  );
}
