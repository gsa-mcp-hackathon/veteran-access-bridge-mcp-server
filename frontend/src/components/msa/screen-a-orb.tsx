/* eslint-disable prettier/prettier -- Screen A feature branch: run Prettier at integration/release gate. */
import type { AgentState } from "@livekit/components-react";
import type { RemoteAudioTrack } from "livekit-client";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";

/** Official LiveKit Agents UI Aura, never a looping GIF or scripted waveform. */
export default function ScreenAOrb({
  state,
  audioTrack,
}: {
  state: AgentState;
  audioTrack?: RemoteAudioTrack | undefined;
}) {
  return (
    <AgentAudioVisualizerAura
      size="lg"
      state={state}
      {...(audioTrack ? { audioTrack } : {})}
      color="#9874F2"
      colorShift={0.2}
      themeMode="dark"
      className="h-[210px] w-[210px] sm:h-[224px] sm:w-[224px]"
      aria-label={`LiveKit Aura · Avery ${state}`}
    />
  );
}
