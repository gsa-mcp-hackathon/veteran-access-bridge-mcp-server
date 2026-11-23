# Isolated browser latency probe

Branch: `experiment/avery-latency-20261117`. Not deployed; off by default.

The test frontend build must set `VITE_ENABLE_LATENCY_PROBE=true`; its isolated
worker must set `VAB_ENABLE_LATENCY_PROBE=true`. Never enable these by editing
the existing deployed Avery configuration during this experiment.

The worker sends a random diagnostic trace ID immediately before requesting
speech. The frontend accepts this marker only from a classified agent and samples
its decoded audio energy every 20 ms. Browser console records contain only the
trace ID, a duration and a status. No transcript, audio recording, patient data or
credentials are logged by this probe. Nothing is uploaded.

`ready_to_decoded_audio_ms` starts when the browser receives the marker and ends
when RMS exceeds 0.01. This is not end-of-caller-speech latency, a speaker-output
measurement, or a timestamp to subtract from backend wall clocks. Correlate by
trace ID and keep the measured spans separate. Overlap, unavailable audio and
timeouts have null duration. Hidden tabs or suspended audio contexts invalidate
pending measurements. Track removal/call cleanup releases the audio context.

The worker marker can add up to 250 ms of diagnostic overhead. Both comparison
variants must use the same instrumentation; normal operation leaves it disabled.

Focused probe/call tests passed (5); full CI passed on `5aa4ab0`, including
TypeScript, lint, tests, observer handshake tests and production build.
CI evidence.
Real browser audio validation against an isolated voice stack remains pending.

Backend comparison plan and remaining boundary.
