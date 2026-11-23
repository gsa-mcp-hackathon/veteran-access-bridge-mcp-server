import type { AgentState } from "@livekit/components-react";
import type { RemoteAudioTrack } from "livekit-client";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";

/**
 * Official LiveKit Agents UI Aura (installed from @agents-ui registry).
 * In scripted replay no audioTrack exists (track-less state-only mode). In
 * authoritative monitor mode the subscribed agent RemoteAudioTrack is bound.
 * Loaded client-side only (WebGL shader).
 */
export default function AveryAura({
  state,
  audioTrack,
}: {
  state: AgentState;
  audioTrack?: RemoteAudioTrack | undefined;
}) {
  return (
    <AgentAudioVisualizerAura
      size="md"
      state={state}
      {...(audioTrack ? { audioTrack } : {})}
      color="#7c5cd6"
      colorShift={0.3}
      themeMode="dark"
      className="size-14 sm:size-[72px] min-[1100px]:size-[84px]"
    />
  );
}
