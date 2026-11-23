import { Link } from "@tanstack/react-router";
import { ArrowUpRight, Pause, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Live } from "./use-live";

export function MSAHeader({
  live,
  onRestart,
  handoff = false,
}: {
  live: Live;
  onRestart: () => void;
  handoff?: boolean;
}) {
  return (
    <header className="border-b border-header bg-header px-4 py-2 text-header-foreground sm:px-6">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div className="min-w-0">
          <p className="mb-1 text-xs font-medium uppercase tracking-[0.12em]">
            Veteran Access Bridge
          </p>
          <h1 className="truncate font-display text-xl font-semibold">MSA Operations</h1>
        </div>
        <div className="shrink-0 border border-header-foreground/30 px-2 py-1 text-xs font-semibold sm:text-xs">
          SYNTHETIC DEMO / REPLAY
        </div>
      </div>
      <div className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:flex sm:justify-between">
        <p className="min-w-0 text-xs text-header-foreground/90">
          Synthetic Operations <span className="hidden sm:inline">/ Primary care scheduling</span>
        </p>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            className="min-h-11 text-header-foreground hover:bg-header-foreground/10 hover:text-header-foreground"
            disabled={
              live.voice === "disconnected" ||
              (!handoff && (live.voice === "awaiting" || live.enc.booked))
            }
            onClick={() => live.setPlaying(!live.playing)}
          >
            {live.playing ? <Pause /> : <Play />}
            <span className="hidden sm:inline">
              {live.playing ? "Pause replay" : "Play replay"}
            </span>
            <span className="sr-only sm:hidden">
              {live.playing ? "Pause replay" : "Play replay"}
            </span>
          </Button>
          <Button
            aria-label="Restart replay"
            title="Restart replay"
            size="icon"
            variant="ghost"
            className="size-11 text-header-foreground hover:bg-header-foreground/10 hover:text-header-foreground"
            onClick={onRestart}
          >
            <RotateCcw />
          </Button>
          <Button
            asChild
            size="sm"
            variant="ghost"
            className="min-h-11 text-header-foreground hover:bg-header-foreground/10 hover:text-header-foreground"
          >
            <Link to="/design-system">
              <span className="hidden sm:inline">Design system</span>
              <span className="sr-only sm:hidden">Design system</span>
              <ArrowUpRight />
            </Link>
          </Button>
          <span className="hidden border-l border-header-foreground/30 pl-3 text-xs sm:block">
            W. Green
            <br />
            MSA · demo actor
          </span>
        </div>
      </div>
    </header>
  );
}
