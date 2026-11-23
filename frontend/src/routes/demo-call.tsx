/* eslint-disable prettier/prettier -- Reformat App layout before release; preserve native IBM embed wiring. */
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, AudioLines, CalendarCheck2, ShieldCheck, UserRound, Activity, Bell, Bot, CheckCircle2, ClipboardList, Settings2, Headphones, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AveryEmbeddedChat } from "@/components/msa/avery-embedded-chat";

/**
 * The Veteran-facing synthetic call surface deliberately has its own route.
 * It shares the MSA visual design, but not the MSA's privileged observer controls.
 */
export const Route = createFileRoute("/demo-call")({
  head: () => ({
    meta: [
      { title: "Talk with Avery · Veteran Access Bridge" },
      {
        name: "description",
        content:
          "Native IBM watsonx Orchestrate chat and voice with Avery M6.4. Synthetic scheduling demo only.",
      },
    ],
  }),
  component: AveryVeteranCallPage,
});

function AveryVeteranCallPage() {
  return (
    <div className="msa-ibm-app flex min-h-[100dvh] flex-col bg-[#f3f6fa]">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 bg-[#09254b] px-4 py-3 text-white lg:px-6">
        <div>
          <p className="text-sm font-semibold">Veteran Access Bridge</p>
          <h1 className="text-lg font-semibold">Autonomous Scheduling Command Center</h1>
          <p className="text-xs text-blue-100">IBM native voice · MCP-powered</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded bg-sandbox px-2 py-1 text-xs font-bold text-sandbox-foreground">
            SANDBOX · Synthetic appointments
          </span>
          <Button
            asChild
            variant="outline"
            className="min-h-10 border-white/35 bg-transparent text-white hover:bg-white/10 hover:text-white"
          >
            <Link to="/">
              <ArrowLeft className="size-4" />
              MSA Command Center
            </Link>
          </Button>
        </div>
      </header>

      <main className="msa-ibm-main grid w-full flex-1 gap-3 p-3 lg:p-4 xl:grid-cols-[minmax(215px,0.75fr)_minmax(520px,1.8fr)_minmax(260px,0.95fr)]">
        <section className="min-w-0 space-y-3" aria-label="Veteran call overview">
          <div className="rounded-xl border border-[#234366] bg-[#102a48] p-4 text-white shadow-sm">
            <h2 className="mb-4 text-base font-semibold">Your Avery session</h2>
            <div className="grid grid-cols-2 items-start gap-3 text-center">
              <div className="flex flex-col items-center gap-2">
                <div className="grid size-16 place-items-center rounded-full border border-cyan-400/70 text-cyan-300">
                  <UserRound className="size-8" aria-hidden="true" />
                </div>
                <p className="text-sm font-semibold">Veteran</p>
              </div>
              <div className="flex flex-col items-center gap-2">
                <div className="grid size-16 place-items-center rounded-full border border-purple-400/70 text-purple-300">
                  <AudioLines className="size-8" aria-hidden="true" />
                </div>
                <p className="text-sm font-semibold">Avery</p>
              </div>
            </div>
            <p className="mt-3 border-t border-white/20 pt-3 text-xs text-blue-100">
              Avery M6.4 · IBM watsonx Orchestrate · No additional conversational agent
            </p>
          </div>
          <div className="console-card space-y-3 p-4">
            <h2 className="font-semibold">How it works</h2>
            <p className="text-sm text-muted-foreground">
              Start with Avery, then use the voice control in the embedded IBM conversation. You can
              also type your request.
            </p>
            <p className="text-sm text-muted-foreground">
              Try asking for a primary care appointment. Avery uses the existing synthetic
              scheduling MCP tools; no real VA appointment will be booked.
            </p>
          </div>
        </section>

        <section
          className="msa-ibm-conversation min-w-0 self-start bg-white"
          aria-label="Avery live conversation"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 bg-white px-4 py-3">
            <div>
              <h2 className="text-base font-semibold">Live Conversation</h2>
              <p className="text-xs text-muted-foreground">
                Avery · Continuous conversation and native IBM voice
              </p>
            </div>
            <span className="rounded-sm bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
              IBM Live agent
            </span>
          </div>
          <AveryEmbeddedChat />
        </section>

        <aside className="min-w-0 space-y-3" aria-label="Scheduling demo details">
          <div className="console-card space-y-3 p-4">
            <div className="flex items-center gap-2">
              <CalendarCheck2 className="size-5 text-primary" aria-hidden="true" />
              <h2 className="font-semibold">Scheduling Encounter</h2>
            </div>
            <p className="text-sm text-muted-foreground">
              Synthetic scheduling is governed by backend evidence. This panel has no verified appointment slots or booking receipt yet.
            </p>
          </div>
          <div className="console-card space-y-3 p-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-primary" aria-hidden="true" />
              <h2 className="font-semibold">Sandbox only</h2>
            </div>
            <p className="text-sm text-muted-foreground">
              This experience uses synthetic data. Do not enter real patient information. An IBM
              chat or voice response is not proof of a completed appointment.
            </p>
            <p className="text-xs text-muted-foreground">
              The protected MSA workspace is separate. Native IBM voice is not represented as a
              synchronized LiveKit audio track or transcript in that workspace.
            </p>
          </div>
        </aside>

        <details
          className="group min-w-0 rounded-xl border bg-white shadow-sm xl:col-span-3"
          aria-label="Operational Activity"
        >
          <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 rounded-xl p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#005ea2] [&::-webkit-details-marker]:hidden">
            <div>
              <h2 className="text-base font-bold text-[#162e51]">Operational Activity</h2>
              <p className="text-xs text-slate-500">Eight-stage scheduling workflow · Pending verified backend events</p>
            </div>
            <span className="text-xs font-semibold text-[#005ea2] group-open:hidden">Expand +</span>
            <span className="hidden text-xs font-semibold text-[#005ea2] group-open:inline">Collapse −</span>
          </summary>
          <div className="overflow-x-auto border-t px-3 py-4">
            <ol
              className="grid min-w-[760px] grid-cols-8 gap-2"
              aria-label="Scheduling stages not yet linked to IBM native voice"
            >
              {([
                ["Call Start", Headphones],
                ["AI Answers", Bot],
                ["Identify Intent", Activity],
                ["Structured Intake", ClipboardList],
                ["Validation", Settings2],
                ["Scheduling Options", CalendarCheck2],
                ["Notifications", Bell],
                ["Call Completion", CheckCircle2],
              ] as const).map(([label, Icon]) => (
                <li key={label} className="flex flex-col items-center gap-1 text-center">
                  <span className="grid size-9 place-items-center rounded-full border bg-slate-100 text-slate-500">
                    <Icon className="size-4" />
                  </span>
                  <span className="text-[11px] font-medium text-[#162e51]">{label}</span>
                  <span className="text-[10px] text-slate-500">Not observed</span>
                </li>
              ))}
            </ol>
          </div>
        </details>
        <details
          className="group min-w-0 rounded-xl border bg-white shadow-sm xl:col-span-3"
          aria-label="Wrap Up"
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#005ea2] [&::-webkit-details-marker]:hidden">
            <div>
              <h2 className="text-base font-bold text-[#162e51]">Wrap Up</h2>
              <p className="text-xs text-slate-500">After-call tasks · Requires persisted evidence</p>
            </div>
            <span className="shrink-0 text-xs font-semibold text-[#005ea2] group-open:hidden">Expand +</span>
            <span className="hidden shrink-0 text-xs font-semibold text-[#005ea2] group-open:inline">Collapse −</span>
          </summary>
          <div className="grid gap-3 border-t p-3 md:grid-cols-2">
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Settings2 className="size-4 text-blue-700" />
                AI Processing
              </h3>
              <p className="mt-2 text-xs text-slate-600">
                Notifications and encounter log: no receipt observed
              </p>
            </div>
            <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <FileText className="size-4 text-orange-700" />
                Needs Your Review
              </h3>
              <p className="mt-2 text-xs text-slate-600">
                Call summary and confirmation: awaiting verified backend evidence
              </p>
            </div>
          </div>
        </details>
      </main>
    </div>
  );
}
