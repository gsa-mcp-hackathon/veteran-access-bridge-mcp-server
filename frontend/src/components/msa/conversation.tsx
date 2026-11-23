import { useEffect, useRef, useState } from "react";
import { ArrowDown, AudioLines, MessageSquare, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Live } from "./use-live";
import { cn } from "@/lib/utils";

export function RichConversation({
  live,
  className,
  channel = "voice",
  sessionLabel,
}: {
  live: Live;
  className?: string;
  channel?: "voice" | "chat";
  sessionLabel?: string | undefined;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const previousIds = useRef("");
  const [unread, setUnread] = useState(false);
  const [partial, setPartial] = useState<"none" | "partial" | "final">("none");
  const ids = live.messages.map((m) => m.id).join("|");
  const scrollDown = () => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "auto" });
    nearBottom.current = true;
    setUnread(false);
  };
  useEffect(() => {
    if (!ids) {
      previousIds.current = "";
      nearBottom.current = true;
      setUnread(false);
      setPartial("none");
      return;
    }
    if (previousIds.current === ids) return;
    previousIds.current = ids;
    if (nearBottom.current)
      viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "auto" });
    else setUnread(true);
  }, [ids]);

  return (
    <section
      className={cn(
        "relative flex min-h-0 max-h-[650px] flex-col overflow-hidden rounded-lg border border-header bg-canvas text-canvas-text",
        className,
      )}
      aria-label="Veteran and Avery conversation"
    >
      <header className="sticky top-0 z-10 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b border-canvas-raised bg-canvas px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Veteran ↔ Avery</h2>
          <p className="mt-0.5 truncate text-xs text-canvas-muted">
            Primary care · synthetic encounter
          </p>
        </div>
        <AudioLines className="size-5 shrink-0 text-canvas-highlight" aria-hidden="true" />
      </header>
      <div className="flex items-center justify-between gap-2 border-b border-canvas-raised px-4 py-2 text-xs text-canvas-muted">
        <span>{channel} · scripted fixture · SYNTHETIC</span>
        <span>{live.messages.length + (partial === "final" ? 1 : 0)} final turns</span>
      </div>
      <div
        ref={viewport}
        tabIndex={0}
        aria-label="Conversation history"
        onScroll={() => {
          const el = viewport.current;
          if (!el) return;
          nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64;
          if (nearBottom.current) setUnread(false);
        }}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain p-4"
      >
        {live.messages.length === 0 && (
          <div className="grid min-h-40 place-items-center text-center text-sm text-canvas-muted">
            <div>
              <MessageSquare className="mx-auto mb-3 size-6" />
              {live.voice === "disconnected"
                ? "Replay ended. No conversation turns recorded."
                : live.playing
                  ? "Waiting for the first synthetic turn…"
                  : "Replay paused. No conversation turns yet."}
            </div>
          </div>
        )}
        {live.messages.map((message) => {
          const veteran = message.speaker === "veteran";
          const role = veteran ? "Veteran" : message.speaker === "msa" ? "MSA (demo)" : "Avery";
          return (
            <article key={message.id} className="grid grid-cols-[32px_minmax(0,1fr)] gap-3">
              <div
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-md",
                  veteran ? "avatar-caller" : "avatar-agent",
                )}
                aria-hidden="true"
              >
                {veteran ? <UserRound className="size-4" /> : <AudioLines className="size-4" />}
              </div>
              <div className={cn("msg-bubble min-w-0", veteran ? "msg-veteran" : "msg-avery")}>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-canvas-muted">
                  <span className="text-xs font-semibold text-canvas-text">{role}</span>
                  <time className="font-mono">{message.time}</time>
                  <span>{channel} · Final</span>
                </div>
                <p className="mt-1.5 whitespace-pre-wrap break-words text-sm leading-6">
                  {message.text}
                </p>
                <p className="mt-1 text-xs text-canvas-muted">
                  Source: UI scripted fixture · {message.id}
                </p>
              </div>
            </article>
          );
        })}
        {partial !== "none" && (
          <article
            className="border-l-2 border-canvas-highlight pl-3"
            aria-label="Synthetic partial message fixture"
          >
            <p className="text-xs text-canvas-muted">
              Veteran · {channel} · {partial === "partial" ? "Partial" : "Final"} · UI-only fixture
              · partial-demo-1
            </p>
            <p className="mt-1 text-sm">
              {partial === "partial"
                ? "I would prefer a morning…"
                : "I would prefer a morning appointment, please."}
            </p>
          </article>
        )}
        <div role="status" className="flex items-center gap-2 text-xs text-canvas-muted">
          <span className="size-1.5 shrink-0 rounded-full bg-canvas-highlight" />
          {sessionLabel ??
            (live.voice === "disconnected"
              ? "Synthetic session ended"
              : `Simulated ${live.voice === "tools" ? "MCP tool activity" : live.voice === "awaiting" ? "awaiting human review" : live.voice} · ${live.playing ? "replay" : "paused / checkpoint"}`)}
        </div>
      </div>
      {unread && (
        <Button
          onClick={scrollDown}
          size="sm"
          className="absolute bottom-16 left-1/2 -translate-x-1/2"
        >
          <ArrowDown />
          New messages
        </Button>
      )}
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-canvas-raised bg-canvas px-4 py-2">
        <span className="text-xs text-canvas-muted">No live audio or chat connection</span>
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 text-canvas-highlight hover:bg-canvas-raised hover:text-canvas-text"
          onClick={scrollDown}
        >
          <ArrowDown />
          Latest
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 text-canvas-highlight hover:bg-canvas-raised hover:text-canvas-text"
          onClick={() =>
            setPartial(partial === "none" ? "partial" : partial === "partial" ? "final" : "none")
          }
        >
          {partial === "none"
            ? "Partial fixture"
            : partial === "partial"
              ? "Finalize fixture"
              : "Clear fixture"}
        </Button>
      </footer>
    </section>
  );
}
