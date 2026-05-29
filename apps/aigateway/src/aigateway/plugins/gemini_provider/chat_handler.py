from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import litellm
from litellm.llms.custom_llm import CustomLLM, CustomLLMError
from litellm.types.utils import ModelResponse

from .auth import GEMINI_PROFILE_HEADER, GEMINI_USER_AGENT
from .message_adapter import (
    PROVIDER,
    build_generate_content_body,
    model_response_from_gemini,
    strip_provider_prefix,
)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"
_HANDLER: GeminiCustomLLM | None = None
_CLIENT_AUTH_HEADER_NAMES = {
    "authorization",
    "content-type",
    "x-aigw-gemini-profile",
    "x-goog-api-key",
    "x-goog-user-project",
}


@dataclass
class _CodeAssistSession:
    project_id: str | None = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _env_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _safe_extra_headers(headers: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or key.lower() in _CLIENT_AUTH_HEADER_NAMES:
            continue
        if value is None:
            continue
        safe[key] = str(value)
    return safe


def _profile_header_value(headers: dict[str, Any]) -> str:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == GEMINI_PROFILE_HEADER.lower() and value:
            return str(value)
    return "default"


_RESET_AFTER_RE = re.compile(r"reset after (\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
_RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def parse_gemini_retry_after(response_text: str, headers: Any) -> float | None:
    """Extract a retry-after delay (seconds) from a Gemini 429.

    Google surfaces the reset window in the response *body* (a ``RetryInfo``
    ``retryDelay`` or the human "reset after Ns" phrasing), not a standard
    ``Retry-After`` header — so the generic header parser misses it. Honors a
    real header first, then ``retryDelay``, then the prose form. Returns
    ``None`` when nothing matches (caller falls back to exponential backoff).
    """
    raw = headers.get("retry-after") if headers is not None else None
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    for pattern in (_RETRY_DELAY_RE, _RESET_AFTER_RE):
        match = pattern.search(response_text or "")
        if match:
            return max(0.0, float(match.group(1)))
    return None


def _error_from_response(response: httpx.Response, provider_name: str) -> CustomLLMError:
    status = response.status_code
    if status in (401, 403):
        return CustomLLMError(
            status_code=status,
            message=f"Gemini {provider_name} rejected credentials",
        )
    body = response.text
    preview = body[:500]
    suffix = f": {preview}" if preview else ""
    error = CustomLLMError(
        status_code=status,
        message=f"Gemini {provider_name} request failed with status {status}{suffix}",
    )
    # Stash the provider's own reset window so the retry loop can honor it.
    error.retry_after = parse_gemini_retry_after(body, response.headers)  # type: ignore[attr-defined]
    return error


class GeminiCustomLLM(CustomLLM):
    def __init__(self, http_client_factory=None) -> None:
        super().__init__()
        self._http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        )
        self._sessions: dict[str, _CodeAssistSession] = {}

    async def acompletion(
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
        normalized_messages = [message for message in messages if isinstance(message, dict)]
        model_slug = strip_provider_prefix(model)
        if api_key:
            return await self._run_oauth(
                model_slug,
                normalized_messages,
                optional_params or {},
                str(api_key),
                headers or {},
                timeout,
            )

        env_key = _env_api_key()
        if env_key:
            return await self._run_api_key(
                model_slug,
                normalized_messages,
                optional_params or {},
                env_key,
                timeout,
            )
        raise CustomLLMError(
            status_code=401,
            message="Gemini requires an OAuth profile or GEMINI_API_KEY/GOOGLE_API_KEY",
        )

    def _session_for(self, session_key: str) -> _CodeAssistSession:
        session = self._sessions.get(session_key)
        if session is None:
            session = _CodeAssistSession()
            self._sessions[session_key] = session
        return session

    def invalidate_session(self, session_key: str) -> None:
        self._sessions.pop(session_key, None)

    async def _ensure_setup(
        self,
        session_key: str,
        request_headers: dict[str, str],
        timeout: Any,
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
                    "pluginType": "GEMINI",
                }
            }
            url = f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}:loadCodeAssist"
            try:
                async with self._http_client_factory() as http_client:
                    response = await http_client.post(
                        url,
                        json=body,
                        headers=request_headers,
                        timeout=timeout,
                    )
            except httpx.RequestError as exc:
                raise CustomLLMError(
                    status_code=502,
                    message=f"Gemini Code Assist setup unreachable: {exc}",
                ) from exc
            if response.status_code != 200:
                raise _error_from_response(response, "Code Assist setup")
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise CustomLLMError(
                    status_code=502,
                    message=f"Gemini Code Assist setup response not JSON: {exc}",
                ) from exc
            project_id = data.get("cloudaicompanionProject") if isinstance(data, dict) else None
            if not isinstance(project_id, str) or not project_id:
                raise CustomLLMError(
                    status_code=502,
                    message="Gemini Code Assist setup did not return cloudaicompanionProject",
                )
            session.project_id = project_id
            return session

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
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "content-type": "application/json",
            "User-Agent": extra_headers.pop("User-Agent", GEMINI_USER_AGENT),
        }
        request_headers.update(extra_headers)
        session = await self._ensure_setup(str(session_key), request_headers, timeout)
        inner_body = build_generate_content_body(messages, optional_params)
        wrapped_body = {
            "model": model,
            "project": session.project_id,
            "user_prompt_id": str(uuid.uuid4()),
            "request": {**inner_body, "session_id": session.session_id},
        }
        url = f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}:generateContent"
        try:
            async with self._http_client_factory() as http_client:
                response = await http_client.post(
                    url,
                    json=wrapped_body,
                    headers=request_headers,
                    timeout=timeout,
                )
        except httpx.RequestError as exc:
            raise CustomLLMError(
                status_code=502,
                message=f"Gemini Code Assist request unreachable: {exc}",
            ) from exc
        if response.status_code != 200:
            raise _error_from_response(response, "Code Assist")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise CustomLLMError(
                status_code=502,
                message=f"Gemini Code Assist response not JSON: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise CustomLLMError(status_code=502, message="Gemini Code Assist response is not JSON")
        return model_response_from_gemini(data, model)

    async def _run_api_key(
        self,
        model: str,
        messages: list[dict[str, Any]],
        optional_params: dict[str, Any],
        api_key: str,
        timeout: Any,
    ) -> ModelResponse:
        body = build_generate_content_body(messages, optional_params)
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        try:
            async with self._http_client_factory() as http_client:
                response = await http_client.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.RequestError as exc:
            raise CustomLLMError(
                status_code=502,
                message=f"Gemini API request unreachable: {exc}",
            ) from exc
        if response.status_code != 200:
            raise _error_from_response(response, "API")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise CustomLLMError(
                status_code=502,
                message=f"Gemini API response not JSON: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise CustomLLMError(status_code=502, message="Gemini API response is not JSON")
        return model_response_from_gemini(data, model)


def ensure_litellm_gemini_provider_registered(handler: GeminiCustomLLM | None = None) -> None:
    global _HANDLER
    if handler is not None:
        _HANDLER = handler
    if _HANDLER is None:
        _HANDLER = GeminiCustomLLM()
    for entry in litellm.custom_provider_map:
        if entry.get("provider") == PROVIDER:
            entry["custom_handler"] = _HANDLER
            litellm.utils.custom_llm_setup()
            return
    litellm.custom_provider_map.append({"provider": PROVIDER, "custom_handler": _HANDLER})
    litellm.utils.custom_llm_setup()


def get_litellm_gemini_handler() -> GeminiCustomLLM:
    ensure_litellm_gemini_provider_registered()
    assert _HANDLER is not None
    return _HANDLER
