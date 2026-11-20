"""IBM Phone integration adapter.

This module maps supported IBM phone-integration context and CDR webhook
payloads into Veteran Access Bridge's provider-neutral voice-session contract.

It does not transport audio. Audio remains owned by IBM Phone/SIP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import jwt

from veteran_access_bridge.domain.voice_session import (
    ApplyVoiceEventRequest,
    VoiceEventType,
)


@dataclass(frozen=True)
class IBMPhoneContext:
    sip_call_id: str
    assistant_phone_number: str | None
    custom_invite_headers: dict[str, str]
    barge_in_occurred: bool
    post_response_timeout_occurred: bool
    final_utterance_timeout_occurred: bool


@dataclass(frozen=True)
class IBMPhoneCDR:
    global_session_id: str | None
    sip_call_id: str | None
    failure_occurred: bool
    failure_details: str | None
    transfer_occurred: bool
    primary_phone_number: str | None


def parse_voice_telephony_context(payload: Mapping[str, Any]) -> IBMPhoneContext:
    """Extract the documented IBM voice_telephony context.

    Accepts either the full assistant turn payload or the voice_telephony object.
    Caller phone numbers and private SIP URIs are intentionally not copied into
    the canonical session model.
    """

    voice = _find_voice_telephony(payload)
    sip_call_id = str(voice.get("sip_call_id", "")).strip()
    if not sip_call_id:
        raise ValueError("IBM phone context is missing voice_telephony.sip_call_id.")

    headers_raw = voice.get("sip_custom_invite_headers") or {}
    headers = (
        {str(key): str(value) for key, value in headers_raw.items()}
        if isinstance(headers_raw, Mapping)
        else {}
    )

    return IBMPhoneContext(
        sip_call_id=sip_call_id,
        assistant_phone_number=_optional_string(voice.get("assistant_phone_number")),
        custom_invite_headers=headers,
        barge_in_occurred=bool(voice.get("barge_in_occurred", False)),
        post_response_timeout_occurred=bool(
            voice.get("post_response_timeout_occurred", False)
        ),
        final_utterance_timeout_occurred=bool(
            voice.get("final_utterance_timeout_occurred", False)
        ),
    )


def context_to_event(payload: Mapping[str, Any]) -> ApplyVoiceEventRequest:
    context = parse_voice_telephony_context(payload)
    return ApplyVoiceEventRequest(
        event_type=VoiceEventType.CONNECTED,
        provider_call_id=context.sip_call_id,
        payload={
            "provider": "IBM_PHONE",
            "assistant_phone_number": context.assistant_phone_number,
            "sip_custom_invite_headers": context.custom_invite_headers,
            "barge_in_occurred": context.barge_in_occurred,
            "post_response_timeout_occurred": (context.post_response_timeout_occurred),
            "final_utterance_timeout_occurred": (
                context.final_utterance_timeout_occurred
            ),
        },
    )


def parse_cdr_webhook(payload: Mapping[str, Any]) -> IBMPhoneCDR:
    """Parse IBM's documented cdr_logged webhook payload."""

    event = payload.get("event")
    if isinstance(event, Mapping):
        event_type = str(event.get("name", "")).lower()
    else:
        event_type = str(payload.get("event_type", event or "")).lower()
    if event_type and event_type != "cdr_logged":
        raise ValueError(f"Unsupported IBM log webhook event {event_type!r}.")

    body = payload.get("payload")
    if not isinstance(body, Mapping):
        body = payload

    headers = body.get("headers")
    if not isinstance(headers, Mapping):
        headers = {}

    sip_call_id = _optional_string(headers.get("call_id"))
    if sip_call_id is None:
        sip_call_id = _optional_string(body.get("x-global-sip-trunk-call-id"))

    return IBMPhoneCDR(
        global_session_id=_optional_string(body.get("global_session_id")),
        sip_call_id=sip_call_id,
        failure_occurred=bool(body.get("failure_occurred", False)),
        failure_details=_optional_string(body.get("failure_details")),
        transfer_occurred=bool(body.get("transfer_occurred", False)),
        primary_phone_number=_optional_string(body.get("primary_phone_number")),
    )


def cdr_to_terminal_event(payload: Mapping[str, Any]) -> ApplyVoiceEventRequest:
    cdr = parse_cdr_webhook(payload)
    event_type = (
        VoiceEventType.SESSION_FAILED
        if cdr.failure_occurred
        else VoiceEventType.SESSION_ENDED
    )
    provider_event_id = (
        f"ibm-cdr:{cdr.global_session_id}" if cdr.global_session_id else None
    )
    return ApplyVoiceEventRequest(
        event_type=event_type,
        provider_event_id=provider_event_id,
        provider_session_id=cdr.global_session_id,
        provider_call_id=cdr.sip_call_id,
        payload={
            "provider": "IBM_PHONE",
            "transfer_occurred": cdr.transfer_occurred,
            "failure_occurred": cdr.failure_occurred,
            "failure_details": cdr.failure_details,
            # Called number is operational routing metadata; caller number is
            # deliberately not retained by this adapter.
            "primary_phone_number": cdr.primary_phone_number,
        },
    )


def _find_voice_telephony(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if "sip_call_id" in payload:
        return payload

    context = payload.get("context")
    if isinstance(context, Mapping):
        integrations = context.get("integrations")
        if isinstance(integrations, Mapping):
            voice = integrations.get("voice_telephony")
            if isinstance(voice, Mapping):
                merged = dict(voice)
                input_obj = payload.get("input")
                if isinstance(input_obj, Mapping):
                    input_integrations = input_obj.get("integrations")
                    if isinstance(input_integrations, Mapping):
                        input_voice = input_integrations.get("voice_telephony")
                        if isinstance(input_voice, Mapping):
                            merged.update(input_voice)
                return merged

    system_integrations = payload.get("system_integrations")
    if isinstance(system_integrations, Mapping):
        voice = system_integrations.get("voice_telephony")
        if isinstance(voice, Mapping):
            return voice

    raise ValueError("IBM phone payload does not contain voice_telephony context.")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def verify_log_webhook_jwt(authorization: str | None, secret: str) -> dict[str, Any]:
    """Verify the JWT IBM sends with log-webhook requests."""

    if not secret:
        raise ValueError("IBM phone log webhook secret is not configured.")
    if not authorization:
        raise ValueError("IBM phone log webhook Authorization header is missing.")

    scheme, separator, credential = authorization.partition(" ")
    token = credential if separator and scheme.lower() == "bearer" else authorization
    token = token.strip()
    if not token:
        raise ValueError("IBM phone log webhook JWT is empty.")

    header = jwt.get_unverified_header(token)
    algorithm = str(header.get("alg", ""))
    allowed = {"HS256", "HS384", "HS512"}
    if algorithm not in allowed:
        raise ValueError(f"Unsupported IBM webhook JWT algorithm {algorithm!r}.")

    decoded = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        options={"verify_aud": False},
    )
    if not isinstance(decoded, dict):
        raise ValueError("IBM phone log webhook JWT payload is invalid.")
    return decoded
