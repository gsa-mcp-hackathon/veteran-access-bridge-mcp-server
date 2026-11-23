import { useState } from "react";
import { Mic, MicOff, PhoneCall, PhoneOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useOneClickCall, type CallSession } from "./use-one-click-call";

const STATUS: Record<string, string> = {
  checking: "Connecting to Avery…",
  ready: "Mic off · ready",
  unavailable: "Voice backend not ready",
  starting: "Creating synthetic call…",
  joining: "Opening microphone…",
  live: "Mic live",
  ending: "Hanging up…",
  error: "Call not established",
};

/** Start Demo Call / mic status / Hang Up for the private one-click demo. */
export function OneClickCallControls(props: {
  onSession: (s: CallSession, accessCode?: string) => void;
  onEnded: () => void;
}) {
  const call = useOneClickCall(props);
  const [draftCode, setDraftCode] = useState("");
  if (call.phase === "unconfigured")
    return (
      <div role="status" className="max-w-md text-sm">
        <p className="font-medium">Live demo backend not configured</p>
        <p className="text-muted-foreground">
          Connect this project's server-side API to the existing IBM Code Engine HTTPS endpoint and
          configure private demo credentials. No credentials belong in browser code.
        </p>
      </div>
    );
  if (call.phase === "authorization_required")
    return (
      <form
        className="flex flex-wrap items-end gap-2 text-sm"
        aria-label="Connect to Avery"
        onSubmit={(event) => {
          event.preventDefault();
          if (draftCode.length >= 32) {
            call.setAccessCode(draftCode);
            setDraftCode("");
          }
        }}
      >
        <label className="flex flex-col gap-1" htmlFor="demo-access-code">
          <span>Demo access code (once per session)</span>
          <input
            id="demo-access-code"
            type="password"
            autoComplete="off"
            value={draftCode}
            onChange={(event) => setDraftCode(event.target.value)}
            className="min-h-11 rounded-md border bg-background px-3 text-foreground"
            required
          />
        </label>
        <Button type="submit" disabled={draftCode.length < 32} className="min-h-11">
          Connect to Avery
        </Button>
        {call.error && (
          <span role="alert" className="text-destructive">
            {call.error}
          </span>
        )}
      </form>
    );
  const inCall = ["starting", "joining", "live"].includes(call.phase);
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Demo call">
      {!inCall ? (
        <Button
          className="min-h-11 gap-2"
          disabled={call.phase === "checking" || call.phase === "ending"}
          onClick={() => (call.phase === "unavailable" ? call.retryStatus() : void call.start())}
        >
          {call.phase === "unavailable" ? <RefreshCw size={16} /> : <PhoneCall size={16} />}
          {call.phase === "unavailable" ? "Retry backend connection" : "Start Demo Call"}
        </Button>
      ) : (
        <Button variant="destructive" className="min-h-11 gap-2" onClick={() => void call.hangUp()}>
          <PhoneOff size={16} /> Hang Up
        </Button>
      )}
      {call.phase === "live" && (
        <Button
          variant="outline"
          className="min-h-11"
          aria-pressed={call.muted}
          aria-label={call.muted ? "Unmute microphone" : "Mute microphone"}
          onClick={() => void call.toggleMute()}
        >
          {call.muted ? <MicOff size={16} /> : <Mic size={16} />}
        </Button>
      )}
      <span role="status" className="text-sm text-muted-foreground">
        {call.phase === "live" && call.muted ? "Mic muted" : STATUS[call.phase]}
        {call.phase === "live" &&
          (call.averyAudio ? " · Avery audio received" : " · waiting for Avery audio")}
      </span>
      {call.notice && (
        <p role="status" className="text-sm">
          {call.notice}
        </p>
      )}
      {call.error && (
        <span role="alert" className="text-sm text-destructive">
          {call.error}
        </span>
      )}
    </div>
  );
}
