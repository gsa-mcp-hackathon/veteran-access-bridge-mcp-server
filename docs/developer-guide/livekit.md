# Set up the LiveKit room connection

LiveKit carries microphone audio from the browser to the worker and carries Avery’s audio back. A browser caller gets a short-lived room token from the application. The worker registers with the LiveKit project so it can receive the call.

1. Sign in to [LiveKit Cloud](https://cloud.livekit.io/) and open or create your own project. From that project, copy its WebSocket URL and obtain an API key and secret from the project’s API keys settings.
2. In the backend and voice worker environments, configure `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` from the **same project**. Keep the secret on the server side. For a temporary local worker, open Bash in the backend repository and enter the values at these prompts. The secret prompt hides what you type.

    ```bash
    read -rp "LiveKit project URL (wss://...): " LIVEKIT_URL
    read -rp "LiveKit API key: " LIVEKIT_API_KEY
    read -rsp "LiveKit API secret: " LIVEKIT_API_SECRET; echo
    export LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET
    ```

3. Leave this terminal open. The next chapter starts the worker after speech is configured. Once started, check the worker log for successful registration in your chosen project. During a call, use the project’s room view to confirm that the browser participant and worker joined the same room.

**If the browser connects but Avery never joins:** check the worker registration, project URL, and the agent name used for dispatch. A browser participant alone proves only that the browser reached LiveKit. [LiveKit connection concepts](https://docs.livekit.io/intro/basics/connect/)

Continue to [Connect Deepgram and start the worker](deepgram.md).
