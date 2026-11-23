import { useRef, useState, type RefObject } from "react";
import { BellRing, ShieldAlert, PhoneForwarded } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import {
  HANDOFF_SCENARIOS,
  DEMO_MSA,
  OTHER_MSA,
  needsAttention,
  ownershipLabel,
  nextAllowed,
  type HandoffState,
  type HandoffAction,
  type HandoffScenario,
} from "@/lib/handoff";
import type { HandoffDemo } from "./use-handoff";
import { cn } from "@/lib/utils";

export function HandoffIndicators({ state }: { state: HandoffState }) {
  return (
    <section
      aria-label="Synthetic session indicators"
      className="grid grid-cols-2 gap-x-4 gap-y-3 border-y px-4 py-3 xl:grid-cols-4"
    >
      {[
        ["Media / session", state.media],
        ["Ownership", ownershipLabel(state)],
        ["Verification", state.verification],
        ["Channel", `${state.channel} · simulated`],
      ].map(([label, value]) => (
        <div key={label} className="min-w-0">
          <p className="text-xs uppercase text-muted-foreground">{label}</p>
          <p className="mt-1 break-words text-xs font-semibold">{value}</p>
        </div>
      ))}
    </section>
  );
}
export function SafeHandoffContext({
  state,
  onReview,
}: {
  state: HandoffState;
  onReview: () => void;
}) {
  return (
    <section
      className="panel flex h-full w-full flex-col gap-4 p-4"
      aria-label="Protected scheduling boundary"
    >
      <h2 className="text-sm font-semibold">Verification / encounter context</h2>
      <div className="flex items-start gap-2 border-y py-4 text-sm">
        <ShieldAlert className="size-5 shrink-0 text-attention" />
        <div>
          <strong>Protected scheduling details hidden</strong>
          <p className="mt-2 text-xs text-muted-foreground">
            Identity: {state.verification}. No appointment details, provider, facility, slots or
            booking actions are available.
          </p>
        </div>
      </div>
      <dl className="space-y-3 text-xs">
        <div>
          <dt className="text-muted-foreground">Safe request</dt>
          <dd>Primary care scheduling enquiry (self-reported fixture)</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Permitted captured preferences</dt>
          <dd>
            {state.step ? "Morning · in person (self-reported, synthetic)" : "Not captured yet"}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Next allowed action</dt>
          <dd className="mt-1 leading-5">{nextAllowed(state)}</dd>
        </div>
      </dl>
      <Button variant="outline" onClick={onReview}>
        Open handoff review
      </Button>
      <p className="mt-auto text-xs text-muted-foreground">
        Acceptance is not identity verification or appointment approval. Non-persistent demo.
      </p>
    </section>
  );
}
export function HandoffQueue({
  demo,
  successStatus,
}: {
  demo: HandoffDemo;
  successStatus: string;
}) {
  const [filter, setFilter] = useState("all");
  return (
    <section className="flex h-full flex-col gap-3" aria-label="Handoff priority queue">
      <h2 className="text-sm font-semibold">Synthetic case queue</h2>
      <select
        aria-label="Handoff queue filter"
        className="h-11 rounded-md border bg-surface px-2 text-xs"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      >
        <option value="all">All scenarios</option>
        <option value="attention">Needs attention</option>
      </select>
      <ul className="space-y-2">
        {HANDOFF_SCENARIOS.filter(
          (scenario) =>
            filter === "all" ||
            demo.records.some(
              (record) => record.scenario === scenario.id && needsAttention(record),
            ),
        ).map((scenario) => {
          const state = demo.records.find((record) => record.scenario === scenario.id);
          return (
            <li key={scenario.id}>
              <Button
                variant="ghost"
                aria-pressed={demo.selected === scenario.id}
                onClick={() => demo.select(scenario.id)}
                className={cn(
                  "h-auto min-h-20 w-full justify-start whitespace-normal border px-3 py-3 text-left",
                  demo.selected === scenario.id && "border-primary bg-accent",
                  state && needsAttention(state) && "border-attention bg-attention/10",
                )}
              >
                <div className="min-w-0">
                  <p className="text-xs font-semibold">{scenario.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {scenario.id === "success"
                      ? successStatus
                      : state?.requestId
                        ? ownershipLabel(state)
                        : state?.step
                          ? "Replayed fixture"
                          : "Not replayed"}
                  </p>
                  {state && scenario.id !== "success" && state.step > 0 && (
                    <p className="mt-1 text-xs">Media: {state.media}</p>
                  )}
                </div>
              </Button>
            </li>
          );
        })}
      </ul>
      <p className="mt-auto text-xs text-muted-foreground">
        Local fixture records only. Refresh resets all cases.
      </p>
    </section>
  );
}
export function HandoffControls({ demo }: { demo: HandoffDemo }) {
  const state = demo.state;
  return (
    <div className="flex flex-wrap gap-2" aria-label="Synthetic session actions">
      <Button
        size="sm"
        className="min-h-11"
        variant="outline"
        disabled={state.media !== "active" || !["avery", "monitoring"].includes(state.ownership)}
        onClick={() => demo.dispatch({ type: "monitor" })}
      >
        Silent monitor
      </Button>
      <Button
        size="sm"
        className="min-h-11"
        variant="outline"
        disabled={
          state.media !== "active" ||
          !!state.owner ||
          ["pending", "requested", "closed"].includes(state.ownership)
        }
        onClick={() => demo.dispatch({ type: "request" })}
      >
        Request takeover
      </Button>
      <Button
        size="sm"
        className="min-h-11"
        variant="outline"
        disabled={state.media === "ended" || state.ownership === "closed"}
        onClick={() => demo.dispatch({ type: "advance" })}
      >
        Next fixture event
      </Button>
      <Button
        size="sm"
        className="min-h-11"
        variant="outline"
        disabled={state.media !== "active"}
        onClick={() => demo.dispatch({ type: "disconnect" })}
      >
        Simulate disconnect
      </Button>
      <Button
        size="sm"
        className="min-h-11"
        variant="outline"
        disabled={state.media !== "disconnected"}
        onClick={() => demo.dispatch({ type: "reconnect" })}
      >
        Simulate reconnect
      </Button>
      <Button
        size="sm"
        className="min-h-11"
        variant="destructive"
        disabled={state.media === "ended"}
        onClick={() => demo.dispatch({ type: "end" })}
      >
        End synthetic session
      </Button>
    </div>
  );
}
export function HandoffCenter({
  demo,
  open,
  onOpenChange,
  tab,
  onTabChange,
  triggerRef,
}: {
  demo: HandoffDemo;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tab: "inbox" | "review";
  onTabChange: (tab: "inbox" | "review") => void;
  /** External header trigger used for focus restoration. */
  triggerRef: RefObject<HTMLButtonElement | null>;
}) {
  const trigger = triggerRef;
  const opener = useRef<HTMLElement | null>(null);
  const [filter, setFilter] = useState("all");
  const attention = demo.records.filter(needsAttention);
  const state = demo.state;
  return (
    <>
      {attention.length > 0 && !(state.requestId && state.ownership !== "closed") && (
        <div
          role="status"
          className="mx-4 mt-3 flex min-w-0 items-center gap-2 text-xs text-attention sm:mx-6"
        >
          <BellRing className="size-4 shrink-0" />
          <span>
            {attention.length} synthetic takeover{" "}
            {attention.length === 1 ? "request needs" : "requests need"} attention
          </span>
        </div>
      )}
      {state.requestId && state.ownership !== "closed" && (
        <div
          className="sticky top-0 z-20 mx-4 mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-attention/40 bg-surface p-3 sm:mx-6"
          role="status"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-attention">{ownershipLabel(state)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {state.media === "disconnected" || state.media === "ended"
                ? `Session ${state.media} · `
                : ""}
              {state.owner ? `Owner: ${state.owner}. ` : "No accepting owner. "}
              {nextAllowed(state)}
            </p>
          </div>
          <Button
            size="sm"
            className="min-h-11"
            variant="outline"
            onClick={() => {
              onTabChange("review");
              onOpenChange(true);
            }}
          >
            Review
          </Button>
        </div>
      )}
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          className="flex w-full max-w-xl flex-col overflow-y-auto sm:max-w-xl"
          onOpenAutoFocus={() => {
            const active = document.activeElement;
            if (active instanceof HTMLElement) opener.current = active;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (opener.current?.isConnected) opener.current.focus();
            else trigger.current?.focus();
          }}
        >
          <SheetTitle>Synthetic handoff center</SheetTitle>
          <SheetDescription>
            UI-only acknowledgements · no persistence or live media
          </SheetDescription>
          <div className="flex gap-2">
            <Button
              variant={tab === "inbox" ? "secondary" : "ghost"}
              onClick={() => onTabChange("inbox")}
            >
              Inbox
            </Button>
            <Button
              variant={tab === "review" ? "secondary" : "ghost"}
              onClick={() => onTabChange("review")}
            >
              Selected case
            </Button>
          </div>
          {tab === "inbox" ? (
            <>
              <select
                aria-label="Inbox status filter"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="h-11 rounded-md border bg-surface px-3 text-sm"
              >
                <option value="all">All requests</option>
                {["requested", "pending", "accepted", "human", "rejected", "timeout", "closed"].map(
                  (status) => (
                    <option key={status}>{status}</option>
                  ),
                )}
              </select>
              <ul className="space-y-2">
                {demo.records
                  .filter(
                    (record) =>
                      record.requestId && (filter === "all" || record.ownership === filter),
                  )
                  .map((record) => (
                    <li key={record.scenario}>
                      <Button
                        variant="outline"
                        className="h-auto w-full justify-start whitespace-normal p-3 text-left"
                        onClick={() => {
                          demo.select(record.scenario);
                          onTabChange("review");
                        }}
                      >
                        <PhoneForwarded className="shrink-0" />
                        <div>
                          <p className="text-xs font-semibold">{record.requestId}</p>
                          <p className="mt-1 text-xs">
                            {ownershipLabel(record)} · media {record.media}
                          </p>
                          <p className="mt-1 text-xs">
                            Received {record.received} · {record.owner ?? "unassigned"}
                          </p>
                        </div>
                      </Button>
                    </li>
                  ))}
              </ul>
              {!demo.records.some(
                (record) => record.requestId && (filter === "all" || record.ownership === filter),
              ) && (
                <p className="py-5 text-sm text-muted-foreground">
                  No matching local handoff requests.
                </p>
              )}
            </>
          ) : (
            <HandoffReview key={state.scenario} state={state} dispatch={demo.dispatch} />
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
function HandoffReview({
  state,
  dispatch,
}: {
  state: HandoffState;
  dispatch: (action: HandoffAction) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [route, setRoute] = useState("Supervisor verification queue");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState("");
  return (
    <div className="space-y-5 text-sm">
      <HandoffIndicators state={state} />
      <dl className="grid grid-cols-[100px_minmax(0,1fr)] gap-3 text-xs">
        <dt className="text-muted-foreground">Reason</dt>
        <dd>Identity verification mismatch / MSA takeover fixture</dd>
        <dt className="text-muted-foreground">Safe summary</dt>
        <dd>
          Caller requests primary care help. Verification must be resolved by an authorized human
          outside this prototype.
        </dd>
        <dt className="text-muted-foreground">Preferences</dt>
        <dd>Morning · in person. Self-reported synthetic preferences only.</dd>
        <dt className="text-muted-foreground">Attempted</dt>
        <dd>
          {state.verification === "unverified"
            ? "No identity review yet"
            : "Synthetic identity status review; no raw identity inputs exposed"}
        </dd>
        <dt className="text-muted-foreground">Demo actor</dt>
        <dd>{state.owner ?? `${DEMO_MSA} · unassigned candidate`}</dd>
        <dt className="text-muted-foreground">Received</dt>
        <dd>{state.received ?? "No request created"}</dd>
        <dt className="text-muted-foreground">Provenance</dt>
        <dd>
          Local UI fixture · {state.requestId ?? state.scenario} · no MCP execution or record
          persistence
        </dd>
        <dt className="text-muted-foreground">Next allowed</dt>
        <dd>{nextAllowed(state)}</dd>
      </dl>
      <div className="border-y py-3 text-xs text-attention">
        Protected appointment details and availability are omitted. Handoff acceptance never marks
        verification matched.
      </div>
      <p role="status" className="rounded-md bg-accent p-3 text-xs text-accent-foreground">
        {state.notice}
      </p>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      {state.ownership === "requested" && (
        <Button onClick={() => dispatch({ type: "advance" })}>
          Simulate authorized queue routing
        </Button>
      )}
      {(state.ownership === "pending" || (state.owner && state.ownership !== "closed")) && (
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={state.media !== "active" && !state.owner}
            onClick={() => {
              if (state.owner) dispatch({ type: "accept" });
              else setConfirm(true);
            }}
          >
            {state.owner ? "Accept again (idempotency check)" : "Accept handoff"}
          </Button>
          {state.ownership === "pending" && (
            <Button variant="outline" onClick={() => setRejecting(true)}>
              Reject handoff
            </Button>
          )}
        </div>
      )}
      {confirm && !state.owner && (
        <div className="space-y-3 border-y py-4">
          <p className="text-xs">
            Confirm ownership as {DEMO_MSA}? This records a demo acknowledgement only; you are not
            joining media.
          </p>
          <div className="flex gap-2">
            <Button
              onClick={() => {
                dispatch({ type: "accept" });
                setConfirm(false);
              }}
            >
              Confirm acceptance
            </Button>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {rejecting && state.ownership === "pending" && (
        <form
          className="space-y-3 border-y py-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!reason.trim()) {
              setError("A rejection reason is required.");
              return;
            }
            dispatch({ type: "reject", reason, fallback: route });
            setRejecting(false);
            setError("");
          }}
        >
          <label className="block text-xs">
            Required rejection reason
            <input
              required
              aria-label="Required rejection reason"
              className="mt-2 h-11 w-full rounded-md border bg-surface px-3"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <FallbackSelector route={route} setRoute={setRoute} />
          <Button type="submit" variant="destructive">
            Confirm rejection & fallback
          </Button>
        </form>
      )}
      {state.ownership === "accepted" && state.owner === DEMO_MSA && (
        <Button disabled={state.media !== "active"} onClick={() => dispatch({ type: "join" })}>
          Simulate {state.channel === "voice" ? "join call" : "join chat"}
        </Button>
      )}
      {state.owner === OTHER_MSA && (
        <p className="text-xs font-semibold text-attention">
          Another demo MSA accepted first. There is no second owner or join action.
        </p>
      )}
      {state.ownership === "human" && (
        <p className="text-xs text-verified">
          Simulated media-joined acknowledged. Avery is now assistant / copilot.
        </p>
      )}
      {state.media === "disconnected" && (
        <Button onClick={() => dispatch({ type: "reconnect" })}>Simulate reconnect</Button>
      )}
      {state.requestId && state.ownership !== "closed" && (
        <div className="space-y-3 border-y py-4">
          <FallbackSelector route={route} setRoute={setRoute} />
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => dispatch({ type: "fallback", route })}>
              Route safe fallback
            </Button>
            {["rejected", "timeout"].includes(state.ownership) && (
              <Button
                variant="outline"
                disabled={state.media !== "active"}
                onClick={() => dispatch({ type: "request" })}
              >
                Retry handoff request
              </Button>
            )}
            {state.ownership === "pending" && (
              <Button variant="outline" onClick={() => dispatch({ type: "timeout" })}>
                Simulate timeout
              </Button>
            )}
          </div>
          <label className="block text-xs">
            Required resolution outcome
            <select
              aria-label="Required resolution outcome"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value)}
              className="mt-2 h-11 w-full rounded-md border bg-surface px-2"
            >
              <option value="">Select outcome</option>
              <option>Verification routed to supervisor</option>
              <option>Caller disconnected; safe callback review queued</option>
              <option>Human review completed outside prototype</option>
              <option>Owned by other demo scheduler</option>
            </select>
          </label>
          <Button
            variant="outline"
            onClick={() => {
              if (
                ["pending", "requested"].includes(state.ownership) &&
                state.media !== "active" &&
                !state.terminalFallback
              ) {
                setError("Confirm a safe fallback route before closing.");
                return;
              }
              if (!outcome) {
                setError("A resolution outcome is required.");
                return;
              }
              dispatch({ type: "close", outcome });
              setError("");
            }}
          >
            Close handoff
          </Button>
        </div>
      )}
      {state.resolution && <p className="text-xs text-verified">Closed: {state.resolution}</p>}
      <section>
        <h3 className="mb-3 text-xs font-semibold">Append-only mock audit · non-persistent</h3>
        <ol className="space-y-3 border-l pl-4">
          {state.audit.map((entry) => (
            <li key={entry.id}>
              <p className="break-all font-mono text-xs text-primary">
                {entry.event} · {entry.time}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{entry.detail}</p>
              <p className="mt-1 text-xs">UI fixture · {entry.id}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
function FallbackSelector({
  route,
  setRoute,
}: {
  route: string;
  setRoute: (route: string) => void;
}) {
  return (
    <label className="block text-xs">
      Fallback route
      <select
        aria-label="Fallback route"
        className="mt-2 h-11 w-full rounded-md border bg-surface px-2"
        value={route}
        onChange={(event) => setRoute(event.target.value)}
      >
        <option>Supervisor verification queue</option>
        <option>Alternate authorized MSA queue</option>
        <option>Safe callback review queue</option>
      </select>
    </label>
  );
}
