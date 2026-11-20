const CASE_ID = "DEMO-PC-5000335-001";
const ENCOUNTER_ID = "SE-DEMO-PC-5000335-001-REQ-PC-5000335-001";
const CANONICAL_AVERY_GREETING =
  "Thank you for calling Department of Veterans Affairs, my name is Avery. How can I help you?";
const LEGACY_GREETING_PREFIXES = [
  "thank you for calling synthetic va medical center",
  "thank you for calling department of veterans affairs",
];
let interactionId = null;
let interactionCorrelationId = null;
let interactionCreationError = null;
let voiceSessionId = null;
let livekitRoom = null;
let livekitMicEnabled = false;
let voiceTransportReady = false;
let callOnHold = false;
let eventCursor = null;
let encounterPayload = null;
let selectedOptionId = null;
let callStartedAt = null;
let sseAbort = null;
let speechRecognition = null;
let voiceMode = false;
let recognitionRunning = false;
let awaitingAgentReply = false;
let speakingAgentReply = false;
let voicePlaybackContext = null;
let activeNeuralSource = null;
let liveCallEnded = false;
let micStream = null;
let micAudioContext = null;
let micAnalyser = null;
let micMeterFrame = null;
let turnStartedAt = null;
let canonicalGreetingDelivered = false;
const activityKeys = new Set();
const handledEventIds = new Set();

function recordActivity(key, label, detail, tone = "complete") {
  if (!key || activityKeys.has(key)) return;
  activityKeys.add(key);
  const feed = document.getElementById("workflowActivity");
  if (!feed) return;
  if (activityKeys.size === 1) feed.innerHTML = "";
  const item = document.createElement("div");
  item.className = "activity-item " + tone;
  const dot = document.createElement("i");
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  const text = document.createElement("small");
  title.textContent = label;
  text.textContent = detail || "";
  copy.append(title, text);
  item.append(dot, copy);
  feed.prepend(item);
  const preview = document.getElementById("activityPreview");
  if (preview) {
    const row = document.createElement("div");
    row.className = "preview-step " + (tone === "attention" ? "attention" : "complete");
    const dot = document.createElement("i");
    const copyPreview = document.createElement("span");
    const previewTitle = document.createElement("strong");
    const previewText = document.createElement("small");
    previewTitle.textContent = label;
    previewText.textContent = detail || "";
    copyPreview.append(previewTitle, previewText);
    row.append(dot, copyPreview);
    preview.prepend(row);
    while (preview.children.length > 4) preview.removeChild(preview.lastChild);
  }
}

async function refreshRuntimeProof() {
  const orchDot = document.getElementById("orchestrateProof");
  const orchText = document.getElementById("orchestrateProofText");
  const agentText = document.getElementById("runtimeAgentId");
  const threadText = document.getElementById("runtimeThreadId");
  if (!orchDot || !orchText) return;

  try {
    const readiness = await api("/readiness");
    const remoteReady =
      readiness.orchestrate_runtime_mode === "remote" &&
      readiness.orchestrate_base_url_configured &&
      readiness.orchestrate_auth_mode !== "none";

    if (!interactionId) {
      orchDot.className = "proof " + (remoteReady ? "pending" : "error");
      orchText.textContent = remoteReady ? "Remote ready / awaiting call" : "Not configured";
      return;
    }

    const runtime = await api("/api/interactions/" + interactionId);
    if (agentText) {
      agentText.textContent = runtime.agent_id || readiness.orchestrate_agent_id || "—";
      agentText.title = agentText.textContent;
    }
    if (threadText) {
      threadText.textContent = runtime.orchestrate_session_id || "Awaiting first Veteran turn";
      threadText.title = threadText.textContent;
    }

    const connected = Boolean(
      remoteReady &&
      runtime.agent_id &&
      runtime.orchestrate_session_id &&
      !runtime.runtime_failure_code
    );
    const failed = Boolean(runtime.runtime_failure_code);
    orchDot.className = "proof " + (failed ? "error" : connected ? "ok" : "pending");
    orchText.textContent = failed
      ? "Runtime error: " + runtime.runtime_failure_code
      : connected
        ? "Connected"
        : remoteReady
          ? "Remote ready / awaiting first turn"
          : "Not configured";
  } catch (error) {
    orchDot.className = "proof error";
    orchText.textContent = "Status unavailable";
  }
}

async function reconcileConversationHistory() {
  if (!interactionId) return;
  try {
    const response = await fetch(
      "/api/interactions/" + interactionId + "/events?once=1",
      {headers: headers()}
    );
    if (!response.ok) return;
    const text = await response.text();
    text.split("\n\n").filter(Boolean).forEach(parseSseFrame);
  } catch (error) {
    console.warn("Unable to reconcile conversation history", error);
  }
}

async function refreshVoiceReadiness() {
  const status = document.getElementById("voiceStatus");
  const state = document.getElementById("ttsState");
  const button = document.getElementById("voiceToggleBtn");
  try {
    const response = await fetch("/api/voice/status", {headers: headers()});
    const body = await response.json();
    const transport = body.transport || {};
    const provider = transport.provider || "UNCONFIGURED";
    if (transport.configured) {
      const browserVoice = transport.mode === "BROWSER_WEBRTC";
      status.textContent = browserVoice
        ? "Avery WebRTC ready • " + provider
        : "Avery phone channel ready • " + provider;
      status.className = "diagnostic-good";
      state.textContent = browserVoice
        ? "WebRTC media • Avery"
        : "Phone/SIP • Orchestrate agent";
      state.className = "diagnostic-good";
      voiceTransportReady = Boolean(browserVoice && transport.browser_softphone_enabled);
      button.disabled = false;
      button.title = voiceTransportReady
        ? "Connect Veteran microphone to Avery through LiveKit"
        : "Voice transport is not browser-ready yet; click to see the current configuration status";
    } else {
      status.textContent = "Voice transport pending";
      status.className = "diagnostic-warn";
      state.textContent = "Avery agent connected";
      state.className = "diagnostic-good";
      voiceTransportReady = false;
      button.disabled = false;
      button.title = "Voice transport is not ready; click to check configuration";
    }
  } catch (error) {
    status.textContent = "Voice transport status unavailable";
    status.className = "diagnostic-warn";
    voiceTransportReady = false;
    if (button) {
      button.disabled = false;
      button.title = "Voice readiness check failed; click to retry the connection";
    }
  }
}

function setMicState(label) {
  const el = document.getElementById("micState");
  if (el) el.textContent = label;
}

async function startMicMeter(mediaTrack = null) {
  if (micStream) return;
  try {
    if (!mediaTrack) {
      throw new Error("LiveKit microphone track is not available for metering.");
    }
    micStream = new MediaStream([mediaTrack]);
    micAudioContext = new AudioContext();
    const source = micAudioContext.createMediaStreamSource(micStream);
    micAnalyser = micAudioContext.createAnalyser();
    micAnalyser.fftSize = 256;
    source.connect(micAnalyser);
    const data = new Uint8Array(micAnalyser.frequencyBinCount);
    const bar = document.getElementById("micLevelBar");
    const draw = function () {
      if (!micAnalyser) return;
      micAnalyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const sample of data) peak = Math.max(peak, Math.abs(sample - 128));
      const pct = Math.min(100, Math.round((peak / 64) * 100));
      if (bar) bar.style.width = pct + "%";
      const veteranMeter = document.querySelector(".veteran-audio-meter");
      const veteranWave = document.querySelector(".veteran-wave");
      const veteranMicStatus = document.getElementById("veteranMicStatus");
      if (veteranMeter && veteranWave) {
        const level = Math.max(0.12, pct / 100);
        veteranWave.style.setProperty("--veteran-level", String(level));
        veteranMeter.classList.toggle("listening", pct > 4);
      }
      if (veteranMicStatus) {
        veteranMicStatus.textContent = pct > 4 ? "Speaking" : "Listening";
      }
      micMeterFrame = requestAnimationFrame(draw);
    };
    setMicState("Mic connected");
    draw();
  } catch (error) {
    setMicState("Mic unavailable");
  }
}

function stopMicMeter() {
  if (micMeterFrame) cancelAnimationFrame(micMeterFrame);
  micMeterFrame = null;
  // The meter observes the LiveKit microphone track; LiveKit owns its lifecycle.
  micStream = null;
  if (micAudioContext) micAudioContext.close();
  micAudioContext = null;
  micAnalyser = null;
  const bar = document.getElementById("micLevelBar");
  if (bar) bar.style.width = "0%";
  const veteranMeter = document.querySelector(".veteran-audio-meter");
  const veteranWave = document.querySelector(".veteran-wave");
  const veteranMicStatus = document.getElementById("veteranMicStatus");
  if (veteranMeter) veteranMeter.classList.remove("listening");
  if (veteranWave) veteranWave.style.setProperty("--veteran-level", "0.12");
  if (veteranMicStatus) veteranMicStatus.textContent = "Waiting";
  setMicState("Not listening");
}

function setTurnLatency(label) {
  const el = document.getElementById("turnLatency");
  if (el) el.textContent = label;
}

function voiceApi() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function setPresence(person, state, active = false) {
  const wrap = document.getElementById(person + "Presence");
  const text = document.getElementById(person + "PresenceText");
  if (wrap) wrap.classList.toggle("active", active);
  if (text) text.textContent = state;
}

function chooseNaturalVoice() {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices() || [];
  if (!voices.length) return null;
  const preferred = [
    "Microsoft Aria Online (Natural) - English (United States)",
    "Microsoft Jenny Online (Natural) - English (United States)",
    "Microsoft Guy Online (Natural) - English (United States)",
    "Google US English",
    "Samantha",
    "Alex",
  ];
  for (const name of preferred) {
    const match = voices.find(function (voice) { return voice.name === name; });
    if (match) return match;
  }
  return voices.find(function (voice) {
    return voice.lang && voice.lang.toLowerCase().startsWith("en-us");
  }) || voices.find(function (voice) {
    return voice.lang && voice.lang.toLowerCase().startsWith("en");
  }) || voices[0];
}

function setVoiceStatus(label, active = false) {
  const status = document.getElementById("voiceStatus");
  if (status) status.textContent = label;
}

function stopRecognition() {
  if (!speechRecognition || !recognitionRunning) return;
  try { speechRecognition.stop(); } catch (error) {
    console.warn("Unable to stop speech recognition", error);
  }
}

function startRecognition() {
  // LiveKit/Deepgram owns STT for WebRTC calls. Browser recognition is only a
  // non-WebRTC fallback and must never run in parallel with the worker.
  if (livekitRoom || !voiceMode || !speechRecognition || recognitionRunning ||
      awaitingAgentReply || speakingAgentReply) return;
  try {
    speechRecognition.start();
  } catch (error) {
    console.warn("Unable to start speech recognition", error);
  }
}

function finishAverySpeech() {
  speakingAgentReply = false;
  setPresence("avery", "Listening", false);
  setPresence("veteran", "Your turn", true);
  setVoiceStatus("Listening for Veteran", true);
  window.setTimeout(startRecognition, 600);
}

async function unlockVoicePlayback() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return false;
  try {
    if (!voicePlaybackContext) voicePlaybackContext = new AudioContextClass();
    if (voicePlaybackContext.state === "suspended") {
      await voicePlaybackContext.resume();
    }
    return voicePlaybackContext.state === "running";
  } catch (error) {
    console.warn("Unable to unlock Avery audio playback", error);
    return false;
  }
}

function stopActiveNeuralPlayback() {
  if (!activeNeuralSource) return;
  const source = activeNeuralSource;
  activeNeuralSource = null;
  source.onended = null;
  try { source.stop(0); } catch (error) {
    console.warn("Unable to stop Avery neural playback", error);
  }
  try { source.disconnect(); } catch (error) {
    console.warn("Unable to disconnect Avery neural playback", error);
  }
}

async function playNeuralAudio(blob) {
  if (!voicePlaybackContext || voicePlaybackContext.state !== "running") {
    const unlocked = await unlockVoicePlayback();
    if (!unlocked) throw new Error("Browser audio playback is not unlocked");
  }

  const bytes = await blob.arrayBuffer();
  const buffer = await voicePlaybackContext.decodeAudioData(bytes.slice(0));
  if (liveCallEnded || !voiceMode) return;

  stopActiveNeuralPlayback();
  const source = voicePlaybackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(voicePlaybackContext.destination);
  activeNeuralSource = source;
  source.onended = function () {
    if (activeNeuralSource === source) activeNeuralSource = null;
    try { source.disconnect(); } catch (error) {
      console.warn("Unable to disconnect completed Avery playback", error);
    }
    if (!liveCallEnded && voiceMode) finishAverySpeech();
  };
  try {
    source.start(0);
  } catch (error) {
    if (activeNeuralSource === source) activeNeuralSource = null;
    try { source.disconnect(); } catch (disconnectError) {
      console.warn("Unable to disconnect failed Avery playback", disconnectError);
    }
    throw error;
  }
}

function speakWithBrowserFallback(text) {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Audio unavailable", false);
    toast("Avery's audio could not play in this browser.", true);
    finishAverySpeech();
    return;
  }

  setVoiceStatus("Avery speaking • Browser fallback", true);
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const naturalVoice = chooseNaturalVoice();
  if (naturalVoice) utterance.voice = naturalVoice;
  utterance.rate = 0.96;
  utterance.pitch = 1.02;
  utterance.onend = finishAverySpeech;
  utterance.onerror = function (event) {
    if (!liveCallEnded && voiceMode) {
      console.warn("Browser speech synthesis failed", event);
      setVoiceStatus("Audio unavailable", false);
      toast("Avery's audio could not play. Check browser audio permissions.", true);
    }
    finishAverySpeech();
  };
  window.speechSynthesis.speak(utterance);
}

async function speakAgentReply(text) {
  if (!voiceMode || !text) {
    awaitingAgentReply = false;
    startRecognition();
    return;
  }

  stopRecognition();
  speakingAgentReply = true;
  awaitingAgentReply = false;
  setVoiceStatus("Avery speaking", true);
  setPresence("avery", "Speaking", true);
  setPresence("veteran", "Listening", false);

  try {
    const response = await fetch("/api/voice/synthesize", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({case_id: CASE_ID, text: text}),
    });
    if (!response.ok) throw new Error("Neural voice unavailable");

    const blob = await response.blob();
    if (liveCallEnded || !voiceMode) return;

    setVoiceStatus("Avery speaking • Neural voice", true);
    await playNeuralAudio(blob);
  } catch (error) {
    console.warn("Neural TTS unavailable; browser fallback disabled.", error);
    setVoiceStatus("Neural voice unavailable", false);
    toast("Avery neural voice is unavailable. Browser fallback is disabled.", true);
    finishAverySpeech();
  }
}

function stripLeadingGreeting(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return "";
  const lower = trimmed.toLowerCase();
  const canonicalLower = CANONICAL_AVERY_GREETING.toLowerCase();
  if (lower.startsWith(canonicalLower)) {
    return trimmed.slice(CANONICAL_AVERY_GREETING.length).trim();
  }
  for (const prefix of LEGACY_GREETING_PREFIXES) {
    if (lower.startsWith(prefix)) {
      const helpPrompt = "how can i help you?";
      const helpEnd = lower.indexOf(helpPrompt);
      if (helpEnd >= 0) {
        return trimmed.slice(helpEnd + helpPrompt.length).trim();
      }
      const sentenceBreak = trimmed.indexOf(". ");
      if (sentenceBreak >= 0) {
        return trimmed.slice(sentenceBreak + 2).trim();
      }
      return "";
    }
  }
  return trimmed;
}

function normalizeAveryReply(text) {
  const stripped = stripLeadingGreeting(text);
  if (!canonicalGreetingDelivered) {
    canonicalGreetingDelivered = true;
    if (!stripped) {
      return CANONICAL_AVERY_GREETING;
    }
    const normalizedLower = stripped.toLowerCase();
    if (normalizedLower.startsWith(CANONICAL_AVERY_GREETING.toLowerCase())) {
      return stripped;
    }
    return CANONICAL_AVERY_GREETING + " " + stripped;
  }
  if (!stripped) {
    return "Yes, I can assist you with scheduling an appointment. For verification purposes, can I have your last name, last4, and date of birth?";
  }
  return stripped;
}

function configureVoiceMode() {
  const Recognition = voiceApi();
  const support = document.getElementById("voiceSupportText");
  const button = document.getElementById("voiceToggleBtn");

  if (!Recognition) {
    if (support) {
      support.textContent = "Voice recognition is not supported in this browser. Use typed input or open the demo in a supported Chromium browser.";
    }
    if (button) button.disabled = true;
    setVoiceStatus("Voice unavailable", false);
    return;
  }

  speechRecognition = new Recognition();
  speechRecognition.lang = "en-US";
  speechRecognition.continuous = false;
  speechRecognition.interimResults = true;

  speechRecognition.onstart = function () {
    recognitionRunning = true;
    setPresence("avery", "Listening", false);
    setPresence("veteran", "Listening for speech", true);
    setVoiceStatus("Listening for Veteran", true);
    setMicState("Listening");
  };

  speechRecognition.onspeechstart = function () {
    setPresence("veteran", "Speaking", true);
    setVoiceStatus("Veteran speaking", true);
    setMicState("Hearing you");
  };

  speechRecognition.onspeechend = function () {
    setPresence("veteran", "Processing speech", true);
    setVoiceStatus("Processing Veteran speech", true);
    setMicState("Processing speech");
  };

  speechRecognition.onend = function () {
    recognitionRunning = false;
    if (!speakingAgentReply) setPresence("veteran", "Waiting", false);
    if (voiceMode && !awaitingAgentReply && !speakingAgentReply) {
      window.setTimeout(startRecognition, 300);
    }
  };

  speechRecognition.onerror = function (event) {
    recognitionRunning = false;
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      voiceMode = false;
      setPresence("veteran", "Microphone blocked", false);
      setVoiceStatus("Microphone permission required", false);
      toast("Microphone permission is required for voice mode.", true);
      return;
    }
    if (event.error !== "no-speech" && event.error !== "aborted") {
      setVoiceStatus("Voice error", voiceMode);
      toast("Voice recognition error: " + event.error, true);
    }
  };

  speechRecognition.onresult = async function (event) {
    let interim = "";
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript.trim();
      if (event.results[i].isFinal) finalText += (finalText ? " " : "") + text;
      else interim += (interim ? " " : "") + text;
    }

    const interimEl = document.getElementById("interimTranscript");
    if (interimEl) {
      interimEl.hidden = !interim;
      interimEl.textContent = interim ? "Hearing: " + interim : "";
    }

    if (!finalText) return;
    if (interimEl) {
      interimEl.hidden = true;
      interimEl.textContent = "";
    }

    awaitingAgentReply = true;
    turnStartedAt = performance.now();
    setTurnLatency("Processing…");
    stopRecognition();
    setPresence("veteran", "Turn captured", false);
    setPresence("avery", "Thinking", true);
    setVoiceStatus("Avery preparing response", true);
    await sendMessage(finalText, {fromVoice: true});
  };
}

async function toggleVoiceMode() {
  if (liveCallEnded) {
    toast("This call has ended. Start a new interaction to use voice.");
    return;
  }
  if (!speechRecognition) return;

  if (voiceMode) {
    voiceMode = false;
    awaitingAgentReply = false;
    speakingAgentReply = false;
    stopRecognition();
    stopActiveNeuralPlayback();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    if (voicePlaybackContext && voicePlaybackContext.state === "running") {
      voicePlaybackContext.suspend().catch(function (error) {
        console.warn("Unable to suspend Avery audio playback", error);
      });
    }
    stopMicMeter();
    setPresence("avery", "Ready", false);
    setPresence("veteran", "Waiting", false);
    setVoiceStatus("Voice ready", false);
    return;
  }

  const playbackUnlocked = await unlockVoicePlayback();
  if (!playbackUnlocked && !("speechSynthesis" in window)) {
    setVoiceStatus("Audio unavailable", false);
    toast("Browser audio playback is unavailable.", true);
    return;
  }

  voiceMode = true;
  if (!interactionId) {
    awaitingAgentReply = true;
    setPresence("avery", "Answering", true);
    setPresence("veteran", "Waiting", false);
    setVoiceStatus("Avery answering", true);
    await startInteraction("PHONE", "", {agentOpening: true});
  }
  if (!interactionId) {
    voiceMode = false;
    setVoiceStatus("Voice ready", false);
    return;
  }

  setVoiceStatus("Listening", true);
  startRecognition();
}

function headers(extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-Demo-Role": "SCHEDULER",
    "X-Demo-Actor": "msa-demo-01",
    "X-Demo-Case": CASE_ID,
    ...extra,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {...headers(), ...(options.headers || {})},
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || "Request failed");
    error.body = body;
    error.status = response.status;
    throw error;
  }
  return body;
}


function updateLiveKitMuteButton() {
  const button = document.getElementById("voiceToggleBtn");
  if (!button) return;
  const label = button.querySelector("small");
  if (label) label.textContent = livekitMicEnabled ? "Mute" : "Unmute";
  button.classList.toggle("active", livekitMicEnabled);
}

async function ensureWebRtcVoiceSession() {
  if (!interactionId) {
    await startInteraction("PHONE", "", {agentOpening: true});
  }
  if (!interactionId) {
    throw new Error(
      interactionCreationError || "Unable to create the live interaction."
    );
  }
  const runtime = await api("/api/interactions/" + interactionId);
  if (runtime.runtime_failure_code) {
    throw new Error(
      "Avery runtime unavailable: " + runtime.runtime_failure_code
    );
  }
  if (voiceSessionId) return voiceSessionId;

  const created = await api("/api/voice-sessions", {
    method: "POST",
    body: JSON.stringify({
      interaction_id: interactionId,
      correlation_id: interactionCorrelationId || ("corr-" + interactionId),
      case_id: CASE_ID,
      scheduling_encounter_id: ENCOUNTER_ID,
      transport: "WEBRTC",
    }),
  });
  voiceSessionId = created.voice_session_id;
  return voiceSessionId;
}

async function connectLiveKitVoice() {
  if (!window.LivekitClient) {
    throw new Error("LiveKit browser client failed to load.");
  }
  const sessionId = await ensureWebRtcVoiceSession();
  const token = await api(
    "/api/voice-sessions/" + sessionId + "/webrtc-token",
    {method: "POST", body: JSON.stringify({})}
  );

  const room = new window.LivekitClient.Room({
    adaptiveStream: true,
    dynacast: true,
  });
  room.on(
    window.LivekitClient.RoomEvent.LocalTrackSubscribed,
    function (publication) {
      if (publication.source !== window.LivekitClient.Track.Source.Microphone) return;
      setMicState("LiveKit microphone subscribed by Avery");
      console.info("Avery subscribed to Veteran microphone", publication.trackSid);
    }
  );
  room.on(window.LivekitClient.RoomEvent.TrackSubscribed, function (track) {
    if (track.kind !== window.LivekitClient.Track.Kind.Audio) return;
    const element = track.attach();
    element.autoplay = true;
    element.dataset.vabRemoteAudio = "true";
    document.body.appendChild(element);
    const wave = document.getElementById("voiceWave");
    if (wave) wave.classList.add("remote-audio");
    setPresence("avery", "Speaking", true);
  });
  room.on(window.LivekitClient.RoomEvent.TrackUnsubscribed, function (track) {
    track.detach().forEach(function (element) { element.remove(); });
    const wave = document.getElementById("voiceWave");
    if (wave) wave.classList.remove("remote-audio");
    setPresence("avery", "Listening", false);
  });
  room.on(window.LivekitClient.RoomEvent.Disconnected, function () {
    livekitRoom = null;
    livekitMicEnabled = false;
    updateLiveKitMuteButton();
    setMicState("Disconnected");
  });

  await room.connect(token.server_url, token.participant_token);
  livekitRoom = room;
  const micPublication = await room.localParticipant.setMicrophoneEnabled(true);
  if (!micPublication || !micPublication.track) {
    throw new Error("LiveKit did not publish the Veteran microphone track.");
  }
  livekitMicEnabled = true;
  callOnHold = false;
  updateLiveKitMuteButton();
  updateHoldButton();
  await startMicMeter(micPublication.track.mediaStreamTrack);
  setMicState("LiveKit microphone published");

  await api("/api/voice-sessions/" + sessionId + "/events", {
    method: "POST",
    body: JSON.stringify({
      event_type: "CONNECTED",
      provider_session_id: token.room_name,
      payload: {
        provider: "LIVEKIT",
        participant_identity: token.participant_identity,
      },
    }),
  });
  voiceMode = true;
  awaitingAgentReply = false;
  speakingAgentReply = false;
  stopRecognition();
  toast("Veteran microphone connected to Avery's WebRTC session.");
  await refreshRuntimeProof();
  await reconcileConversationHistory();
}

async function toggleLiveKitVoice() {
  if (liveCallEnded) {
    toast("This call has ended. Start a new interaction to use voice.");
    return;
  }
  try {
    if (!livekitRoom) {
      if (!voiceTransportReady) await refreshVoiceReadiness();
      await connectLiveKitVoice();
      return;
    }
    if (callOnHold) {
      toast("Resume the call before changing the microphone state.");
      return;
    }
    livekitMicEnabled = !livekitMicEnabled;
    await livekitRoom.localParticipant.setMicrophoneEnabled(livekitMicEnabled);
    updateLiveKitMuteButton();
    setMicState(livekitMicEnabled ? "LiveKit microphone connected" : "Muted");
  } catch (error) {
    console.error("LiveKit voice connection failed", error);
    toast("WebRTC voice failed: " + error.message, true);
  }
}

async function disconnectLiveKitVoice() {
  if (!livekitRoom) return;
  const room = livekitRoom;
  livekitRoom = null;
  livekitMicEnabled = false;
  updateLiveKitMuteButton();
  callOnHold = false;
  updateHoldButton();
  stopMicMeter();
  const wave = document.getElementById("voiceWave");
  if (wave) wave.classList.remove("remote-audio", "listening", "speaking");
  await room.disconnect();
  document.querySelectorAll("[data-vab-remote-audio='true']").forEach(function (element) {
    element.remove();
  });
  voiceMode = false;
  awaitingAgentReply = false;
  speakingAgentReply = false;
  stopRecognition();
}


function updateHoldButton() {
  const button = document.getElementById("holdCallBtn");
  if (!button) return;
  const label = button.querySelector("small");
  const icon = button.querySelector("span");
  if (label) label.textContent = callOnHold ? "Resume" : "Hold";
  if (icon) icon.textContent = callOnHold ? "▶" : "Ⅱ";
  button.classList.toggle("active", callOnHold);
}

async function toggleHoldCall() {
  if (liveCallEnded) {
    toast("This call has ended.");
    return;
  }
  if (!interactionId) await openIncomingCall();
  if (!interactionId) return;

  callOnHold = !callOnHold;
  if (livekitRoom) {
    await livekitRoom.localParticipant.setMicrophoneEnabled(!callOnHold && livekitMicEnabled);
  }
  updateHoldButton();
  if (callOnHold) {
    stopMicMeter();
  } else if (livekitRoom) {
    await startMicMeter();
  }
  setMicState(callOnHold ? "Call on hold" : (livekitRoom ? "LiveKit microphone connected" : "MSA monitoring"));
  setInteractionStatus(callOnHold ? "CALL ON HOLD" : "AGENT HANDLING", callOnHold ? "attention" : "handling");
  recordActivity(
    "hold-" + Date.now(),
    callOnHold ? "Call placed on hold" : "Call resumed",
    callOnHold ? "Veteran microphone paused while the live session remains connected." : "Live call resumed with preserved context.",
    "human"
  );
  toast(callOnHold ? "Call placed on hold." : "Call resumed.");
}

function buildVoiceWave() {
  const wave = document.getElementById("voiceWave");
  if (!wave || wave.children.length) return;
  for (let i = 0; i < 24; i += 1) {
    const bar = document.createElement("i");
    bar.style.setProperty("--bar-index", String(i));
    wave.appendChild(bar);
  }
}

function pulseAveryWave() {
  const wave = document.getElementById("voiceWave");
  if (!wave) return;
  wave.classList.add("speaking");
  setPresence("avery", "Speaking", true);
  window.setTimeout(function () {
    wave.classList.remove("speaking");
    if (livekitRoom) setPresence("avery", "Listening", false);
  }, 1800);
}

function operationalMarkup(view) {
  const eligible = encounterPayload?.calendar?.filter(function (slot) {
    return ["ELIGIBLE", "SELECTED", "VERIFIED", "SIMULATED_BOOKED", "REVIEW_REQUIRED"].includes(slot.state);
  }).length || 0;
  const excluded = encounterPayload?.calendar?.filter(function (slot) { return slot.state === "EXCLUDED"; }).length || 0;
  const views = {
    dashboard: {
      title: "Operations Dashboard",
      subtitle: "Current scheduling workload and Avery supervision state.",
      body: '<div class="ops-metric-grid">' +
        '<article><span>Active calls</span><strong>' + (liveCallEnded ? "0" : "1") + '</strong><small>Avery handling: ' + (liveCallEnded ? "0" : "1") + '</small></article>' +
        '<article><span>Queued calls</span><strong>3</strong><small>Oldest wait: 00:05</small></article>' +
        '<article><span>Eligible options</span><strong>' + eligible + '</strong><small>Governed availability</small></article>' +
        '<article><span>Needs review</span><strong>' + excluded + '</strong><small>Excluded / policy evidence</small></article>' +
        '</div><div class="ops-table"><strong>Live workload</strong><div class="ops-row"><span>Mariano Ruelas</span><span>Primary Care</span><span>' + (liveCallEnded ? "Ended" : "Avery handling") + '</span><button data-nav-jump="live">Open call</button></div></div>'
    },
    queue: {
      title: "Call Queue",
      subtitle: "MSA queue ordered by live and waiting calls.",
      body: '<div class="ops-table"><div class="ops-row heading"><span>Veteran</span><span>Service</span><span>Status</span><span>Action</span></div>' +
        '<div class="ops-row"><span>Mariano Ruelas</span><span>Primary Care</span><span>' + (liveCallEnded ? "Ended" : "Live • Avery") + '</span><button data-nav-jump="live">Monitor</button></div>' +
        '<div class="ops-row"><span>Carla Torres</span><span>Specialty Care</span><span>Waiting • 00:01</span><button data-queue-action="Carla Torres">Preview</button></div>' +
        '<div class="ops-row"><span>David Wilson</span><span>Primary Care</span><span>Waiting • 00:03</span><button data-queue-action="David Wilson">Preview</button></div>' +
        '<div class="ops-row"><span>Susan Lee</span><span>Specialty Care</span><span>Waiting • 00:05</span><button data-queue-action="Susan Lee">Preview</button></div></div>'
    },
    encounters: {
      title: "Scheduling Encounters",
      subtitle: "Governed scheduling context and lifecycle state.",
      body: '<div class="ops-table"><div class="ops-row heading"><span>Encounter</span><span>Domain</span><span>State</span><span>Action</span></div>' +
        '<div class="ops-row"><span>' + ENCOUNTER_ID + '</span><span>Primary Care</span><span>' + (encounterPayload?.demo_a?.state || "OPTIONS READY").replaceAll("_"," ") + '</span><button data-open-panel-from-view="encounterPanel">Open encounter</button></div></div>'
    },
    analytics: {
      title: "Access Analytics",
      subtitle: "Synthetic operational measures from the active prototype session.",
      body: '<div class="ops-metric-grid">' +
        '<article><span>Eligible slots</span><strong>' + eligible + '</strong><small>Current encounter</small></article>' +
        '<article><span>Excluded slots</span><strong>' + excluded + '</strong><small>Governed exclusions</small></article>' +
        '<article><span>Warm handoffs</span><strong>' + (document.getElementById("humanControl")?.textContent.includes("MONITORING") ? "0" : "1") + '</strong><small>Current session</small></article>' +
        '<article><span>Voice transport</span><strong>' + (livekitRoom ? "Live" : (voiceTransportReady ? "Ready" : "Offline")) + '</strong><small>LiveKit / Deepgram path</small></article></div>'
    },
    reports: {
      title: "Reports",
      subtitle: "Session-ready operational summaries for review.",
      body: '<div class="ops-report-list"><button data-report="call">Call summary <span>Current interaction transcript, state, and handoff status</span></button>' +
        '<button data-report="access">Access evidence <span>Eligible comparator, exclusions, and governed options</span></button>' +
        '<button data-report="audit">Audit bundle <span>Observed Avery activity and human-control events</span></button></div>'
    },
    settings: {
      title: "Workspace Settings",
      subtitle: "Runtime status for this local prototype.",
      body: '<div class="ops-settings">' +
        '<div><span>Voice gateway</span><strong>' + (voiceTransportReady ? "LiveKit ready" : "Not ready") + '</strong></div>' +
        '<div><span>Voice session</span><strong>' + (livekitRoom ? "Connected" : "Disconnected") + '</strong></div>' +
        '<div><span>Production writes</span><strong>Disabled</strong></div>' +
        '<div><span>Data mode</span><strong>Synthetic only</strong></div></div>'
    }
  };
  return views[view] || views.dashboard;
}

function showNavigationView(view) {
  const operational = document.getElementById("operationalView");
  const callCard = document.querySelector(".call-card");
  const conversation = document.querySelector(".conversation-card");
  const rail = document.getElementById("monitoringRail");

  document.querySelectorAll(".primary-nav [data-nav]").forEach(function (button) {
    button.classList.toggle("active", button.dataset.nav === view);
  });

  if (view === "live") {
    if (operational) operational.hidden = true;
    if (callCard) callCard.hidden = false;
    if (conversation) conversation.hidden = false;
    if (rail) rail.hidden = false;
    return;
  }

  if (callCard) callCard.hidden = true;
  if (conversation) conversation.hidden = true;
  if (rail) rail.hidden = true;
  const config = operationalMarkup(view);
  operational.innerHTML = '<div class="ops-heading"><div><span class="eyebrow">MSA Workspace</span><h1>' + config.title + '</h1><p>' + config.subtitle + '</p></div><button type="button" data-nav-jump="live">Return to Live Call</button></div>' + config.body;
  operational.hidden = false;

  operational.querySelectorAll("[data-nav-jump]").forEach(function (button) {
    button.onclick = function () { showNavigationView(button.dataset.navJump); };
  });
  operational.querySelectorAll("[data-open-panel-from-view]").forEach(function (button) {
    button.onclick = function () {
      showNavigationView("live");
      openWorkPanel(button.dataset.openPanelFromView);
    };
  });
  operational.querySelectorAll("[data-queue-action]").forEach(function (button) {
    button.onclick = function () {
      toast(button.dataset.queueAction + " is waiting in the synthetic queue. Live call remains with Mariano Ruelas.");
    };
  });
  operational.querySelectorAll("[data-report]").forEach(function (button) {
    button.onclick = function () {
      toast("Prepared " + button.dataset.report + " report from the current synthetic session.");
    };
  });
}

function focusMonitoringCard(targetId, button) {
  document.querySelectorAll(".rail-tabs button").forEach(function (tab) { tab.classList.remove("active"); });
  if (button) button.classList.add("active");
  const target = document.getElementById(targetId);
  if (!target) return;
  document.querySelectorAll(".monitor-card").forEach(function (card) { card.classList.remove("focused"); });
  target.classList.add("focused");
  target.scrollIntoView({behavior: "smooth", block: "nearest"});
  window.setTimeout(function () { target.classList.remove("focused"); }, 1400);
}

function toast(message, bad = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = bad ? "show bad" : "show";
  window.setTimeout(function () { el.className = ""; }, 2800);
}

function fmt(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function fmtDate(value) {
  if (!value) return "—";
  return new Date(value + "T12:00:00").toLocaleDateString([], {
    month: "short", day: "numeric", year: "numeric",
  });
}

function setInteractionStatus(label, css) {
  ["interactionStatus", "queueStatus"].forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = label;
    el.className = "status-pill " + (css || "");
  });
  const visible = document.querySelector(".call-state span");
  if (visible) visible.textContent = label.replaceAll("_", " ");
}

function appendTranscript(actor, text, kind) {
  if (!text) return;
  const wrap = document.createElement("div");
  wrap.className = "transcript-message " + (kind || "agent");
  const label = document.createElement("span");
  label.textContent = actor;
  const body = document.createElement("p");
  body.textContent = text;
  wrap.append(label, body);
  const transcript = document.getElementById("transcript");
  transcript.appendChild(wrap);
  transcript.scrollTop = transcript.scrollHeight;
}

function calendarCard(slot) {
  let meta = "";
  if (slot.preference_rank) {
    meta += '<span class="meta-chip">Preference #' + slot.preference_rank + "</span>";
  }
  if (slot.is_access_comparator) {
    meta += '<span class="meta-chip comparator">Access comparator</span>';
  }
  let reasons = "";
  if (slot.state === "EXCLUDED" && slot.eligibility_reasons.length) {
    reasons = '<div class="exclusion-reasons">' +
      slot.eligibility_reasons.map(function (reason) {
        return "<span>" + reason.replaceAll("_", " ") + "</span>";
      }).join("") + "</div>";
  }
  const selectButton = slot.state === "ELIGIBLE"
    ? '<button class="compact select-option" data-option-id="' +
      slot.option_id + '">Select option</button>'
    : "";
  return '<article class="slot-card state-' + slot.state.toLowerCase() + '">' +
    '<div class="slot-card-top"><div><span class="slot-source">' +
    slot.source_system + "</span><strong>" + fmt(slot.slot_start) +
    '</strong></div><span class="state-label">' +
    slot.state.replaceAll("_", " ") + "</span></div><p>" +
    (slot.resource_name || "Primary Care resource") + " • " +
    (slot.modality || "modality not specified") +
    '</p><div class="slot-meta">' + meta + selectButton + "</div>" +
    reasons + "</article>";
}

function nextActionForState(state) {
  const actions = {
    OPTIONS_READY: "Select one governed eligible option.",
    SLOT_SELECTED: "Verify the selected slot.",
    SLOT_VERIFIED: "Record the Veteran's explicit confirmation.",
    VETERAN_CONFIRMED: "MSA approval is required.",
    MSA_APPROVAL_PENDING: "MSA approval is required.",
    MSA_APPROVED: "Record the simulated booking.",
    SIMULATED_BOOKED: "No further booking action.",
  };
  return actions[state] || "Review governed options.";
}

function renderDemoState(record) {
  if (!record) return;
  selectedOptionId = record.selected_option_id;
  document.getElementById("demoState").textContent = record.state.replaceAll("_", " ");
  document.getElementById("demoNextAction").textContent = nextActionForState(record.state);

  document.getElementById("verifyBtn").disabled = record.state !== "SLOT_SELECTED";
  document.getElementById("confirmBtn").disabled = record.state !== "SLOT_VERIFIED";
  document.getElementById("approveBtn").disabled =
    !["VETERAN_CONFIRMED", "MSA_APPROVAL_PENDING"].includes(record.state);
  document.getElementById("bookBtn").disabled = record.state !== "MSA_APPROVED";

  const result = document.getElementById("bookingResult");
  if (record.state === "SIMULATED_BOOKED") {
    result.hidden = false;
    result.innerHTML = "<strong>Simulated booking recorded</strong>" +
      "<p>Booking ID: " + record.booking_id +
      "</p><small>No production scheduling write occurred.</small>";
  } else {
    result.hidden = true;
  }
}

function renderEncounter() {
  if (!encounterPayload) return;
  const encounter = encounterPayload.encounter;
  const calendar = encounterPayload.calendar || [];
  const assessment = encounter.access_standard || {};
  const request = encounter.request || {};
  document.getElementById("encounterState").textContent = encounter.encounter_state || "—";
  document.getElementById("encounterSubtitle").textContent =
    CASE_ID + " • " + encounter.patient_classification + " • " + request.service;
  document.getElementById("requestSource").textContent = request.request_source || "—";
  document.getElementById("canonicalPid").textContent = fmtDate(request.canonical_pid);
  document.getElementById("patientClassification").textContent =
    encounter.patient_classification || "—";
  document.getElementById("railClassification").textContent =
    encounter.patient_classification || "—";

  if (encounter.patient_classification) {
    recordActivity(
      "governed-context-loaded",
      "Governed context loaded",
      "Primary Care context classified as " + encounter.patient_classification + ".",
      "governed"
    );
  }

  const standardDays = assessment.standard_days;
  const waitDays = assessment.earliest_eligible_va_wait_days;
  document.getElementById("accessStandard").textContent =
    standardDays == null ? "—" : standardDays + "-day standard";
  document.getElementById("accessStandardDetail").textContent =
    waitDays == null ? "No eligible comparator" : waitDays + "-day eligible comparator";
  document.getElementById("comparatorWait").textContent =
    waitDays == null ? "—" : waitDays + " days";

  const eligible = calendar.filter(function (item) {
    return ["ELIGIBLE", "SELECTED", "VERIFIED", "SIMULATED_BOOKED", "REVIEW_REQUIRED"]
      .includes(item.state);
  });
  const excluded = calendar.filter(function (item) { return item.state === "EXCLUDED"; });
  document.getElementById("eligibleCount").textContent = String(eligible.length);
  document.getElementById("excludedCount").textContent = String(excluded.length);
  if (calendar.length) {
    recordActivity(
      "availability-retrieved",
      "Raw availability retrieved",
      calendar.length + " candidate slot" + (calendar.length === 1 ? "" : "s") + " evaluated.",
      "system"
    );
    recordActivity(
      "eligibility-updated",
      "Eligibility evaluated",
      eligible.length + " eligible • " + excluded.length + " excluded.",
      "governed"
    );
  }
  document.getElementById("calendarSlots").innerHTML = calendar.map(calendarCard).join("");
  document.querySelectorAll(".select-option").forEach(function (button) {
    button.addEventListener("click", function () {
      runDemoAction("SELECT", button.dataset.optionId);
    });
  });
  renderDemoState(encounterPayload.demo_a);

  const handoff = encounterPayload.handoff || {};
  const conflict = handoff.apparent_conflict;
  const conflictEl = document.getElementById("conflictExplanation");
  if (conflict) {
    conflictEl.hidden = false;
    conflictEl.innerHTML =
      "<strong>Earlier raw slot is not eligible</strong><p>" +
      conflict.explanation + "</p>";
  } else {
    conflictEl.hidden = true;
    conflictEl.textContent = "";
  }
  document.getElementById("nextAction").textContent =
    (handoff.next_permitted_action || "PRESENT_GOVERNED_OPTIONS").replaceAll("_", " ");
  if (handoff.transfer_reason) {
    document.getElementById("handoffReason").textContent = handoff.transfer_reason;
  }

  const result = assessment.wait_standard_exceeded ? "Threshold exceeded" : "Within standard";
  document.getElementById("evidenceSummary").innerHTML =
    "<div><span>Raw slots</span><strong>" + calendar.length +
    "</strong><small>Source availability evaluated</small></div>" +
    "<div><span>Governed eligible</span><strong>" + eligible.length +
    "</strong><small>Eligibility service result</small></div>" +
    "<div><span>Excluded</span><strong>" + excluded.length +
    "</strong><small>Reasons preserved per slot</small></div>" +
    "<div><span>Access result</span><strong>" + result +
    "</strong><small>Preference rank does not alter this result</small></div>";
}

async function refreshEncounter() {
  try {
    encounterPayload = await api("/api/scheduling-encounters/" + CASE_ID);
    renderEncounter();
  } catch (error) {
    toast(error.message, true);
  }
}

function handleEvent(event) {
  if (event.event_id && handledEventIds.has(event.event_id)) return;
  if (event.event_id) handledEventIds.add(event.event_id);
  eventCursor = event.event_id || eventCursor;
  const type = event.event_type;
  const activityLabels = {
    interaction_received: ["Interaction received", "Phone/chat interaction entered the governed workflow.", "system"],
    agent_answered: ["Avery handling", "Avery responded through watsonx Orchestrate while the MSA remains in the live view.", "agent"],
    mcp_tool_called: ["MCP tool called", "Avery invoked an observable MCP tool through watsonx Orchestrate.", "governed"],
    mcp_tool_result: ["MCP tool result", "Observable MCP tool output returned to Avery.", "governed"],
    intent_captured: ["Scheduling intent captured", "Conversation identified the Primary Care scheduling request.", "conversation"],
    preference_captured: ["Preference captured", "Veteran-stated scheduling preference updated.", "conversation"],
    preferred_date_captured: ["Preferred date captured", "Veteran-stated date or window updated.", "conversation"],
    encounter_loaded: ["Governed encounter loaded", "Scheduling Encounter context became available.", "governed"],
    eligibility_updated: ["Eligibility updated", "Deterministic eligibility evidence changed.", "governed"],
    access_assessed: ["Access standard assessed", "Earliest eligible comparator evaluated.", "governed"],
    options_presented: ["Options presented", "Governed eligible options were presented to the Veteran.", "agent"],
    veteran_selected: ["Veteran selected option", "A governed eligible option was selected.", "conversation"],
    slot_verified: ["Slot verified", "Selected slot passed current availability verification.", "governed"],
    veteran_confirmed: ["Veteran confirmed", "Explicit confirmation was recorded.", "conversation"],
    msa_approved: ["MSA approved", "Human approval was recorded.", "human"],
    simulated_booking_recorded: ["Simulated booking recorded", "Synthetic booking completed; no production write occurred.", "human"],
    human_attention_recommended: ["MSA attention recommended", "The workflow requires scheduler attention.", "attention"],
    transfer_requested: ["Warm transfer required", "Agent requested MSA takeover with context preserved.", "attention"],
    msa_joined: ["MSA joined", "Scheduler joined the interaction with context retained.", "human"],
    interaction_ended: ["Interaction ended", "Live interaction closed.", "system"],
  };
  const activity = activityLabels[type];
  if (activity) {
    recordActivity(event.event_id || type, activity[0], activity[1], activity[2]);
  }
  if (type === "interaction_received") {
    const channel = event.payload?.channel;
    const runtimeOwner = event.payload?.runtime_owner;
    if (runtimeOwner === "embedded_orchestrate") {
      setInteractionStatus("ORCHESTRATE ACTIVE", "handling");
    } else if (channel === "CHAT") {
      setInteractionStatus("CHAT ACTIVE", "handling");
    } else {
      setInteractionStatus("INCOMING CALL", "incoming");
    }
  }
  if (type === "preference_captured") {
    const preferred = event.payload?.preferred_time_of_day;
    if (preferred) {
      document.getElementById("preferredTime").textContent =
        preferred.charAt(0) + preferred.slice(1).toLowerCase();
    }
  }
  if (type === "intent_captured") {
    const intent = event.payload?.request_intent;
    if (intent) {
      const fact = document.querySelector("#capturedFacts div:first-child dd");
      if (fact) fact.textContent = intent.replaceAll("_", " ");
    }
  }
  if (type === "veteran_utterance") {
    if (event.payload && event.payload.text) {
      appendTranscript("Veteran", event.payload.text, "veteran");
    }
  }
  if (type === "agent_answered") {
    setInteractionStatus("AGENT HANDLING", "handling");
    if (turnStartedAt != null) {
      const seconds = (performance.now() - turnStartedAt) / 1000;
      setTurnLatency("Reply " + seconds.toFixed(1) + "s");
      turnStartedAt = null;
    }
    if (event.payload && event.payload.text) {
      const replyText = normalizeAveryReply(event.payload.text);
      appendTranscript("Avery", replyText, "agent");
      pulseAveryWave();
      // In WebRTC mode Avery audio is already synthesized by the LiveKit
      // worker. Re-synthesizing the same event in the browser creates duplicate
      // speech and competing turn state.
      if (voiceMode && !livekitRoom) {
        speakAgentReply(replyText);
      } else if (awaitingAgentReply) {
        awaitingAgentReply = false;
      }
    } else if (voiceMode && awaitingAgentReply) {
      awaitingAgentReply = false;
      setVoiceStatus("Listening", true);
      startRecognition();
    }
  }
  if (type === "mcp_tool_called") {
    const toolName = event.payload?.tool_name || "MCP tool";
    const args = event.payload?.arguments;
    const detail = args ? toolName + " • " + String(args) : toolName;
    appendTranscript("Avery → MCP", detail, "tool");
    const mcpDot = document.getElementById("mcpProof");
    const mcpText = document.getElementById("mcpProofText");
    if (mcpDot) mcpDot.className = "proof ok";
    if (mcpText) mcpText.textContent = "Observed: " + toolName;
  }
  if (type === "mcp_tool_result") {
    const toolName = event.payload?.tool_name || "MCP tool";
    const result = event.payload?.result;
    appendTranscript(
      "MCP → Avery",
      result ? toolName + " result: " + String(result) : toolName + " returned a result",
      "tool-result"
    );
  }
  if (type === "human_attention_recommended" && event.payload?.failure_code) {
    appendTranscript(
      "Runtime",
      "Avery could not complete the Orchestrate turn. " +
        "Failure: " + event.payload.failure_code +
        ". Context was preserved for MSA review.",
      "runtime"
    );
  }
  if (type === "human_attention_recommended") {
    setInteractionStatus("ATTENTION RECOMMENDED", "attention");
    document.getElementById("humanControl").textContent = "ATTENTION RECOMMENDED";
    const handoffTab = document.querySelector('[data-panel="handoffPanel"]');
    if (handoffTab) handoffTab.classList.add("attention");
    const state = document.getElementById("handoffPeekState");
    if (state) state.textContent = "Attention recommended";
  }
  if (type === "transfer_requested") {
    setInteractionStatus("HUMAN TAKEOVER REQUESTED", "transfer");
    document.getElementById("humanControl").textContent = "WARM TRANSFER REQUIRED";
    document.getElementById("handoffReason").textContent =
      "Avery is preparing a warm transfer. Review the preserved scheduling context before accepting.";
    document.getElementById("nextAction").textContent = "MSA review / accept transfer";
    const handoffTab = document.querySelector('[data-panel="handoffPanel"]');
    if (handoffTab) handoffTab.classList.add("attention");
    const state = document.getElementById("handoffPeekState");
    if (state) state.textContent = "Warm transfer requested";
  }
  if (type === "msa_joined") setInteractionStatus("MSA JOINED", "joined");
  if (type === "interaction_ended") setInteractionStatus("CALL ENDED", "ended");
  refreshRuntimeProof();
}

function parseSseFrame(frame) {
  const line = frame.split("\n").find(function (item) {
    return item.startsWith("data: ");
  });
  if (!line) return;
  try { handleEvent(JSON.parse(line.slice(6))); } catch (error) {
    console.warn("Unable to parse SSE frame", error);
  }
}

async function connectSse() {
  if (!interactionId) return;
  if (sseAbort) sseAbort.abort();
  sseAbort = new AbortController();
  try {
    const extra = eventCursor ? {"Last-Event-ID": eventCursor} : {};
    const response = await fetch(
      "/api/interactions/" + interactionId + "/events",
      {headers: headers(extra), signal: sseAbort.signal}
    );
    if (!response.ok || !response.body) throw new Error("Live event stream unavailable");
    const connectionDot = document.getElementById("connectionDot");
    const connectionText = document.getElementById("connectionText");
    if (connectionDot) connectionDot.classList.add("live");
    if (connectionText) connectionText.textContent = "Live stream";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, {stream: true});
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      frames.forEach(parseSseFrame);
    }
  } catch (error) {
    if (error.name === "AbortError") return;
    const connectionDot = document.getElementById("connectionDot");
    const connectionText = document.getElementById("connectionText");
    if (connectionDot) connectionDot.classList.remove("live");
    if (connectionText) connectionText.textContent = "Reconnecting";
    window.setTimeout(connectSse, 1500);
  }
}

async function startInteraction(channel, initialMessage, options = {}) {
  if (interactionId) {
    toast("An interaction is already active. Reload to start another demo.");
    return;
  }

  if (channel === "PHONE") liveCallEnded = false;

  eventCursor = null;
  interactionCreationError = null;
  canonicalGreetingDelivered = false;
  setInteractionStatus(
    channel === "CHAT" ? "CHAT STARTING" : "AGENT ANSWERING",
    channel === "CHAT" ? "handling" : "answering"
  );
  if (initialMessage) {
    appendTranscript("Veteran", initialMessage, "veteran");
  }

  try {
    const created = await api("/api/interactions", {
      method: "POST",
      body: JSON.stringify({
        case_id: CASE_ID,
        scheduling_encounter_id: ENCOUNTER_ID,
        channel: channel,
        initial_message: initialMessage,
        agent_opening: Boolean(options.agentOpening),
      }),
    });
    interactionId = created.interaction_id;
    interactionCorrelationId = created.correlation_id || null;
    document.getElementById("incomingBanner").classList.add("connected");
    document.getElementById("openCallBtn").textContent = "Interaction open";
    document.getElementById("openCallBtn").disabled = true;

    if (channel === "CHAT") {
      setInteractionStatus("CHAT ACTIVE", "handling");
      appendTranscript(
        "System",
        "Synthetic chat active. MSA monitoring governed eligibility evidence.",
        "system"
      );
    } else {
      callStartedAt = Date.now();
      setInteractionStatus("AGENT HANDLING", "handling");
      appendTranscript(
        "System",
        "Agent connected. MSA monitoring without takeover.",
        "system"
      );
    }

    if (options.agentOpening) {
      try {
        const replay = await fetch(
          "/api/interactions/" + interactionId + "/events?once=1",
          {headers: headers()}
        );
        const text = await replay.text();
        text.split("\n\n").filter(Boolean).forEach(parseSseFrame);
      } catch (error) {
        console.warn("Unable to replay opening interaction events", error);
      }
    }

    connectSse();
    await reconcileConversationHistory();
    await refreshRuntimeProof();
    if (channel === "CHAT" && initialMessage.toLowerCase().includes("earliest")) {
      await api("/api/interactions/" + interactionId + "/messages", {
        method: "POST",
        body: JSON.stringify({message: initialMessage}),
      });
    }
  } catch (error) {
    interactionCreationError = error.body?.error || error.message || "Request failed";
    if (error.body?.interaction_id) {
      interactionId = error.body.interaction_id;
      interactionCorrelationId = error.body.correlation_id || null;
    }
    setInteractionStatus(
      channel === "CHAT" ? "CHAT READY" : "INCOMING CALL",
      channel === "CHAT" ? "handling" : "incoming"
    );
    const runtimeFailure = error.body?.runtime_failure_code;
    const message = runtimeFailure
      ? "Avery runtime unavailable: " + runtimeFailure
      : interactionCreationError;
    toast(message, true);
  }
}

async function openIncomingCall() {
  if (interactionId) return interactionId;
  await startInteraction("PHONE", "", {agentOpening: true});
  return interactionId;
}

async function openConflictChat() {
  await startInteraction("CHAT", "I want the earliest appointment you have.");
}

async function sendMessage(message, options = {}) {
  if (liveCallEnded) {
    toast("This call has ended. Start a new interaction to continue.");
    return;
  }
  if (!interactionId) await openIncomingCall();
  if (!interactionId) return;
  appendTranscript("Veteran", message, "veteran");
  if (options.fromVoice) {
    recordActivity(
      "voice-" + Date.now(),
      "Veteran spoke",
      "Speech was transcribed and sent through the governed interaction API.",
      "conversation"
    );
  }
  try {
    const result = await api("/api/interactions/" + interactionId + "/messages", {
      method: "POST",
      body: JSON.stringify({message: message}),
    });
    handleEvent(result);
    if (options.fromVoice && result.event_type !== "agent_answered") {
      awaitingAgentReply = false;
      setVoiceStatus("Listening", voiceMode);
      startRecognition();
    }
  } catch (error) {
    awaitingAgentReply = false;
    toast(error.message, true);
    if (voiceMode) {
      setVoiceStatus("Listening", true);
      startRecognition();
    }
  }
}

async function runDemoAction(action, optionId) {
  if (!interactionId) await openIncomingCall();
  if (!interactionId) return;

  const payload = {action: action};
  if (optionId) payload.option_id = optionId;
  else if (selectedOptionId) payload.option_id = selectedOptionId;

  const actionButtons = {
    VERIFY: "verifyBtn",
    CONFIRM: "confirmBtn",
    APPROVE: "approveBtn",
    BOOK: "bookBtn",
  };
  const buttonId = actionButtons[action];
  const button = buttonId ? document.getElementById(buttonId) : null;
  const originalText = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = action === "BOOK" ? "Recording…" : "Working…";
  }

  try {
    const result = await api(
      "/api/primary-care/" + interactionId + "/actions",
      {method: "POST", body: JSON.stringify(payload)}
    );

    if (!result.demo_a) {
      throw new Error("Lifecycle action returned no governed state.");
    }

    if (result.demo_a.selected_option_id) {
      selectedOptionId = result.demo_a.selected_option_id;
    }

    // The action response is authoritative for the transition that just
    // completed. Render it immediately so the next permitted action is not
    // dependent on a second GET completing first.
    renderDemoState(result.demo_a);

    const actionActivity = {
      SELECT: ["Veteran selected option", "A governed eligible option was selected.", "conversation"],
      VERIFY: ["Slot verified", "Selected option passed the verification step.", "governed"],
      CONFIRM: ["Veteran confirmed", "Explicit Veteran confirmation was recorded.", "conversation"],
      APPROVE: ["MSA approved", "Human approval was recorded for the synthetic booking.", "human"],
      BOOK: ["Simulated booking recorded", "Synthetic booking completed; no production scheduling write occurred.", "human"],
    };
    const activity = actionActivity[action];
    if (activity) {
      recordActivity("action-" + action + "-" + result.demo_a.state, activity[0], activity[1], activity[2]);
    }

    try {
      await refreshEncounter();
    } catch (refreshError) {
      console.warn("Lifecycle advanced but encounter refresh failed", refreshError);
      toast("State advanced; governed evidence refresh will retry.", true);
      return;
    }

    const successMessages = {
      SELECT: "Governed option selected.",
      VERIFY: "Selected slot verified.",
      CONFIRM: "Veteran confirmation recorded.",
      APPROVE: "MSA approval recorded.",
      BOOK: "Simulated booking recorded.",
    };
    toast(successMessages[action] || "Demo A state advanced.");
  } catch (error) {
    toast(action + " failed: " + error.message, true);
    console.error("Primary Care lifecycle action failed", {action: action, error: error});
    // Reconcile controls with the backend after a rejected transition.
    await refreshEncounter();
  } finally {
    if (button) button.textContent = originalText;
  }
}

async function endLiveCall() {
  if (!interactionId) {
    toast("No live call is active.");
    return;
  }

  liveCallEnded = true;
  callStartedAt = null;
  canonicalGreetingDelivered = false;
  voiceMode = false;
  awaitingAgentReply = false;
  speakingAgentReply = false;
  stopRecognition();
  stopMicMeter();
  stopActiveNeuralPlayback();
  await disconnectLiveKitVoice();
  if (voicePlaybackContext) {
    const context = voicePlaybackContext;
    voicePlaybackContext = null;
    context.close().catch(function (error) {
      console.warn("Unable to close Avery audio playback", error);
    });
  }
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }

  try {
    const snapshot = await api(
      "/api/interactions/" + interactionId + "/actions",
      {method: "POST", body: JSON.stringify({action: "END"})}
    );
    setInteractionStatus("CALL ENDED", "ended");
    const state = document.getElementById("handoffPeekState");
    if (state) state.textContent = "Call ended";
    document.getElementById("humanControl").textContent =
      snapshot.human_control_mode.replaceAll("_", " ");
    const endButton = document.getElementById("endCallBtn");
    if (endButton) endButton.disabled = true;
    const voiceButton = document.getElementById("voiceToggleBtn");
    if (voiceButton) voiceButton.disabled = true;
    toast("Live call ended.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function setHumanControl(mode) {
  if (!interactionId) await openIncomingCall();
  if (!interactionId) return;

  const actionMap = {
    "MSA MONITORING": "MONITOR",
    "MSA JOINED": "JOIN",
    "HANDOFF ACCEPTED": "ACCEPT_HANDOFF",
  };
  const action = actionMap[mode];
  if (!action) return;

  try {
    const snapshot = await api(
      "/api/interactions/" + interactionId + "/actions",
      {method: "POST", body: JSON.stringify({action: action})}
    );
    document.getElementById("humanControl").textContent =
      snapshot.human_control_mode.replaceAll("_", " ");
    document.querySelectorAll(".rail-controls button").forEach(function (button) {
      button.classList.remove("active");
    });
    if (mode === "MSA MONITORING") {
      document.getElementById("monitorBtn").classList.add("active");
    } else if (mode === "MSA JOINED") {
      document.getElementById("railJoinBtn").classList.add("active");
      appendTranscript(
        "System",
        "MSA joined. Previously captured context remains visible.",
        "system"
      );
    } else {
      document.getElementById("acceptTransferBtn").classList.add("active");
      appendTranscript(
        "System",
        "Handoff accepted. Scheduling context retained.",
        "system"
      );
    }
    if (snapshot.status === "MSA_JOINED") {
      setInteractionStatus("MSA JOINED", "joined");
    }
  } catch (error) {
    toast(error.message, true);
  }
}

function updateDuration() {
  const seconds = callStartedAt == null
    ? 0
    : Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000));
  const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  const text = mins + ":" + secs;
  document.getElementById("incomingDuration").textContent = text;
  document.getElementById("queueDuration").textContent = text;
}

function showVoiceTransportStatus() {
  const status = document.getElementById("voiceStatus");
  const message = status ? status.textContent : "Phone/SIP transport status unavailable";
  toast(message);
}

function showWorkspace() {
  const live = document.getElementById("liveWorkspace");
  const liveButton = document.getElementById("liveCallMode");
  if (live) live.hidden = false;
  if (liveButton) liveButton.classList.add("active");
}

function openWorkPanel(panelId) {
  document.querySelectorAll(".work-tab").forEach(function (button) {
    button.classList.toggle("active", button.dataset.panel === panelId);
  });
  document.querySelectorAll(".tab-panel").forEach(function (panel) {
    panel.classList.toggle("active", panel.id === panelId);
  });
}

document.querySelectorAll(".work-tab").forEach(function (button) {
  button.addEventListener("click", function () { openWorkPanel(button.dataset.panel); });
});
document.querySelectorAll("[data-open-panel]").forEach(function (button) {
  button.addEventListener("click", function () { openWorkPanel(button.dataset.openPanel); });
});
document.getElementById("liveCallMode").onclick = function () { showNavigationView("live"); };
document.querySelectorAll(".primary-nav [data-nav]").forEach(function (button) {
  button.addEventListener("click", function () { showNavigationView(button.dataset.nav); });
});
document.querySelectorAll(".rail-tabs [data-monitor-target]").forEach(function (button) {
  button.addEventListener("click", function () {
    focusMonitoringCard(button.dataset.monitorTarget, button);
  });
});
document.getElementById("msaAssistantForm").addEventListener("submit", function (event) {
  event.preventDefault();
  const input = document.getElementById("msaAssistantInput");
  if (!input || !input.value.trim()) return;
  toast("MSA ↔ Avery assistant transport is the next functional wiring step.");
  input.value = "";
});

document.getElementById("openCallBtn").onclick = openIncomingCall;
document.getElementById("queueCase").onclick = openIncomingCall;
document.getElementById("refreshEncounterBtn").onclick = refreshEncounter;
document.getElementById("joinBtn").onclick = function () { setHumanControl("MSA JOINED"); };
document.getElementById("railJoinBtn").onclick = function () { setHumanControl("MSA JOINED"); };
document.getElementById("monitorBtn").onclick = function () {
  setHumanControl("MSA MONITORING");
};
document.getElementById("acceptTransferBtn").onclick = function () {
  setHumanControl("HANDOFF ACCEPTED");
};
document.getElementById("endCallBtn").onclick = endLiveCall;
document.getElementById("voiceToggleBtn").onclick = toggleLiveKitVoice;
document.getElementById("holdCallBtn").onclick = function () {
  toggleHoldCall().catch(function (error) {
    console.error("Unable to change hold state", error);
    toast("Hold failed: " + error.message, true);
  });
};
document.getElementById("verifyBtn").onclick = function () {
  runDemoAction("VERIFY");
};
document.getElementById("confirmBtn").onclick = function () {
  runDemoAction("CONFIRM");
};
document.getElementById("approveBtn").onclick = function () {
  runDemoAction("APPROVE");
};
document.getElementById("bookBtn").onclick = function () {
  runDemoAction("BOOK");
};
window.setInterval(updateDuration, 1000);
buildVoiceWave();
configureVoiceMode();
showNavigationView("live");
updateDuration();
refreshVoiceReadiness();
refreshEncounter();

window.setInterval(function () {
  if (!interactionId || liveCallEnded) return;
  reconcileConversationHistory();
  refreshRuntimeProof();
}, 2000);
