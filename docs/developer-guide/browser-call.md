# Connect the frontend

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

Open the local address printed by Vite and confirm the application loads. Keep the frontend and worker running in their terminals. Continue to [Run your first voice call](first-voice-call.md).
