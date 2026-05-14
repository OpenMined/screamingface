from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
from litellm.llms.custom_llm import CustomLLM, CustomLLMError
from litellm.types.utils import Choices, Message, ModelResponse

from .models import CODEX_MODEL_SLUGS
from .oauth_config import CODEX_ORIGINATOR, codex_chatgpt_responses_url

_ALLOWED_PAYLOAD_KEYS = {
    "model",
    "input",
    "instructions",
    "stream",
    "store",
    "include",
    "tools",
    "tool_choice",
    "reasoning",
    "previous_response_id",
    "truncation",
}


class CodexChatGPTHandler(CustomLLM):
    async def acompletion(
        self,
        model: str,
        messages: list,
        api_base: str,
        custom_prompt_dict: dict,
        model_response: ModelResponse,
        print_verbose: Callable,
        encoding,
        api_key,
        logging_obj,
        optional_params: dict,
        acompletion=None,
        litellm_params=None,
        logger_fn=None,
        headers={},
        timeout: float | httpx.Timeout | None = None,
        client: AsyncHTTPHandler | None = None,
    ) -> ModelResponse:
        slug = _slug_from_model(model)
        if api_key and _looks_like_openai_api_key(str(api_key)):
            raise CustomLLMError(
                status_code=400,
                message=(
                    f"codex/{slug} is not available via OpenAI API key; "
                    "this gateway profile requires a ChatGPT subscription OAuth token"
                ),
            )
        if not api_key:
            raise CustomLLMError(status_code=401, message="missing Codex OAuth bearer token")

        extra_headers = dict(headers or {})
        extra_headers.update(optional_params.pop("extra_headers", {}) or {})
        payload = _build_payload(slug, messages, optional_params)
        request_headers = _build_headers(str(api_key), extra_headers)
        timeout_value = timeout if timeout is not None else httpx.Timeout(300.0)

        async with httpx.AsyncClient(timeout=timeout_value) as http_client:
            response = await http_client.post(
                codex_chatgpt_responses_url(),
                json=payload,
                headers=request_headers,
            )
        if response.status_code >= 400:
            raise CustomLLMError(
                status_code=response.status_code,
                message=(
                    f"Codex backend returned HTTP {response.status_code}: {response.text[:500]}"
                ),
            )

        content = _parse_responses_sse(response.text)
        model_response.choices = [
            Choices(index=0, message=Message(content=content, role="assistant"))
        ]
        model_response.created = int(time.time())
        model_response.model = f"codex/{slug}"
        return model_response


def _slug_from_model(model: str) -> str:
    prefix = "codex/"
    slug = model[len(prefix) :] if model.startswith(prefix) else model
    if not slug or slug not in CODEX_MODEL_SLUGS:
        raise CustomLLMError(
            status_code=400, message=f"missing or unknown codex model slug: {model!r}"
        )
    return slug


def _looks_like_openai_api_key(value: str) -> bool:
    return value.startswith("sk-") or value.startswith("sk-proj-")


def _build_headers(api_key: str, extra_headers: dict[str, str]) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "accept": "text/event-stream",
        "originator": CODEX_ORIGINATOR,
        "user-agent": "codex_cli_rs/0.130.0",
        "session_id": str(uuid.uuid4()),
    }
    account_id = extra_headers.get("ChatGPT-Account-Id") or extra_headers.get("chatgpt-account-id")
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _build_payload(slug: str, messages: list, optional_params: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": slug,
        "input": _messages_to_input(messages),
        "instructions": _messages_to_instructions(messages),
        "stream": True,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "reasoning": optional_params.get("reasoning") or {"effort": "medium"},
    }
    for key in ("tools", "tool_choice", "previous_response_id", "truncation"):
        if key in optional_params:
            payload[key] = optional_params[key]
    return {key: value for key, value in payload.items() if key in _ALLOWED_PAYLOAD_KEYS}


def _messages_to_instructions(messages: list) -> str:
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "developer"}:
            continue
        text = _content_to_text(message.get("content"))
        if text:
            parts.append(text)
    return "\n\n".join(parts) if parts else "You are a helpful assistant."


def _messages_to_input(messages: list) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role in {"system", "developer"}:
            continue
        text = _content_to_text(message.get("content"))
        if not text:
            continue
        items.append(
            {
                "role": "assistant" if role == "assistant" else "user",
                "content": [{"type": "input_text", "text": text}],
            }
        )
    return items or [{"role": "user", "content": [{"type": "input_text", "text": ""}]}]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "\n".join(parts)
    return ""


def _parse_responses_sse(text: str) -> str:
    parts: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        event_type = data.get("type")
        if event_type == "response.output_text.delta":
            delta = data.get("delta")
            if isinstance(delta, str):
                parts.append(delta)
        elif event_type == "response.completed":
            response = data.get("response")
            if isinstance(response, dict):
                output = response.get("output_text")
                if isinstance(output, str) and not parts:
                    parts.append(output)
    return "".join(parts)


HANDLER = CodexChatGPTHandler()
