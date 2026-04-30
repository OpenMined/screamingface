"""POST /v1/chat/completions — resolves OAuth, proxies to litellm.acompletion.

LiteLLM validates credentials before any `input_callback` fires, so the
OAuth bridge can't be a pure post-hoc callback for auth — we resolve the
provider plugin's headers here, in the route, and pass the bearer token
explicitly via `api_key` (Anthropic detects oauth tokens by the
`sk-ant-oat` prefix; for other providers it lands as the bearer auth).
The remaining provider-specific headers (e.g. `anthropic-version`,
`anthropic-beta`) are forwarded via `extra_headers`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.registry import ProviderRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


async def _resolve_auth(
    body: dict[str, Any], registry: ProviderRegistry
) -> tuple[dict[str, Any], dict[str, str]]:
    """Mutate `body` with auth_token / extra_headers from the matching provider plugin.

    Returns (body, extra_headers) — `extra_headers` is also stored on body
    so LiteLLM forwards it to the upstream HTTP call. The bearer token
    (if present in the strategy's headers) is moved into `api_key` so it
    survives LiteLLM's pre-dispatch credential check.
    """
    model = body.get("model", "")
    provider = model.split("/", 1)[0] if "/" in model else None
    if not provider:
        return body, {}

    plugin = registry.get(provider)
    if plugin is None:
        return body, {}

    strategy = plugin.oauth_strategy()
    if strategy is None:
        return body, {}

    headers = await strategy.get_authorization_header()

    auth_value = headers.pop("Authorization", None)
    if auth_value and auth_value.lower().startswith("bearer "):
        body.setdefault("api_key", auth_value.split(" ", 1)[1])

    if headers:
        merged = dict(body.get("extra_headers") or {})
        merged.update(headers)
        body["extra_headers"] = merged

    return body, headers


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()
    if not isinstance(body, dict) or "model" not in body or "messages" not in body:
        raise HTTPException(status_code=400, detail="model and messages are required")

    registry: ProviderRegistry = request.app.state.providers
    body, _ = await _resolve_auth(body, registry)

    if body.get("stream"):
        return StreamingResponse(_stream(body), media_type="text/event-stream")

    response = await litellm.acompletion(**body)
    return response.model_dump() if hasattr(response, "model_dump") else response


async def _stream(body: dict[str, Any]):
    try:
        stream = await litellm.acompletion(**body)
        async for chunk in stream:
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("stream failed")
        err = {"error": {"message": str(exc), "type": type(exc).__name__}}
        yield f"data: {json.dumps(err)}\n\n"
