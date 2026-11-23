import { useEffect, useMemo, useRef, useState } from "react";
import {
  Mic,
  MicOff,
  Headphones,
  PhoneOff,
  PhoneIncoming,
  Pause,
  UserPlus,
  Wifi,
  ShieldCheck,
  ChevronDown,
  Check,
  X,
  AlertTriangle,
  Loader2,
  Wrench,
  Play,
  RotateCcw,
  CalendarDays,
  List,
  Clock,
  MapPin,
  Lock,
  Circle,
  Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { RichConversation } from "@/components/msa/conversation";
import { cn } from "@/lib/utils";
import {
  SCRIPT,
  STAGES,
  QUEUE,
  emptyEncounter,
  slotsFor,
  scriptFor,
  canReviewAppointment,
  type DemoCase,
  type ActivityEvent,
  type Encounter,
  type Message,
  type Slot,
  type Stage,
  type VoiceState,
  type SlotStatus,
} from "@/lib/scenario";

export { useLive, type Live } from "@/components/msa/use-live";
import type { Live } from "@/components/msa/use-live";

/* ---------------- shared atoms ---------------- */
export const VOICE_META: Record<VoiceState, { label: string; hint: string; color: string }> = {
  listening: { label: "Listening", hint: "Receiving Veteran speech", color: "var(--ai)" },
  processing: { label: "Processing", hint: "Awaiting agent response", color: "var(--primary)" },
  speaking: { label: "Speaking", hint: "Avery responding via audio", color: "var(--avery)" },
  tools: { label: "Using MCP tools", hint: "Governed tools executing", color: "var(--verified)" },
  awaiting: {
    label: "Awaiting human",
    hint: "Scheduler decision required",
    color: "var(--attention)",
  },
  disconnected: {
    label: "Disconnected",
    hint: "Audio session ended",
    color: "var(--muted-foreground)",
  },
};

export function Chip({
  tone = "muted",
  children,
  icon,
}: {
  tone?: "muted" | "ai" | "avery" | "verified" | "attention" | "destructive";
  children: React.ReactNode;
  icon?: React.ReactNode;
}) {
  const map = {
    muted: "bg-muted text-muted-foreground",
    ai: "bg-ai/12 text-ai",
    avery: "bg-avery/15 text-avery",
    verified: "bg-verified/12 text-verified",
    attention: "bg-attention/15 text-attention",
    destructive: "bg-destructive/15 text-destructive",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        map[tone],
      )}
    >
      {icon}
      {children}
    </span>
  );
}

function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
      <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {children}
      </h2>
      {right}
    </div>
  );
}

/* ---------------- Aura visualizer (LiveKit Agents UI stand-in) ---------------- */
export function Aura({ state, size = 120 }: { state: VoiceState; size?: number }) {
  const c = VOICE_META[state].color;
  const off = state === "disconnected";
  const fast = state === "speaking" || state === "listening";
  return (
    <div
      className="relative grid place-items-center"
      style={{ width: size, height: size }}
      aria-label={`Avery: ${VOICE_META[state].label}`}
      role="img"
    >
      <div
        className={cn(
          "absolute inset-0 rounded-full blur-xl transition-colors duration-700",
          !off && "animate-aura-breathe",
        )}
        style={{
          background: `radial-gradient(circle, color-mix(in oklab, ${c} 45%, transparent), transparent 70%)`,
          animationDuration: fast ? "1.4s" : "3s",
        }}
      />
      <div
        className={cn("absolute inset-[14%] rounded-full", !off && "animate-aura-spin")}
        style={{
          background: `conic-gradient(from 0deg, transparent, ${c}, color-mix(in oklab, var(--avery) 70%, transparent), transparent 70%)`,
          maskImage:
            "radial-gradient(circle, transparent 58%, #000 60%, #000 66%, transparent 68%)",
          WebkitMaskImage:
            "radial-gradient(circle, transparent 58%, #000 60%, #000 66%, transparent 68%)",
          animationDuration: state === "tools" ? "1.6s" : state === "processing" ? "2.5s" : "6s",
        }}
      />
      <div
        className="absolute inset-[30%] rounded-full border border-border transition-all duration-500"
        style={{
          background: `radial-gradient(circle at 35% 30%, color-mix(in oklab, ${c} 60%, white 10%), color-mix(in oklab, ${c} 25%, var(--surface)) 70%)`,
          opacity: off ? 0.35 : 1,
        }}
      />
      {state === "awaiting" && <AlertTriangle className="relative size-5 text-background" />}
    </div>
  );
}

function Bars({ active, color }: { active: boolean; color: string }) {
  return (
    <div className="flex h-4 items-end gap-[2px]" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className="w-[3px] rounded-full transition-all"
          style={{
            background: color,
            height: active ? `${30 + ((i * 37) % 70)}%` : "20%",
            animation: active ? `aura-breathe ${0.6 + i * 0.15}s ease-in-out infinite` : undefined,
          }}
        />
      ))}
    </div>
  );
}

/* ---------------- A. Queue ---------------- */
export function Queue({ compact = false }: { compact?: boolean }) {
  const tone = {
    active: "ai",
    incoming: "avery",
    attention: "attention",
    waiting: "muted",
  } as const;
  const label = {
    active: "Avery active",
    incoming: "Incoming",
    attention: "Needs MSA",
    waiting: "Waiting",
  };
  return (
    <section className="panel flex min-h-0 flex-col">
      <SectionTitle
        right={
          <Chip tone="avery" icon={<PhoneIncoming className="size-3" />}>
            1 new
          </Chip>
        }
      >
        Live queue
      </SectionTitle>
      <ul className="flex-1 space-y-1 overflow-auto px-2 pb-2">
        {QUEUE.map((q, i) => (
          <li key={q.id}>
            <Button
              className={cn(
                "w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-accent",
                i === 0 && "bg-accent ring-1 ring-primary/40",
                q.status === "incoming" && "ring-1 ring-avery/50",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{q.name}</span>
                <span className="font-mono text-xs tabular-nums text-muted-foreground">
                  {q.dur}
                </span>
              </div>
              {!compact && (
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="truncate text-xs text-muted-foreground">{q.care}</span>
                  <Chip
                    tone={tone[q.status]}
                    icon={
                      q.status === "attention" ? (
                        <AlertTriangle className="size-3" />
                      ) : (
                        <Circle className="size-2 fill-current" />
                      )
                    }
                  >
                    {label[q.status]}
                  </Chip>
                </div>
              )}
            </Button>
          </li>
        ))}
      </ul>
      <div className="border-t px-4 py-2 text-xs text-muted-foreground">
        Synthetic data · 6 calls · avg wait 0:41
      </div>
    </section>
  );
}

/* ---------------- B. Avery voice + controls ---------------- */
export function AveryPanel({ live, layout = "row" }: { live: Live; layout?: "row" | "stack" }) {
  const m = VOICE_META[live.voice];
  const connected = live.voice !== "disconnected";
  return (
    <section
      className={cn(
        "panel p-3",
        layout === "row"
          ? "flex items-center gap-2"
          : "flex flex-col items-center gap-3 text-center",
      )}
    >
      <Aura state={live.voice} size={layout === "row" ? 64 : 140} />
      <div className={cn("min-w-0 flex-1", layout === "stack" && "w-full")}>
        <div className={cn("flex items-center gap-2", layout === "stack" && "justify-center")}>
          <span className="font-display text-lg font-semibold">Avery</span>
          <Chip tone="avery">AI assistant</Chip>
        </div>
        <div
          className={cn(
            "mt-1 flex items-center gap-2 text-sm",
            layout === "stack" && "justify-center",
          )}
        >
          <span className="size-2 rounded-full" style={{ background: m.color }} />
          <span className="font-medium" style={{ color: m.color }}>
            Simulated · {m.label}
          </span>
          <span className="hidden text-muted-foreground xl:inline">· {m.hint}</span>
        </div>
        <div
          className={cn(
            "mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs",
            layout === "stack" && "text-left",
          )}
        >
          <div className="text-muted-foreground">Audio source</div>
          <div className="text-muted-foreground">Workflow</div>
          <div className="flex items-center gap-1.5">
            <Wifi className={cn("size-3", connected ? "text-verified" : "text-muted-foreground")} />
            {connected ? "Synthetic replay · no live audio" : "Replay ended · no live audio"}
          </div>
          <div className="flex items-center gap-1.5">
            <Wrench className="size-3 text-ai" />
            Stage: {live.stage}
          </div>
        </div>
        <ControlBar live={live} className={cn("mt-3", layout === "stack" && "justify-center")} />
      </div>
    </section>
  );
}

function CtrlBtn({
  label,
  onClick,
  active,
  danger,
  disabled,
  children,
}: {
  label: string;
  onClick?: () => void;
  active?: boolean;
  danger?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Button
      aria-label={label}
      title={disabled ? `${label} — unavailable in synthetic replay` : `${label} (simulated)`}
      variant="secondary"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-11 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        danger
          ? "border-destructive/40 bg-destructive/15 text-destructive hover:bg-destructive/25"
          : active
            ? "border-primary/50 bg-primary/15 text-primary"
            : "bg-secondary hover:bg-accent",
      )}
    >
      {children}
      <span>{label}</span>
    </Button>
  );
}

function ControlBar({ live, className }: { live: Live; className?: string }) {
  const off = live.voice === "disconnected";
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <CtrlBtn
        label={live.muted ? "Unmute" : "Mute"}
        active={live.muted}
        onClick={() => live.setMuted(!live.muted)}
        disabled={off}
      >
        {live.muted ? <MicOff className="size-3.5" /> : <Mic className="size-3.5" />}
      </CtrlBtn>
      <CtrlBtn label="Monitor" active={!live.joined && !off} disabled={off}>
        <Headphones className="size-3.5" />
      </CtrlBtn>
      <CtrlBtn
        label={live.joined ? "Joined" : "Join"}
        active={live.joined}
        onClick={() => live.setJoined(!live.joined)}
        disabled={off}
      >
        <UserPlus className="size-3.5" />
      </CtrlBtn>
      <CtrlBtn label="Hold" disabled>
        <Pause className="size-3.5" />
      </CtrlBtn>
      <CtrlBtn label="End" danger onClick={live.end} disabled={off}>
        <PhoneOff className="size-3.5" />
      </CtrlBtn>
    </div>
  );
}

/* ---------------- C. Conversation ---------------- */
export const Conversation = RichConversation;

/* ---------------- C. Agent activity ---------------- */
const STATUS_UI: Record<
  ActivityEvent["status"],
  { icon: React.ReactNode; label: string; tone: "ai" | "verified" | "destructive" | "attention" }
> = {
  running: { icon: <Loader2 className="size-3 animate-spin" />, label: "Running", tone: "ai" },
  completed: { icon: <Check className="size-3" />, label: "Done", tone: "verified" },
  failed: { icon: <X className="size-3" />, label: "Failed", tone: "destructive" },
  human: { icon: <AlertTriangle className="size-3" />, label: "Action", tone: "attention" },
};

export function Activity({ live, className }: { live: Live; className?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className={cn("panel flex min-h-0 flex-col", className)}>
      <SectionTitle
        right={<span className="text-xs text-muted-foreground">{live.events.length} events</span>}
      >
        Observed activity
      </SectionTitle>
      <p className="px-4 pb-3 text-xs text-muted-foreground">
        Synthetic execution records · no hidden reasoning
      </p>
      <ol className="flex-1 overflow-auto px-4 pb-4">
        {[...live.events].reverse().map((e) => {
          const s = STATUS_UI[e.status];
          const isOpen = open === e.id;
          return (
            <li
              key={e.id}
              className="relative animate-fade-up border-l border-border pb-3 pl-4 last:pb-0"
            >
              <span
                className={cn(
                  "absolute -left-[5px] top-1.5 size-2.5 rounded-full ring-4 ring-surface",
                  {
                    ai: "bg-ai",
                    verified: "bg-verified",
                    destructive: "bg-destructive",
                    attention: "bg-attention",
                  }[s.tone],
                )}
              />
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm">{e.label}</div>
                  <div className="text-xs text-muted-foreground">
                    {e.mcp
                      ? "MCP · synthetic execution"
                      : e.status === "human"
                        ? "Governed · synthetic checkpoint"
                        : "Agent · replay event"}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">{e.time}</span>
                    {e.mcp && (
                      <Chip tone="ai" icon={<Wrench className="size-3" />}>
                        MCP
                      </Chip>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Chip tone={s.tone} icon={s.icon}>
                    {s.label}
                  </Chip>
                  {e.mcp && (
                    <Button
                      aria-expanded={isOpen}
                      aria-label="Inspect tool call"
                      variant="ghost"
                      size="icon"
                      onClick={() => setOpen(isOpen ? null : e.id)}
                      className="rounded p-1 hover:bg-accent"
                    >
                      <ChevronDown
                        className={cn("size-3.5 transition-transform", isOpen && "rotate-180")}
                      />
                    </Button>
                  )}
                </div>
              </div>
              {e.mcp && isOpen && (
                <dl className="mt-2 grid animate-fade-up grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-1 rounded-lg bg-background/60 p-3 font-mono text-xs">
                  <dt className="text-muted-foreground">server</dt>
                  <dd>Synthetic MCP fixture</dd>
                  <dt className="text-muted-foreground">tool</dt>
                  <dd className="text-ai">{e.mcp.tool}</dd>
                  <dt className="text-muted-foreground">status</dt>
                  <dd>{e.status}</dd>
                  <dt className="text-muted-foreground">duration</dt>
                  <dd>{e.mcp.durationMs} ms</dd>
                  <dt className="text-muted-foreground">params</dt>
                  <dd className="break-all">
                    {Object.entries(e.mcp.params).map(([k, v]) => (
                      <div key={k}>
                        {k}: {v}
                      </div>
                    ))}
                  </dd>
                  <dt className="text-muted-foreground">result</dt>
                  <dd className="font-sans">{e.mcp.result}</dd>
                  <dt className="text-muted-foreground">provenance</dt>
                  <dd className="break-words">{e.mcp.provenance} · synthetic</dd>
                  <dt className="text-muted-foreground">correlation</dt>
                  <dd className="break-all">{e.mcp.correlationId}</dd>
                  <dt className="text-muted-foreground">errors</dt>
                  <dd>{e.mcp.error ?? "none"}</dd>
                </dl>
              )}
            </li>
          );
        })}
        {live.events.length === 0 && (
          <li className="text-sm text-muted-foreground">No agent events yet.</li>
        )}
      </ol>
    </section>
  );
}

/* ---------------- Progress ---------------- */
export function Progress({ live }: { live: Live }) {
  const idx = STAGES.indexOf(live.stage);
  const done = live.enc.booked;
  return (
    <section className="panel px-4 py-3" aria-label="Scheduling progress">
      <ol className="grid grid-cols-3 gap-x-2 gap-y-3 sm:flex sm:items-center sm:gap-1">
        {STAGES.map((s, i) => {
          const complete = i < idx || (done && i === idx);
          const current = i === idx && !done;
          const human = current && live.enc.awaitingApproval;
          return (
            <li key={s} className="flex min-w-0 flex-1 items-center gap-1" title={s}>
              <div className="flex min-w-0 flex-col items-center gap-1">
                <span
                  className={cn(
                    "grid size-6 place-items-center rounded-full border text-xs font-semibold transition-all duration-500",
                    complete && "border-verified bg-verified/20 text-verified",
                    current &&
                      !human &&
                      "border-primary bg-primary/20 text-primary ring-4 ring-primary/15",
                    human &&
                      "border-attention bg-attention/20 text-attention ring-4 ring-attention/15",
                    !complete && !current && "text-muted-foreground",
                  )}
                >
                  {complete ? (
                    <Check className="size-3" />
                  ) : human ? (
                    <AlertTriangle className="size-3" />
                  ) : i > idx ? (
                    <Lock className="size-2.5" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={cn(
                    "max-w-full truncate text-xs",
                    current ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {s}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <span
                  className={cn(
                    "mb-4 hidden h-px flex-1 transition-colors duration-500 sm:block",
                    i < idx || done ? "bg-verified/60" : "bg-border",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/* ---------------- D. Scheduling ---------------- */
export const SLOT_UI: Record<
  SlotStatus,
  {
    label: string;
    cls: string;
    tone: "muted" | "ai" | "verified" | "attention" | "avery" | "destructive";
  }
> = {
  raw: {
    label: "Raw · unevaluated",
    cls: "border-dashed border-muted-foreground/40 text-muted-foreground",
    tone: "muted",
  },
  eligible: { label: "Eligible", cls: "border-ai/50 bg-ai/8", tone: "ai" },
  excluded: {
    label: "Excluded",
    cls: "border-border bg-muted/40 text-muted-foreground line-through decoration-muted-foreground/50",
    tone: "muted",
  },
  selected: { label: "Veteran selected", cls: "border-avery bg-avery/12", tone: "avery" },
  verified: {
    label: "Verified open",
    cls: "border-avery bg-avery/12 ring-1 ring-avery/40",
    tone: "avery",
  },
  confirmed: {
    label: "Veteran confirmed",
    cls: "border-attention bg-attention/10",
    tone: "attention",
  },
  booked: { label: "Simulated booked", cls: "border-verified bg-verified/15", tone: "verified" },
};

export function Scheduling({
  live,
  className,
  onRequestApproval,
}: {
  live: Live;
  className?: string;
  onRequestApproval?: () => void;
}) {
  const [view, setView] = useState<"week" | "list">("week");
  const { enc, slots } = live;
  const selected = slots.find((s) => s.id === enc.selectedId);
  const days = ["Tue 11/10", "Wed 11/11", "Thu 11/12", "Fri 11/13", "Mon 11/16"];
  return (
    <section className={cn("panel flex min-h-0 flex-col", className)}>
      <SectionTitle
        right={
          <div className="flex rounded-md bg-secondary p-0.5" aria-label="Calendar view">
            {(["week", "list"] as const).map((v) => (
              <Button
                key={v}
                variant="ghost"
                size="sm"
                aria-pressed={view === v}
                onClick={() => setView(v)}
                className={cn(
                  "flex items-center gap-1 rounded px-2 py-0.5 text-xs",
                  view === v ? "bg-accent text-foreground" : "text-muted-foreground",
                )}
              >
                {v === "week" ? <CalendarDays className="size-3" /> : <List className="size-3" />}
                {v === "week" ? "Week" : "List"}
              </Button>
            ))}
          </div>
        }
      >
        Scheduling encounter
      </SectionTitle>

      <div className="flex-1 space-y-3 overflow-auto px-4 pb-4">
        {!enc.verified && (
          <div role="status" className="flex items-center gap-2 rounded-md bg-muted p-3 text-xs">
            <Lock className="size-4 shrink-0" />
            Scheduling locked · identity verification not successful.
          </div>
        )}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Field
            k="Veteran"
            v={
              <span className="flex items-center gap-1">
                M. Delgado{" "}
                {enc.verified ? (
                  <Chip tone="verified" icon={<ShieldCheck className="size-3" />}>
                    Verified
                  </Chip>
                ) : (
                  <Chip>Unverified</Chip>
                )}
              </span>
            }
          />
          <Field k="Care category" v={enc.careCategory} />
          <Field k="Appointment type" v={enc.apptType} />
          <Field
            k="Facility"
            v={
              enc.facility && (
                <span className="flex items-center gap-1">
                  <MapPin className="size-3" />
                  {enc.facility}
                </span>
              )
            }
          />
        </div>
        <div>
          <div className="mb-1 text-xs text-muted-foreground">Veteran preferences</div>
          <div className="flex flex-wrap gap-1">
            {enc.prefs.length ? (
              enc.prefs.map((p) => (
                <Chip key={p} tone="ai">
                  {p}
                </Chip>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">Not captured yet</span>
            )}
          </div>
        </div>

        {!enc.slotsLoaded ? (
          <div className="grid h-40 place-items-center rounded-lg border border-dashed text-xs text-muted-foreground">
            Calendar populates when availability is retrieved
          </div>
        ) : view === "week" ? (
          <div className="grid grid-cols-5 gap-1.5">
            {days.map((d) => (
              <div key={d} className="min-w-0">
                <div className="mb-1 text-center text-xs text-muted-foreground">{d}</div>
                <div className="space-y-1">
                  {slots
                    .filter((s) => s.dayLabel === d)
                    .map((s) => (
                      <SlotCell key={s.id} s={s} />
                    ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <ul className="space-y-1.5">
            {slots.map((s) => (
              <SlotRow key={s.id} s={s} />
            ))}
          </ul>
        )}
        {enc.slotsLoaded && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {(
              [
                "raw",
                "eligible",
                "excluded",
                "selected",
                "verified",
                "confirmed",
                "booked",
              ] as SlotStatus[]
            ).map((k) => (
              <span key={k} className="flex items-center gap-1">
                <span className={cn("size-2.5 rounded-sm border", SLOT_UI[k].cls)} />
                {SLOT_UI[k].label}
              </span>
            ))}
          </div>
        )}
        {enc.evaluated && (
          <div className="rounded-lg bg-background/50 p-2.5 text-xs text-muted-foreground">
            <span className="text-foreground">Access standard:</span> Synthetic fixture: primary
            care ≤ 20 days from desired date. Eligible options are 3–6 days out. Morning preference
            ranks options; it does not exclude afternoon slots.
          </div>
        )}

        <div className="rounded-lg border p-3">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Selected appointment
          </div>
          {selected ? (
            <div className="text-sm">
              <span className="font-medium">
                {selected.dayLabel} · {selected.time}
              </span>{" "}
              · {selected.provider} · {selected.clinic}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              No selection
              {enc.approval === "declined"
                ? ` — previous proposal declined (${enc.declineReason})`
                : ""}
            </div>
          )}
          <ul className="mt-2 grid grid-cols-2 gap-1 text-xs">
            <Gate ok={!!selected} label="Veteran selection" />
            <Gate ok={enc.verifiedSlot} label="Slot verified" />
            <Gate ok={enc.veteranConfirmed} label="Veteran confirmed" />
            <Gate
              ok={enc.approval === "approved"}
              human={enc.awaitingApproval}
              label="MSA approval"
            />
          </ul>
          {enc.booked ? (
            <div className="mt-3 flex items-center gap-2 rounded-md bg-verified/15 px-3 py-2 text-sm text-verified">
              <Check className="size-4" />
              Simulated booking SIM-20261110-0830 · no system-of-record write
            </div>
          ) : (
            <Button
              disabled={!canReviewAppointment(enc) || live.voice === "disconnected"}
              onClick={onRequestApproval}
              className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
            >
              {canReviewAppointment(enc) ? (
                "Review & approve"
              ) : (
                <>
                  <Lock className="size-3.5" />
                  Booking locked until prerequisites met
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({ k, v }: { k: string; v?: React.ReactNode }) {
  return (
    <div className="rounded-md bg-background/40 px-2.5 py-1.5">
      <div className="text-xs text-muted-foreground">{k}</div>
      <div className="mt-0.5 truncate text-xs">
        {v ?? <span className="text-muted-foreground">—</span>}
      </div>
    </div>
  );
}
function Gate({ ok, human, label }: { ok: boolean; human?: boolean; label: string }) {
  return (
    <li
      className={cn(
        "flex items-center gap-1.5",
        ok ? "text-verified" : human ? "text-attention" : "text-muted-foreground",
      )}
    >
      {ok ? (
        <Check className="size-3" />
      ) : human ? (
        <AlertTriangle className="size-3" />
      ) : (
        <Circle className="size-3" />
      )}
      {label}
    </li>
  );
}
function SlotCell({ s }: { s: Slot }) {
  const [open, setOpen] = useState(false);
  return (
    <Button
      variant="ghost"
      onClick={() => setOpen(!open)}
      aria-expanded={open}
      className={cn(
        "h-auto min-h-11 w-full flex-col items-start gap-0 whitespace-normal rounded-md border px-1.5 py-1 text-left text-xs transition-all",
        SLOT_UI[s.status].cls,
      )}
    >
      <div className="font-mono font-medium">{s.time}</div>
      <div title={s.provider} className="w-full min-w-0 truncate text-xs">
        {s.status === "excluded" ? "Excluded" : s.provider}
      </div>
      {open && (
        <div className="mt-1 w-full break-words text-xs no-underline">
          {SLOT_UI[s.status].label}
          {s.reason && ` — ${s.reason}`} · {s.daysOut}d out
        </div>
      )}
    </Button>
  );
}
function SlotRow({ s }: { s: Slot }) {
  return (
    <li
      className={cn(
        "flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs",
        SLOT_UI[s.status].cls,
      )}
    >
      <span className="flex items-center gap-2">
        <Clock className="size-3" />
        <span className="font-mono">
          {s.dayLabel} {s.time}
        </span>{" "}
        · {s.provider}
      </span>
      <span className="flex items-center gap-2 no-underline">
        {s.reason && <span className="hidden text-xs xl:inline">{s.reason}</span>}
        <Chip tone={SLOT_UI[s.status].tone}>{SLOT_UI[s.status].label}</Chip>
      </span>
    </li>
  );
}

/* ---------------- Human in the loop ---------------- */
export function HitlBanner({ live, onReview }: { live: Live; onReview: () => void }) {
  if (!live.enc.awaitingApproval) return null;
  return (
    <div
      role="status"
      className="flex animate-fade-up items-center gap-3 rounded-xl border border-attention/40 bg-attention/10 px-4 py-2.5"
    >
      <AlertTriangle className="size-4 shrink-0 text-attention" />
      <div className="min-w-0 flex-1 text-sm">
        <span className="font-medium text-attention">MSA approval required.</span>{" "}
        <span className="text-muted-foreground">
          Veteran confirmed Tue 11/10 08:30. Policy requires scheduler approval before simulated
          booking.
        </span>
      </div>
      <Button
        onClick={onReview}
        className="rounded-md bg-attention px-3 py-1.5 text-xs font-semibold text-background"
      >
        Review
      </Button>
    </div>
  );
}

export function ApprovalSheet({
  live,
  open,
  onClose,
}: {
  live: Live;
  open: boolean;
  onClose: () => void;
}) {
  const opener = useRef<HTMLElement | null>(null);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("Provider schedule conflict");
  if (!open) return null;
  const sel = live.slots.find((s) => s.id === live.enc.selectedId);
  const tools = live.events.filter((e) => e.mcp && e.status === "completed");
  return (
    <Sheet
      open={open}
      onOpenChange={(value) => {
        if (!value) {
          onClose();
          setDeclining(false);
        }
      }}
    >
      <SheetContent
        className="flex w-full max-w-[460px] flex-col p-0 sm:max-w-[460px]"
        onOpenAutoFocus={() => {
          const active = document.activeElement;
          if (active instanceof HTMLElement) opener.current = active;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (opener.current?.isConnected) opener.current.focus();
        }}
      >
        <SheetTitle className="sr-only">Approval review</SheetTitle>
        <SheetDescription className="sr-only">
          Review synthetic appointment evidence.
        </SheetDescription>
        <div className="flex items-center justify-between border-b px-5 py-4 pr-16">
          <div>
            <div className="font-display text-lg font-semibold">Approve proposed appointment</div>
            <div className="text-xs text-muted-foreground">
              Why: scheduling policy requires MSA approval before booking.
            </div>
          </div>
        </div>
        <div className="flex-1 space-y-4 overflow-auto px-5 py-4 text-sm">
          <div className="rounded-lg border border-avery/40 bg-avery/10 p-3">
            <div className="text-xs text-muted-foreground">Proposed</div>
            <div className="font-medium">
              {sel ? `${sel.dayLabel} · ${sel.time} · ${sel.provider}` : "—"}
            </div>
            <div className="text-xs text-muted-foreground">
              PC Green Team · Riverside VA Clinic · In person · 30 min
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Conversation context
            </div>
            {live.messages.slice(-3).map((m) => (
              <p key={m.id} className="text-xs">
                <span className="text-muted-foreground">
                  {m.speaker === "veteran" ? "Veteran" : "Avery"}:
                </span>{" "}
                {m.text}
              </p>
            ))}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Completed MCP actions
            </div>
            <ul className="space-y-1">
              {tools.map((t) => (
                <li key={t.id} className="flex items-center gap-2 text-xs">
                  <Check className="size-3 text-verified" />
                  <span className="font-mono text-ai">{t.mcp?.tool}</span>
                  <span className="text-muted-foreground">{t.mcp?.durationMs}ms</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Evidence
            </div>
            <ul className="space-y-1 text-xs">
              <li className="flex gap-2">
                <ShieldCheck className="size-3.5 text-verified" />
                Identity verified (synthetic MPI)
              </li>
              <li className="flex gap-2">
                <ShieldCheck className="size-3.5 text-verified" />
                Assigned PACT team match
              </li>
              <li className="flex gap-2">
                <ShieldCheck className="size-3.5 text-verified" />
                Within 20-day access standard (3 days)
              </li>
              <li className="flex gap-2">
                <ShieldCheck className="size-3.5 text-verified" />
                Slot re-verified open at 13:42:01
              </li>
              <li className="flex gap-2">
                <ShieldCheck className="size-3.5 text-verified" />
                Veteran verbal confirmation recorded
              </li>
            </ul>
          </div>
          <div className="rounded-lg bg-background/60 p-3 text-xs">
            <span className="text-muted-foreground">Next permitted action:</span> Approve →
            simulated booking, or Decline with reason → return to Select.
          </div>
          {declining && (
            <label className="block text-xs">
              <span className="text-muted-foreground">Authorized decline reason</span>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border bg-secondary px-2 text-sm"
              >
                {[
                  "Provider schedule conflict",
                  "Clinical review required",
                  "Incorrect appointment type",
                  "Veteran requested change",
                ].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="flex gap-2 border-t px-5 py-4">
          {declining ? (
            <>
              <Button
                onClick={() => setDeclining(false)}
                variant="secondary"
                className="min-h-11 flex-1 rounded-md border text-sm"
              >
                Back
              </Button>
              <Button
                onClick={() => {
                  live.decline(reason);
                  onClose();
                  setDeclining(false);
                }}
                className="min-h-11 flex-1 rounded-md bg-destructive text-sm font-medium text-destructive-foreground"
              >
                Confirm decline
              </Button>
            </>
          ) : (
            <>
              <Button
                onClick={() => setDeclining(true)}
                variant="secondary"
                className="min-h-11 flex-1 rounded-md border text-sm"
              >
                Decline…
              </Button>
              <Button
                onClick={() => {
                  live.approve();
                  onClose();
                }}
                className="min-h-11 h-auto flex-[2] whitespace-normal rounded-md bg-verified text-sm font-semibold text-background"
              >
                Approve & simulate booking
              </Button>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ---------------- Top bar ---------------- */
export function TopBar({
  live,
  concept,
  setConcept,
}: {
  live: Live;
  concept: string;
  setConcept: (c: "A" | "B" | "C") => void;
}) {
  const names = { A: "Command Center", B: "Conversation First", C: "Scheduling Cockpit" };
  return (
    <header className="flex items-center gap-4 px-1">
      <div className="flex items-center gap-2.5">
        <div className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-ai to-avery font-display text-sm font-bold text-background">
          VA
        </div>
        <div>
          <div className="font-display text-sm font-semibold leading-tight">
            Veteran Access Bridge
          </div>
          <div className="text-xs text-muted-foreground">MSA Live Call Workspace</div>
        </div>
      </div>
      <nav className="ml-4 flex rounded-lg bg-surface p-0.5" aria-label="Design concept">
        {(["A", "B", "C"] as const).map((c) => (
          <Button
            key={c}
            onClick={() => setConcept(c)}
            aria-pressed={concept === c}
            className={cn(
              "rounded-md px-3 py-1 text-xs",
              concept === c
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="font-mono text-ai">{c}</span> {names[c]}
            {c === "A" && <span className="ml-1 text-xs text-verified">★</span>}
          </Button>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <Chip tone="attention">Synthetic data</Chip>
        <Button
          onClick={() => live.setPlaying(!live.playing)}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md bg-secondary px-2.5 text-xs"
        >
          {live.playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          {live.playing ? "Pause replay" : "Play replay"}
        </Button>
        <Button
          onClick={live.reset}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md bg-secondary px-2.5 text-xs"
        >
          <RotateCcw className="size-3.5" />
          Restart
        </Button>
        <a
          href="/design-system"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md border px-2.5 text-xs hover:bg-accent"
        >
          <Eye className="size-3.5" />
          Design system
        </a>
        <div className="grid size-8 place-items-center rounded-full bg-surface-2 text-xs font-semibold">
          WG
        </div>
      </div>
    </header>
  );
}
