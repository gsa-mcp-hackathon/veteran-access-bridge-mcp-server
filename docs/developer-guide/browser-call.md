# Run the browser application and complete a scheduling call

Open a **second terminal** while the worker is running. The browser application lives in the companion repository and uses Bun. Install [Bun](https://bun.sh/docs/installation) if `bun --version` is unavailable. From a directory alongside your backend checkout, run these commands in Bash:

```bash
git clone https://github.com/wbgreen0405/veteran-appointment-bridge.git
cd veteran-appointment-bridge
git rev-parse HEAD
bun install --frozen-lockfile
cp -n .env.example .env
```

Open the private `.env` file in VS Code. Set `VAB_API_BASE_URL` to your backend and configure `VAB_MSA_MONITOR_SERVICE_KEY` to match its server-side monitor credential. Use a distinct operator access code for the operator path. Select the access mode documented in the [frontend README](https://github.com/wbgreen0405/veteran-appointment-bridge) for the environment you are running. For the hosted reviewer experience, follow the [reviewer access instructions](https://github.com/wbgreen0405/veteran-appointment-bridge/blob/main/docs/deployment/reviewer-access.md) for the fixed HTTPS origin and guest call configuration. Restart the application after changing settings.

```bash
bun run dev
```

Open the local address printed by Vite. Sign in if prompted, choose **Call in Browser**, and allow microphone access. For a booking rehearsal, use a test identity linked to an open request with eligible slots in your own database.

| Say or do | Look for |
|---|---|
| Ask to schedule primary care and complete the spoken identity step | Caller and Avery turns appear. The verification trace identifies the tool, its caller and the verified state. |
| Ask for available times and choose one by voice | The calendar displays facility and local times, then the selected appointment. |
| Confirm the selected appointment once | The backend returns a persisted booking receipt tied to this interaction. |
| End the call | Wrap Up shows the CRM result and confirmation letter for the verified booking. |

**If speech works but there are no appointments:** inspect the verified case, its slot bindings and local inventory. **If the booking is confirmed but Wrap Up is empty:** check the call-ended event and persisted receipt for that same interaction.

[Configuration and secrets](configuration-and-secrets.md) · [Troubleshooting](troubleshooting.md)
