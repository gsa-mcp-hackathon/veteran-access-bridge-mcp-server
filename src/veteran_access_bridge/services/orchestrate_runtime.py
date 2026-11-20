"""Server-side watsonx Orchestrate runtime abstraction and HTTP client.

Issue #79.

Browser code never receives IBM credentials. The application depends on the
OrchestrateRuntime abstraction rather than IBM-specific HTTP details.

The default HTTP implementation uses a configurable chat-completions path so
IBM Cloud / service-instance deployment shapes can be supplied by environment
configuration without changing application code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator, Mapping

import httpx

from veteran_access_bridge.domain.avery_script import (
    AVERY_OPENING_GREETING,
    AVERY_PRIMARY_CARE_VERIFICATION_PROMPT,
    format_missing_verification_prompt,
)
from veteran_access_bridge.mcp.session_scope import (
    redact,
    runtime_context,
    timing_trace_id,
)


class OrchestrateRuntimeError(RuntimeError):
    """Base runtime failure exposed to the application layer."""


class OrchestrateAuthenticationError(OrchestrateRuntimeError):
    """Authentication/authorization failure."""


class OrchestrateTimeoutError(OrchestrateRuntimeError):
    """Request exceeded configured timeout."""


class OrchestrateUnavailableError(OrchestrateRuntimeError):
    """Runtime could not be reached or returned a transient server error."""


class OrchestrateProtocolError(OrchestrateRuntimeError):
    """Runtime response could not be normalized safely."""


class RuntimeEventType(StrEnum):
    RUN_STARTED = "run_started"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_COMPLETED = "message_completed"
    TOOL_ACTIVITY = "tool_activity"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class RuntimeInteraction:
    interaction_id: str
    run_id: str | None
    session_id: str | None
    agent_id: str
    initial_response_text: str | None = None
    tool_activity: tuple[Mapping[str, Any], ...] = ()
    synthetic: bool = True


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: RuntimeEventType
    interaction_id: str
    run_id: str | None
    session_id: str | None
    payload: Mapping[str, Any] = field(default_factory=dict)
    synthetic: bool = True


@dataclass(frozen=True)
class OrchestrateConfig:
    base_url: str
    agent_id: str
    bearer_token: str | None = None
    api_key: str | None = None
    chat_path: str = "/v2/orchestrate/{agent_id}/chat/completions"
    timeout_seconds: float = 30.0
    max_retries: int = 1
    thread_header: str = "X-IBM-THREAD-ID"
    iam_token_url: str = "https://iam.cloud.ibm.com/identity/token"
    token_refresh_skew_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url is required.")
        if not self.agent_id.strip():
            raise ValueError("agent_id is required.")
        bearer = (self.bearer_token or "").strip()
        api_key = (self.api_key or "").strip()
        if not bearer and not api_key:
            raise ValueError("bearer_token or api_key is required.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_retries < 0:
            raise ValueError("max_retries must be zero or greater.")
        if self.token_refresh_skew_seconds < 0:
            raise ValueError("token_refresh_skew_seconds must be zero or greater.")

    @classmethod
    def from_env(cls) -> "OrchestrateConfig":
        """Load server-side configuration from environment variables."""

        base_url = os.getenv("ORCHESTRATE_BASE_URL", "").strip()
        bearer_token = os.getenv("ORCHESTRATE_BEARER_TOKEN", "").strip()
        api_key = os.getenv("ORCHESTRATE_API_KEY", "").strip()
        missing = []
        if not base_url:
            missing.append("ORCHESTRATE_BASE_URL")
        if not bearer_token and not api_key:
            missing.append("ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN")
        if missing:
            raise ValueError(
                "Missing required watsonx Orchestrate configuration: "
                + ", ".join(missing)
            )

        return cls(
            base_url=base_url,
            agent_id=os.environ.get(
                "ORCHESTRATE_AGENT_ID",
                "veteran_access_agent",
            ),
            bearer_token=bearer_token or None,
            api_key=api_key or None,
            chat_path=os.environ.get(
                "ORCHESTRATE_CHAT_PATH",
                "/v2/orchestrate/{agent_id}/chat/completions",
            ),
            timeout_seconds=float(os.environ.get("ORCHESTRATE_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.environ.get("ORCHESTRATE_MAX_RETRIES", "1")),
            thread_header=os.environ.get(
                "ORCHESTRATE_THREAD_HEADER",
                "X-IBM-THREAD-ID",
            ),
            iam_token_url=os.environ.get(
                "ORCHESTRATE_IAM_TOKEN_URL",
                "https://iam.cloud.ibm.com/identity/token",
            ),
            token_refresh_skew_seconds=float(
                os.environ.get("ORCHESTRATE_TOKEN_REFRESH_SKEW_SECONDS", "300")
            ),
        )

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + self.chat_path.format(agent_id=self.agent_id)


class OrchestrateRuntime(ABC):
    """Application-facing runtime contract."""

    @abstractmethod
    async def start_interaction(
        self,
        *,
        interaction_id: str,
        message: str,
        session_id: str | None = None,
    ) -> RuntimeInteraction:
        raise NotImplementedError

    @abstractmethod
    async def send_message(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> RuntimeEvent:
        raise NotImplementedError

    @abstractmethod
    async def stream_events(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> AsyncIterator[RuntimeEvent]:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Optional cleanup hook."""


class HttpOrchestrateRuntime(OrchestrateRuntime):
    """Backend-only HTTP client for watsonx Orchestrate."""

    def __init__(
        self,
        config: OrchestrateConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds)
        )
        self._owns_client = client is None
        self.last_retry_count = 0
        self._cached_iam_token: str | None = None
        self._cached_iam_token_expires_at = 0.0
        # Synthetic demo fallback: replay only bounded chat history, not IBM
        # server-side tool state. Do not share history between interactions.
        self._history: dict[str, list[dict[str, str]]] = {}
        self._history_limit = 12
        self._thread_mode = os.getenv("ORCHESTRATE_THREAD_MODE", "history").lower()
        if self._thread_mode not in {"history", "native"}:
            raise ValueError("ORCHESTRATE_THREAD_MODE must be history or native.")

    def _invalidate_cached_iam_token(self) -> None:
        self._cached_iam_token = None
        self._cached_iam_token_expires_at = 0.0

    async def _authorization_token(self) -> str:
        if self.config.bearer_token:
            return self.config.bearer_token

        now = time.time()
        if (
            self._cached_iam_token
            and now + self.config.token_refresh_skew_seconds
            < self._cached_iam_token_expires_at
        ):
            return self._cached_iam_token

        if not self.config.api_key:
            raise OrchestrateAuthenticationError(
                "watsonx Orchestrate server credential is not configured."
            )

        try:
            response = await self._client.post(
                self.config.iam_token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": self.config.api_key,
                },
            )
        except httpx.TimeoutException as exc:
            raise OrchestrateTimeoutError("IBM IAM token request timed out.") from exc
        except httpx.RequestError as exc:
            raise OrchestrateUnavailableError("IBM IAM token request failed.") from exc

        if response.status_code in {400, 401, 403}:
            raise OrchestrateAuthenticationError(
                "IBM IAM API-key authentication failed."
            )
        if response.status_code >= 500:
            raise OrchestrateUnavailableError(
                f"IBM IAM returned HTTP {response.status_code}."
            )
        if response.status_code >= 400:
            raise OrchestrateProtocolError(
                f"IBM IAM returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OrchestrateProtocolError("IBM IAM returned invalid JSON.") from exc

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise OrchestrateProtocolError(
                "IBM IAM response did not include an access token."
            )

        expiration = payload.get("expiration")
        expires_in = payload.get("expires_in")
        if isinstance(expiration, (int, float)):
            expires_at = float(expiration)
        elif isinstance(expires_in, (int, float)):
            expires_at = now + float(expires_in)
        else:
            expires_at = now + 3600.0

        self._cached_iam_token = token
        self._cached_iam_token_expires_at = expires_at
        return token

    async def _headers(self, session_id: str | None) -> dict[str, str]:
        token = await self._authorization_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if session_id:
            headers[self.config.thread_header] = session_id
        return headers

    @staticmethod
    def _payload(message: str, *, stream: bool) -> dict[str, Any]:
        if not message.strip():
            raise ValueError("message is required.")
        return {
            "messages": [{"role": "user", "content": message}],
            "stream": stream,
            "context_variables": runtime_context(),
        }

    async def _post_json(
        self,
        *,
        message: str,
        session_id: str | None,
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        attempts = self.config.max_retries + 1
        last_error: Exception | None = None

        self.last_retry_count = 0
        for attempt in range(attempts):
            self.last_retry_count = attempt
            started = time.perf_counter()
            headers = await self._headers(session_id)
            auth_ready = time.perf_counter()
            try:
                response = await self._client.post(
                    self.config.chat_url,
                    headers=headers,
                    json={
                        "messages": messages or [{"role": "user", "content": message}],
                        "stream": False,
                        "context_variables": runtime_context(),
                    },
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise OrchestrateTimeoutError(
                        "watsonx Orchestrate request timed out."
                    ) from exc
                continue
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise OrchestrateUnavailableError(
                        "watsonx Orchestrate request failed."
                    ) from exc
                continue

            logging.getLogger("uvicorn.error.vab_timing").info(
                "Orchestrate request auth_ms=%.1f request_ms=%.1f "
                "attempt=%d status=%d trace_id=%s",
                (auth_ready - started) * 1000,
                (time.perf_counter() - auth_ready) * 1000,
                attempt + 1,
                response.status_code,
                timing_trace_id(),
            )

            if response.status_code in {401, 403}:
                if self.config.api_key and not self.config.bearer_token:
                    self._invalidate_cached_iam_token()
                    if attempt + 1 < attempts:
                        continue
                raise OrchestrateAuthenticationError(
                    "watsonx Orchestrate authentication failed."
                )
            if response.status_code >= 500:
                if attempt + 1 >= attempts:
                    raise OrchestrateUnavailableError(
                        f"watsonx Orchestrate returned HTTP {response.status_code}."
                    )
                continue
            if response.status_code >= 400:
                raise OrchestrateProtocolError(
                    f"watsonx Orchestrate returned HTTP {response.status_code}."
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise OrchestrateProtocolError(
                    "watsonx Orchestrate returned invalid JSON."
                ) from exc
            if not isinstance(data, dict):
                raise OrchestrateProtocolError(
                    "watsonx Orchestrate JSON response must be an object."
                )
            return redact(data)

        raise OrchestrateUnavailableError(
            "watsonx Orchestrate request failed."
        ) from last_error

    @staticmethod
    def _extract_run_id(data: Mapping[str, Any]) -> str | None:
        for key in ("run_id", "id", "trace_id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _extract_text(data: Mapping[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                delta = first.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str):
                        return content

        for key in ("output_text", "response", "message"):
            value = data.get(key)
            if isinstance(value, str):
                return value

        return ""

    @staticmethod
    def _extract_tool_activity(
        data: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        """Best-effort extraction of observable tool calls/results from IBM responses.

        This never exposes hidden chain-of-thought. It only projects structured
        tool names, arguments, and tool outputs when IBM returns them in the
        chat-completions payload.
        """
        activity: list[Mapping[str, Any]] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                role = value.get("role")
                if role == "tool":
                    activity.append(
                        {
                            "phase": "result",
                            "name": str(
                                value.get("name") or value.get("tool_name") or "tool"
                            ),
                            "result": value.get("content"),
                            "tool_call_id": value.get("tool_call_id")
                            or value.get("toolCallId"),
                            "status": value.get("status"),
                        }
                    )

                tool_calls = value.get("tool_calls")
                if isinstance(tool_calls, list):
                    for item in tool_calls:
                        if not isinstance(item, dict):
                            continue
                        function = item.get("function")
                        if isinstance(function, dict):
                            activity.append(
                                {
                                    "phase": "call",
                                    "name": str(
                                        function.get("name")
                                        or item.get("name")
                                        or "tool"
                                    ),
                                    "arguments": function.get("arguments"),
                                    "tool_call_id": item.get("id"),
                                }
                            )
                        else:
                            activity.append(
                                {
                                    "phase": "call",
                                    "name": str(
                                        item.get("name")
                                        or item.get("tool_name")
                                        or "tool"
                                    ),
                                    "arguments": item.get("arguments")
                                    or item.get("input"),
                                    "tool_call_id": item.get("id"),
                                }
                            )

                for key, child in value.items():
                    if key == "tool_calls":
                        continue
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(data)

        # Deduplicate repeated nested representations while preserving order.
        seen: set[str] = set()
        unique: list[Mapping[str, Any]] = []
        for item in activity:
            marker = json.dumps(item, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(item)
        return tuple(unique)

    async def start_interaction(
        self,
        *,
        interaction_id: str,
        message: str,
        session_id: str | None = None,
    ) -> RuntimeInteraction:
        # IBM creates the initial conversation thread. Never pass a locally
        # generated VAB session/correlation ID as X-IBM-THREAD-ID: IBM returns
        # HTTP 404 when asked to resume a thread that does not exist.
        data = await self._post_json(message=message, session_id=None)
        thread_id = data.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise OrchestrateProtocolError(
                "watsonx Orchestrate response missing IBM thread_id."
            )
        if self._thread_mode == "history":
            self._history[interaction_id] = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": self._extract_text(data)},
            ]
        return RuntimeInteraction(
            interaction_id=interaction_id,
            run_id=self._extract_run_id(data),
            session_id=thread_id,
            agent_id=self.config.agent_id,
            initial_response_text=self._extract_text(data) or None,
            tool_activity=self._extract_tool_activity(data),
        )

    async def send_message(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> RuntimeEvent:
        if self._thread_mode == "history":
            history = self._history.get(interaction.interaction_id)
            if history is None:
                raise OrchestrateProtocolError(
                    "Conversation history unavailable; cannot safely resume."
                )
            messages = [*history, {"role": "user", "content": message}]
            data = await self._post_json(
                message=message,
                session_id=None,
                messages=messages,
            )
            text = self._extract_text(data)
            if not text:
                raise OrchestrateProtocolError(
                    "watsonx Orchestrate replay returned no assistant reply."
                )
            # Commit only after a valid response; retain a bounded rolling window.
            self._history[interaction.interaction_id] = (
                messages + [{"role": "assistant", "content": text}]
            )[-self._history_limit :]
        else:
            data = await self._post_json(
                message=message,
                session_id=interaction.session_id,
            )
        run_id = self._extract_run_id(data) or interaction.run_id
        return RuntimeEvent(
            event_type=RuntimeEventType.MESSAGE_COMPLETED,
            interaction_id=interaction.interaction_id,
            run_id=run_id,
            session_id=interaction.session_id,
            payload={
                "text": self._extract_text(data),
                "raw_event_type": data.get("type"),
                "tool_activity": self._extract_tool_activity(data),
            },
        )

    async def stream_events(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> AsyncIterator[RuntimeEvent]:
        if runtime_context():
            # Buffer scoped replies so split token fragments can never leak via
            # streaming deltas. The browser voice path already uses send_message.
            raise OrchestrateProtocolError(
                "Scoped voice turns require buffered replies."
            )
        headers = await self._headers(interaction.session_id)
        headers["Accept"] = "text/event-stream"

        try:
            async with self._client.stream(
                "POST",
                self.config.chat_url,
                headers=headers,
                json=self._payload(message, stream=True),
            ) as response:
                if response.status_code in {401, 403}:
                    raise OrchestrateAuthenticationError(
                        "watsonx Orchestrate authentication failed."
                    )
                if response.status_code >= 500:
                    raise OrchestrateUnavailableError(
                        f"watsonx Orchestrate returned HTTP {response.status_code}."
                    )
                if response.status_code >= 400:
                    raise OrchestrateProtocolError(
                        f"watsonx Orchestrate returned HTTP {response.status_code}."
                    )

                yield RuntimeEvent(
                    event_type=RuntimeEventType.RUN_STARTED,
                    interaction_id=interaction.interaction_id,
                    run_id=interaction.run_id,
                    session_id=interaction.session_id,
                    payload={},
                )

                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue

                    raw = line.removeprefix("data:").strip()
                    if raw == "[DONE]":
                        yield RuntimeEvent(
                            event_type=RuntimeEventType.RUN_COMPLETED,
                            interaction_id=interaction.interaction_id,
                            run_id=interaction.run_id,
                            session_id=interaction.session_id,
                            payload={},
                        )
                        return

                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise OrchestrateProtocolError(
                            "Invalid JSON in watsonx Orchestrate stream."
                        ) from exc
                    if not isinstance(data, dict):
                        continue

                    text = self._extract_text(data)
                    run_id = self._extract_run_id(data) or interaction.run_id

                    if text:
                        yield RuntimeEvent(
                            event_type=RuntimeEventType.MESSAGE_DELTA,
                            interaction_id=interaction.interaction_id,
                            run_id=run_id,
                            session_id=interaction.session_id,
                            payload={"text": text},
                        )
                    elif "tool_calls" in data:
                        yield RuntimeEvent(
                            event_type=RuntimeEventType.TOOL_ACTIVITY,
                            interaction_id=interaction.interaction_id,
                            run_id=run_id,
                            session_id=interaction.session_id,
                            payload={"tool_calls": data.get("tool_calls")},
                        )
        except httpx.TimeoutException as exc:
            raise OrchestrateTimeoutError(
                "watsonx Orchestrate stream timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise OrchestrateUnavailableError(
                "watsonx Orchestrate stream failed."
            ) from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class FakeOrchestrateRuntime(OrchestrateRuntime):
    """Deterministic local-first runtime for tests and offline development."""

    def __init__(self, *, agent_id: str = "veteran_access_agent") -> None:
        self.agent_id = agent_id
        self.messages: list[str] = []
        self.last_retry_count = 0
        self._missing_verification_fields: dict[str, set[str]] = {}

    @staticmethod
    def _extract_utterance(message: str) -> str:
        marker = "Veteran utterance:\n"
        if marker in message:
            return message.split(marker, 1)[1].strip()
        return message.strip()

    @staticmethod
    def _is_application_event(message: str) -> bool:
        return "[APPLICATION EVENT - INTERNAL]" in message

    @staticmethod
    def _looks_like_primary_care_request(text: str) -> bool:
        normalized = text.lower()
        return "primary care" in normalized and (
            "schedule" in normalized or "appointment" in normalized
        )

    @staticmethod
    def _extract_last4(text: str) -> str | None:
        match = re.search(r"\b(\d{4})\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_date_of_birth(text: str) -> str | None:
        patterns = (
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _extract_last_name(text: str) -> str | None:
        patterns = (
            r"(?:last\s*name\s*(?:is|:)\s*)([A-Za-z][A-Za-z'\-]{1,})",
            r"(?:my\s+last\s+name\s+is\s+)([A-Za-z][A-Za-z'\-]{1,})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        compact = text.strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z'\-]{1,}", compact):
            return compact
        return None

    def _update_missing_fields(self, interaction_id: str, utterance: str) -> list[str]:
        missing = self._missing_verification_fields.setdefault(
            interaction_id,
            {"last_name", "last4", "date_of_birth"},
        )
        if self._extract_last_name(utterance):
            missing.discard("last_name")
        if self._extract_last4(utterance):
            missing.discard("last4")
        if self._extract_date_of_birth(utterance):
            missing.discard("date_of_birth")
        return sorted(missing)

    def _message_response(self, interaction_id: str, message: str) -> str:
        if self._is_application_event(message):
            self._missing_verification_fields[interaction_id] = {
                "last_name",
                "last4",
                "date_of_birth",
            }
            return AVERY_OPENING_GREETING

        utterance = self._extract_utterance(message)
        if self._looks_like_primary_care_request(utterance):
            self._missing_verification_fields[interaction_id] = {
                "last_name",
                "last4",
                "date_of_birth",
            }
            return AVERY_PRIMARY_CARE_VERIFICATION_PROMPT

        if interaction_id in self._missing_verification_fields:
            missing = self._update_missing_fields(interaction_id, utterance)
            if missing:
                return format_missing_verification_prompt(missing)
            self._missing_verification_fields.pop(interaction_id, None)
            return (
                "Thank you for verifying your information. "
                "I can continue helping with your primary care scheduling."
            )

        return (
            "I can continue helping with your primary care scheduling. "
            "When we are done, I can offer to end the call "
            "and wait for your confirmation."
        )

    async def start_interaction(
        self,
        *,
        interaction_id: str,
        message: str,
        session_id: str | None = None,
    ) -> RuntimeInteraction:
        self.messages.append(message)
        return RuntimeInteraction(
            interaction_id=interaction_id,
            run_id=f"run-{interaction_id}",
            session_id=session_id or f"thread-{interaction_id}",
            agent_id=self.agent_id,
            initial_response_text=self._message_response(interaction_id, message),
        )

    async def send_message(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> RuntimeEvent:
        self.messages.append(message)
        return RuntimeEvent(
            event_type=RuntimeEventType.MESSAGE_COMPLETED,
            interaction_id=interaction.interaction_id,
            run_id=interaction.run_id,
            session_id=interaction.session_id,
            payload={
                "text": self._message_response(interaction.interaction_id, message)
            },
        )

    async def stream_events(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> AsyncIterator[RuntimeEvent]:
        self.messages.append(message)
        text = self._message_response(interaction.interaction_id, message)
        yield RuntimeEvent(
            event_type=RuntimeEventType.RUN_STARTED,
            interaction_id=interaction.interaction_id,
            run_id=interaction.run_id,
            session_id=interaction.session_id,
        )
        yield RuntimeEvent(
            event_type=RuntimeEventType.MESSAGE_DELTA,
            interaction_id=interaction.interaction_id,
            run_id=interaction.run_id,
            session_id=interaction.session_id,
            payload={"text": text},
        )
        yield RuntimeEvent(
            event_type=RuntimeEventType.RUN_COMPLETED,
            interaction_id=interaction.interaction_id,
            run_id=interaction.run_id,
            session_id=interaction.session_id,
        )
