"""Antigravity LiteLLM custom handler + Code Assist transport.

OAuth-only (no API-key path). Generation tries non-streaming
``:generateContent`` FIRST (mirrors the Gemini gateway path; the SSE-aggregation
fallback is the documented contingency — findings U6). The Code Assist host is
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
                    "ideType": "IDE_UNSPECIFIED",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "ANTIGRAVITY",
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
        extra_headers = _safe_extra_headers(raw_headers)
        # Gateway-owned headers set LAST so a caller value cannot override the
        # bearer token / content-type / user agent (findings U4).
        request_headers = {
            "User-Agent": extra_headers.pop("User-Agent", self._settings.user_agent),
            **extra_headers,
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
        if response.status_code != 200:
            raise _error_from_response(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise CustomLLMError(
                status_code=502,
                message=f"Antigravity Code Assist response not JSON: {exc}",
            ) from exc
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
