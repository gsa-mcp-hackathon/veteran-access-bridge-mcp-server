# Live Conversation browser acceptance

On November 19, 2026 a reviewer-authenticated browser connected to the deployed Avery call center using a generated microphone signal. The caller said “I would like to schedule a primary care appointment.” After starting the call, the test observed the conversation without clicking any calendar, tool card or confirmation control.

| Browser observation | Outcome |
|---|---|
| Veteran caption containing the scheduling request | Visible |
| Avery caption | Visible |
| MCP tool name in the default Live Conversation feed | `get_scheduling_encounter` |
| Browser page errors | 0 |

The test ended the call without requesting a booking. It did not exercise persistence, letter generation, human speech recognition accuracy or a complete identity challenge. The tool card records a scheduling encounter lookup; this run does not establish a VA patient API call.

Frontend revision `vab-avery-callcenter-00035`, image commit `d26602a`. Voice worker revision `vab-avery-voice-worker-00010`, image commit `c0f6447`. Frontend suite: 204 passed. Focused Linux voice and verification suite: 55 passed.

The trusted worker sends finalized recognition text back to the originating participant through a private, voice-session-bound channel. Shared verification captions remain redacted. Browser-only updates are ephemeral. The booking service's CRM note status appears on the confirmed appointment card when its verified receipt says the note was saved.
