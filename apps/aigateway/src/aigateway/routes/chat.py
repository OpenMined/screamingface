"""POST /v1/chat/completions — resolves profile auth + merges defaults, dispatches via LiteLLM."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.auth.middleware import CurrentAccount
from ..core.errors import AuthError, CredentialNotFoundError
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import ProfileDefaults, ProfileState
from ..core.registry import ProviderRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


_BUCKET_A_FIELDS = (
    "model",
    "max_tokens",
    "temperature",
    "timeout_seconds",
    "reasoning_effort",
)


def _has_system_message(body: dict[str, Any]) -> bool:
    return any(m.get("role") == "system" for m in body.get("messages", []))


def _apply_defaults(body: dict[str, Any], defaults: ProfileDefaults) -> dict[str, Any]:
    """Body wins per field. Fields the body omits get the profile default."""
    if defaults.system_prompt and not _has_system_message(body):
        body.setdefault("messages", [])
        body["messages"] = [
            {"role": "system", "content": defaults.system_prompt},
            *body["messages"],
        ]
    for field in _BUCKET_A_FIELDS:
        gateway_field = "timeout" if field == "timeout_seconds" else field
        value = getattr(defaults, field)
        if value is not None and gateway_field not in body:
            body[gateway_field] = value
    return body


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, _current: CurrentAccount) -> Any:
    body = await request.json()
    if not isinstance(body, dict) or "model" not in body or "messages" not in body:
        raise HTTPException(status_code=400, detail="model and messages are required")

    profile_name = request.headers.get("X-Profile", "default")
    model = body.get("model", "")
    provider = model.split("/", 1)[0] if "/" in model else None
    if not provider:
        raise HTTPException(status_code=400, detail="model must be prefixed (e.g. anthropic/...)")

    registry: ProviderRegistry = request.app.state.providers
    plugin = registry.get(provider)
    if plugin is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    idx: ProfileIndexStore = request.app.state.profile_index
    profile = await idx.get(provider, profile_name)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "profile_not_found",
                "provider": provider,
                "name": profile_name,
            },
        )
    if profile.state == ProfileState.PENDING:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "profile_pending_auth",
                "provider": provider,
                "name": profile_name,
            },
        )

    body = _apply_defaults(body, profile.defaults)

    strategy = plugin.oauth_strategy_for(profile_name)
    if strategy is not None:
        # Same `_store` injection pattern Tasks 7-9 introduced for parity with the
        # tests' fake keychain. In production both reference the same singleton.
        if hasattr(strategy, "_store"):
            strategy._store = idx._store  # type: ignore[attr-defined]
        try:
            headers = await strategy.get_authorization_header()
        except CredentialNotFoundError as exc:
            raise HTTPException(
                status_code=401,
                detail={"code": "auth_required", "message": str(exc)},
            )
        except AuthError as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "auth_required",
                    "message": str(exc),
                    "reauth_url": f"/v1/auth/{provider}/profiles/{profile_name}",
                },
            )
        auth_value = headers.pop("Authorization", None)
        if auth_value and auth_value.lower().startswith("bearer "):
            body.setdefault("api_key", auth_value.split(" ", 1)[1])
        if headers:
            merged = dict(body.get("extra_headers") or {})
            merged.update(headers)
            body["extra_headers"] = merged

    if body.get("stream"):
        return StreamingResponse(_stream(body), media_type="text/event-stream")

    response: Any = await litellm.acompletion(**body)
    return response.model_dump() if hasattr(response, "model_dump") else response


async def _stream(body: dict[str, Any]):
    try:
        stream: Any = await litellm.acompletion(**body)
        async for chunk in stream:
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("stream failed")
        err = {"error": {"message": str(exc), "type": type(exc).__name__}}
        yield f"data: {json.dumps(err)}\n\n"
