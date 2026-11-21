# Connect Deepgram and start the voice worker

Deepgram transcribes what the caller says and synthesizes Avery’s reply. The worker sends a turn to the scheduling backend, which communicates with Orchestrate. Start in the same Bash terminal where you set the [LiveKit credentials](livekit.md).

1. In the [Deepgram console](https://console.deepgram.com/), select your own project and create a key with speech API access. Store the key privately. [Deepgram API key instructions](https://developers.deepgram.com/docs/create-additional-api-keys)
2. At the root of the backend repository, enter the key and the HTTPS address of your deployed scheduling backend. Use the base address without the MCP path. Install the locked voice dependencies and start the worker:

    ```bash
    read -rsp "Deepgram API key: " DEEPGRAM_API_KEY; echo
    read -rp "Scheduling backend base URL: " VAB_VOICE_BACKEND_URL
    export DEEPGRAM_API_KEY VAB_VOICE_BACKEND_URL
    uv sync --locked --group dev --extra voice
    bash scripts/run-voice-worker-codespace.sh
    ```

3. Keep the process running while testing. The launcher prints the selected speech models and backend address. For the protected booking path, configure the trusted worker credentials from the [backend environment example](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/.env.example) in both participating services before trying a write.

**Speech check:** say “I’d like a primary care appointment.” Confirm that the caller’s words appear in the conversation and Avery’s reply is audible. Worker registration checks the LiveKit connection. This spoken exchange checks both directions of the speech pipeline.

**If you see a transcript but hear silence:** inspect the worker’s speech synthesis error and verify the configured model is available to your Deepgram project. If no transcript appears, check microphone permission, room participation and speech recognition errors first.

Continue to [Run the browser application](browser-call.md).
