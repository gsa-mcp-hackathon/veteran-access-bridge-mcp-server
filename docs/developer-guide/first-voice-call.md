# Run your first voice call

Start with the [connected frontend](browser-call.md) open and the voice worker registered in your LiveKit project. Sign in if prompted, choose **Call in Browser**, and allow microphone access. For a booking rehearsal, use a test identity linked to an open request with eligible slots in your own database.

| Say or do | Look for |
|---|---|
| Ask to schedule primary care and complete the spoken identity step | Caller and Avery turns appear. The verification trace identifies the tool, its caller and the verified state. |
| Ask for available times and choose one by voice | The calendar displays facility and local times, then the selected appointment. |
| Confirm the selected appointment once | The backend returns a persisted booking receipt tied to this interaction. |
| End the call | Wrap Up shows the CRM result and confirmation letter for the verified booking. |

**If speech works but there are no appointments:** inspect the verified case, its slot bindings and local inventory. **If the booking is confirmed but Wrap Up is empty:** check the call-ended event and persisted receipt for that same interaction.

[Configuration and secrets](configuration-and-secrets.md) · [Troubleshooting](troubleshooting.md)
