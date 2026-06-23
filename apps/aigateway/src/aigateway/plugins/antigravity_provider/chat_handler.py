"""Antigravity LiteLLM custom handler + Code Assist transport.

OAuth-only (no API-key path). Generation tries non-streaming
``:generateContent`` first, then falls back to aggregated
``:streamGenerateContent?alt=sse`` when the non-streaming method is unavailable.
The Code Assist host is
``daily-cloudcode-pa`` with a ``cloudcode-pa`` prod fallback on 404/5xx (U12).

Registration is keyed on provider="antigravity" (verified against litellm
1.87.0 that custom_llm_setup keys the provider list on the ``provider`` string,
so reusing gemini's constant would overwrite gemini's handler — findings U3).
The plugin calls the handler directly (mirroring gemini_provider), so the
custom_provider_map registration stays defensive-only.

Caller-auth strip is two-layer (U4): the same ``CLIENT_AUTH_HEADER_NAMES``
superset is filtered in the plugin's ``prepare_chat_body`` AND here on the
upstream forward, and gateway-owned headers (Authorization/User-Agent/profile)
are set LAST so a caller value can never override them.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import litellm
from litellm.llms.custom_llm import CustomLLM, CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.core.google_code_assist import parse_google_retry_after

from .auth import ANTIGRAVITY_PROFILE_HEADER
from .message_adapter import (
    PROVIDER,
    build_generate_content_body,
    model_response_from_antigravity,
    strip_provider_prefix,
)
from .settings import AntigravityPluginSettings

if TYPE_CHECKING:
    from collections.abc import Callable

# Single source of truth for gateway-owned headers (findings U4). Superset of
# gemini's set: adds the Code-Assist-surface names a caller could otherwise use
# to redirect billing/account/session — x-goog-authuser (account selector),
# x-goog-iam-authorization-token (IAM), cookie (daily-cloudcode session). Shared
# by prepare_chat_body (plugin) AND the upstream-forward filter below.
CLIENT_AUTH_HEADER_NAMES = frozenset(
    {
        "authorization",
        "content-type",
        "user-agent",
        "x-aigw-antigravity-profile",
        "x-goog-api-key",
        "x-goog-user-project",
        "x-goog-authuser",
        "x-goog-iam-authorization-token",
        "cookie",
    }
)

_HANDLER: AntigravityCustomLLM | None = None


@dataclass
class _CodeAssistSession:
    project_id: str | None = None
    endpoint: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _StreamMergeState:
    parts: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    block_reason: str | None = None
    stream_error: str | None = None
    usage: dict[str, Any] | None = None
    response_id: str | None = None
    model_version: str | None = None


def _safe_extra_headers(headers: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or key.lower() in CLIENT_AUTH_HEADER_NAMES:
            continue
        if value is None:
            continue
        safe[key] = str(value)
    return safe


def _profile_header_value(headers: dict[str, Any]) -> str:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == ANTIGRAVITY_PROFILE_HEADER.lower() and value:
            return str(value)
    return "default"


def _error_from_response(response: httpx.Response) -> CustomLLMError:
    status = response.status_code
    if status in (401, 403):
        return CustomLLMError(status_code=status, message="Antigravity rejected credentials")
    if status == 429:
        error = CustomLLMError(status_code=429, message="Antigravity rate limited")
        error.retry_after = parse_google_retry_after(  # type: ignore[attr-defined]
            response.text, response.headers
        )
        return error
    # 5xx (and any other non-2xx) → provider unavailable.
    return CustomLLMError(
        status_code=502,
        message=f"Antigravity Code Assist request failed with status {status}",
    )


def _should_try_stream_generate_content(response: httpx.Response) -> bool:
    # Only retry on the streaming verb when generateContent itself is
    # unsupported (404 not-found / 405 method-not-allowed). A 400 is our own
    # bad request; a 5xx is provider-unavailable; 401/403 are auth_required;
    # 429 is rate-limited — all flow to _error_from_response (5xx → 502), NOT a
    # verb-retry (review round 2 finding C; team-lead ruling: 404/405-only).
    # The EXACT verb-unsupported signal is to be PINNED by the Phase-0 live
    # spike — this 404/405 set is the best interim policy while generateContent
    # is unproven.
    return response.status_code in {404, 405}


def _payload_response(data: dict[str, Any]) -> dict[str, Any]:
    response = data.get("response")
    return response if isinstance(response, dict) else data


def _sse_error_message(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return f"Antigravity Code Assist SSE error: {message}"
        status = error.get("status")
        if isinstance(status, str) and status:
            return f"Antigravity Code Assist SSE error: {status}"
        code = error.get("code")
        if isinstance(code, int | float | str):
            return f"Antigravity Code Assist SSE error code {code}"
    if isinstance(error, str) and error:
        return f"Antigravity Code Assist SSE error: {error}"
    return "Antigravity Code Assist SSE error"


def _consume_stream_generate_content_event(raw: str, state: _StreamMergeState) -> None:
    if not raw or raw == "[DONE]":
        return
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CustomLLMError(
            status_code=502,
            message=f"Antigravity Code Assist SSE event not JSON: {exc}",
        ) from exc
    if not isinstance(event, dict):
        return
    payload = _payload_response(event)
    event_error = event.get("error") or payload.get("error")
    if event_error is not None:
        state.stream_error = _sse_error_message(event_error)
        return
    prompt_feedback = payload.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and isinstance(prompt_feedback.get("blockReason"), str):
        state.block_reason = prompt_feedback["blockReason"]
    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        candidate = candidates[0]
        if isinstance(candidate, dict):
            content = candidate.get("content")
            chunk_parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(chunk_parts, list):
                state.parts.extend(part for part in chunk_parts if isinstance(part, dict))
            if isinstance(candidate.get("finishReason"), str):
                state.finish_reason = candidate["finishReason"]
    if isinstance(payload.get("usageMetadata"), dict):
        state.usage = payload["usageMetadata"]
    if isinstance(payload.get("responseId"), str):
        state.response_id = payload["responseId"]
    elif isinstance(event.get("responseId"), str):
        state.response_id = event["responseId"]
    if isinstance(payload.get("modelVersion"), str):
        state.model_version = payload["modelVersion"]


def _merge_stream_generate_content_sse(text: str) -> dict[str, Any]:
    state = _StreamMergeState()
    event_lines: list[str] = []

    def flush_event() -> None:
        if not event_lines:
            return
        raw = "\n".join(event_lines).strip()
        event_lines.clear()
        _consume_stream_generate_content_event(raw, state)

    for line in text.splitlines():
        if not line.strip():
            flush_event()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            event_lines.append(line.removeprefix("data:").lstrip())
    flush_event()

    if state.stream_error is not None:
        raise CustomLLMError(status_code=502, message=state.stream_error)

    # A blocked response must never surface as a successful completion, even if
    # partial content streamed before the block (findings review round 2, B).
    if state.block_reason is not None:
        raise CustomLLMError(
            status_code=502,
            message=f"Antigravity Code Assist response blocked: {state.block_reason}",
        )

    if not state.parts:
        raise CustomLLMError(
            status_code=502,
            message="Antigravity Code Assist SSE response missing content parts",
        )

    # Do NOT default a missing finishReason to STOP. A stream that delivers
    # parts but never a terminal finishReason was truncated (dropped
    # connection / mid-stream abort) — returning finish="stop" would be a false
    # success. Raise instead so the caller sees a 502, not a silent truncation.
    if state.finish_reason is None:
        raise CustomLLMError(
            status_code=502,
            message="Antigravity Code Assist SSE stream ended without a finishReason (truncated)",
        )

    response: dict[str, Any] = {
        "candidates": [
            {
                "content": {"role": "model", "parts": state.parts},
                "finishReason": state.finish_reason,
            }
        ]
    }
    if state.usage is not None:
        response["usageMetadata"] = state.usage
    if state.response_id is not None:
        response["responseId"] = state.response_id
    if state.model_version is not None:
        response["modelVersion"] = state.model_version
    return {"response": response}


class AntigravityCustomLLM(CustomLLM):
    def __init__(
        self,
        settings: AntigravityPluginSettings | None = None,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings or AntigravityPluginSettings()
        self._http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        )
        self._sessions: dict[str, _CodeAssistSession] = {}

    # --- session cache -----------------------------------------------------

    def _session_for(self, session_key: str) -> _CodeAssistSession:
        session = self._sessions.get(session_key)
        if session is None:
            session = _CodeAssistSession()
            self._sessions[session_key] = session
        return session

    def invalidate_session(self, session_key: str) -> None:
        self._sessions.pop(session_key, None)

    # --- host fallback (U12) ----------------------------------------------

    def _endpoints(self) -> list[str]:
        hosts = [self._settings.code_assist_endpoint]
        fallback = self._settings.code_assist_fallback_endpoint
        if fallback and fallback not in hosts:
            hosts.append(fallback)
        return hosts

    async def _post_with_fallback(
        self,
        verb: str,
        request_headers: dict[str, str],
        body: dict[str, Any],
        timeout: Any,
        *,
        preferred_endpoint: str | None = None,
    ) -> tuple[httpx.Response, str]:
        """POST to the Code Assist verb, trying daily- then the prod fallback on
        404/5xx. Returns (response, endpoint_that_served_it). A non-retriable
        status (e.g. 401/403/429) returns immediately without trying fallback."""
        version = self._settings.code_assist_api_version
        endpoints = self._endpoints()
        if preferred_endpoint is not None:
            endpoints = [preferred_endpoint, *(e for e in endpoints if e != preferred_endpoint)]
        last_response: httpx.Response | None = None
        for index, endpoint in enumerate(endpoints):
            url = f"{endpoint}/{version}:{verb}"
            try:
                async with self._http_client_factory() as client:
                    response = await client.post(
                        url, json=body, headers=request_headers, timeout=timeout
                    )
            except httpx.RequestError as exc:
                raise CustomLLMError(
                    status_code=502, message=f"Antigravity Code Assist unreachable: {exc}"
                ) from exc
            last_response = response
            is_last = index == len(endpoints) - 1
            retriable = response.status_code == 404 or response.status_code >= 500
            if response.status_code == 200 or not retriable or is_last:
                return response, endpoint
        assert last_response is not None  # endpoints is non-empty
        return last_response, endpoints[-1]

    # --- setup -------------------------------------------------------------

    async def _ensure_setup(
        self, session_key: str, request_headers: dict[str, str], timeout: Any
    ) -> _CodeAssistSession:
        session = self._session_for(session_key)
        if session.project_id is not None:
            return session
        async with session.lock:
            if session.project_id is not None:
                return session
            body = {
                "metadata": {
                    # Live Code Assist rejects pluginType="ANTIGRAVITY" as an
                    # invalid enum; real Antigravity still identifies to this
                    # endpoint as the Gemini plugin surface.
                    "ideType": "ANTIGRAVITY",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                }
            }
            response, endpoint = await self._post_with_fallback(
                "loadCodeAssist", request_headers, body, timeout
            )
            if response.status_code != 200:
                raise _error_from_response(response)
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise CustomLLMError(
                    status_code=502,
                    message=f"Antigravity Code Assist setup response not JSON: {exc}",
                ) from exc
            project_id = data.get("cloudaicompanionProject") if isinstance(data, dict) else None
            if not isinstance(project_id, str) or not project_id:
                raise CustomLLMError(
                    status_code=502,
                    message="Antigravity Code Assist setup did not return cloudaicompanionProject",
                )
            session.project_id = project_id
            session.endpoint = endpoint
            return session

    # --- completion --------------------------------------------------------

    async def acompletion(  # type: ignore[override]
        self,
        model: str,
        messages: list,
        api_base: str | None,
        custom_prompt_dict: dict,
        model_response: ModelResponse,
        print_verbose,
        encoding,
        api_key,
        logging_obj,
        optional_params: dict,
        acompletion=None,
        litellm_params=None,
        logger_fn=None,
        headers=None,
        timeout=None,
        client=None,
    ) -> ModelResponse:
        del api_base, custom_prompt_dict, model_response, print_verbose, encoding
        del logging_obj, acompletion, litellm_params, logger_fn, client
        if not api_key:
            raise CustomLLMError(
                status_code=401,
                message="Antigravity requires gateway-owned OAuth credentials",
            )
        normalized_messages = [message for message in messages if isinstance(message, dict)]
        model_slug = strip_provider_prefix(model)
        return await self._run_oauth(
            model_slug,
            normalized_messages,
            optional_params or {},
            str(api_key),
            headers or {},
            timeout,
        )

    async def _run_oauth(
        self,
        model: str,
        messages: list[dict[str, Any]],
        optional_params: dict[str, Any],
        access_token: str,
        headers: dict[str, str],
        timeout: Any,
    ) -> ModelResponse:
        raw_headers = dict(headers)
        session_key = _profile_header_value(raw_headers)
        # _safe_extra_headers strips the CLIENT_AUTH_HEADER_NAMES superset
        # (which includes user-agent, case-insensitively), so no caller value
        # for any gateway-owned header reaches `extra_headers`.
        extra_headers = _safe_extra_headers(raw_headers)
        # Gateway-owned headers set LAST so a caller value cannot override the
        # bearer token / content-type / user agent (findings U4). User-Agent is
        # always the gateway value — a caller's user-agent (any case) was
        # already dropped by _safe_extra_headers.
        request_headers = {
            **extra_headers,
            "User-Agent": self._settings.user_agent,
            "Authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        }
        session = await self._ensure_setup(str(session_key), request_headers, timeout)
        inner_body = build_generate_content_body(messages, optional_params)
        wrapped_body = {
            "project": session.project_id,
            "model": model,
            "request": inner_body,
            "userAgent": self._settings.user_agent,
            "requestId": str(uuid.uuid4()),
        }
        response, _endpoint = await self._post_with_fallback(
            "generateContent",
            request_headers,
            wrapped_body,
            timeout,
            preferred_endpoint=session.endpoint,
        )
        if response.status_code == 200:
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise CustomLLMError(
                    status_code=502,
                    message=f"Antigravity Code Assist response not JSON: {exc}",
                ) from exc
        elif _should_try_stream_generate_content(response):
            response, _endpoint = await self._post_with_fallback(
                "streamGenerateContent?alt=sse",
                request_headers,
                wrapped_body,
                timeout,
                preferred_endpoint=session.endpoint,
            )
            if response.status_code != 200:
                raise _error_from_response(response)
            data = _merge_stream_generate_content_sse(response.text)
        else:
            raise _error_from_response(response)
        if not isinstance(data, dict):
            raise CustomLLMError(
                status_code=502, message="Antigravity Code Assist response is not JSON"
            )
        return model_response_from_antigravity(data, model)


def ensure_litellm_antigravity_provider_registered(
    handler: AntigravityCustomLLM | None = None,
) -> None:
    global _HANDLER
    if handler is not None:
        _HANDLER = handler
    if _HANDLER is None:
        _HANDLER = AntigravityCustomLLM()
    for entry in litellm.custom_provider_map:
        if entry.get("provider") == PROVIDER:
            entry["custom_handler"] = _HANDLER
            litellm.utils.custom_llm_setup()
            return
    litellm.custom_provider_map.append({"provider": PROVIDER, "custom_handler": _HANDLER})
    litellm.utils.custom_llm_setup()


def get_litellm_antigravity_handler() -> AntigravityCustomLLM:
    ensure_litellm_antigravity_provider_registered()
    assert _HANDLER is not None
    return _HANDLER
