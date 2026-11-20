"""Redact verification speech before LiveKit history and caption publication."""

from dataclasses import replace

from livekit.agents import Agent, stt

from .spoken_last_four import redact_spoken_identity


class PrivateSpeechAgent(Agent):
    def __init__(self, *, dispatch, identity_pending, **kwargs):
        super().__init__(**kwargs)
        self._dispatch_private = dispatch
        self._identity_pending = identity_pending

    async def stt_node(self, audio, model_settings):
        async for event in Agent.default.stt_node(self, audio, model_settings):
            if event.alternatives:
                # Raw finalized speech goes only to the existing signed host path.
                if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                    self._dispatch_private(event.alternatives[0].text, "speech")
                event = replace(
                    event,
                    alternatives=[
                        replace(
                            alternative,
                            text=redact_spoken_identity(
                                alternative.text,
                                identity_phase=self._identity_pending(),
                            ),
                        )
                        for alternative in event.alternatives
                    ],
                )
            yield event
