"""Dispatch-side helpers for /v1/chat/completions.

Everything after the body is credential-sealed lives here: backpressure +
overload retry, LiteLLM-exception → HTTP mapping, dispatch-failure credential
marking, and SSE streaming. Split out of routes/chat.py (OME-428 Phase 1) behind
characterization tests; behavior is unchanged.

OME-305: request-cache planning and persistence NO LONGER live here. The v1 stage
belonged on the dispatch side because its key was account- and profile-scoped, so it
could only be built after credentials were resolved. The v2 cache is global and must
be consulted BEFORE any identity exists, so the whole stage moved to
``chat_cache_stage`` — which the route calls ahead of this module, not after it.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from fastapi import HTTPException, Request

from ..core.concurrency import effective_provider_limit, provider_slot
from ..core.credential_strategy_cache import credential_strategy_cache
from ..core.http_status import valid_http_error_status
from ..core.oauth.models import OAuthConnection
from ..core.profile_models import AuthType, Profile
from ..core.retry import RetryPolicy, parse_retry_after_seconds, with_overload_retry
from .chat_credentials import (
    _invalidate_profile_session,
    _mark_profile_error_fresh,
    _oauth_connection_store,
    _reauth_url_for,
)

logger = logging.getLogger(__name__)


def _should_mark_profile_error_on_dispatch_status(plugin: Any, status_code: int) -> bool:
    checker = getattr(plugin, "should_mark_profile_error_on_dispatch_status", None)
    return bool(checker(status_code)) if callable(checker) else False


async def _dispatch_failure_response(
    request: Request,
    exc: HTTPException,
    *,
    plugin: Any,
    provider: str,
    account_id: str,
    profile_name: str,
    profile: Profile | None,
    connection: OAuthConnection | None,
    credential_name: str | None,
    auth_type: AuthType,
) -> HTTPException:
    """Mark the credential target on auth-meaning dispatch failures.

    Shared by the HTTPException path (custom handlers raise these) and the
    LiteLLM-exception path (e.g. anthropic AuthenticationError), so a bad
    stored credential flips the profile/connection to ERROR regardless of
    which exception family the provider dispatch uses.
    """
    if not _should_mark_profile_error_on_dispatch_status(plugin, exc.status_code):
        return exc
    # Drop the cached strategy so its (now bad) token isn't reused by the next
    # request — important under fan-out where many requests share the instance.
    if credential_name is not None:
        credential_strategy_cache(request.app).evict(credential_name)
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    if connection is not None:
        await _oauth_connection_store(request).mark_error(
            connection,
            str(detail.get("message", str(exc.detail))),
        )
        if credential_name is not None:
            _invalidate_profile_session(plugin, credential_name)
        return exc
    if profile is None:
        return exc
    await _mark_profile_error_fresh(request, profile=profile)
    if credential_name is not None:
        _invalidate_profile_session(plugin, credential_name)
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": detail.get("code", "auth_required"),
            "message": detail.get("message", str(exc.detail)),
            "reauth_url": detail.get(
                "reauth_url", _reauth_url_for(provider, profile_name, auth_type)
            ),
        },
    )


async def _safe_dispatch_failure_response(
    request: Request,
    exc: HTTPException,
    *,
    plugin: Any,
    provider: str,
    account_id: str,
    profile_name: str,
    profile: Profile | None,
    connection: OAuthConnection | None,
    credential_name: str | None,
    auth_type: AuthType,
) -> HTTPException:
    """Contain secondary failures while rendering/persisting dispatch errors."""
    try:
        return await _dispatch_failure_response(
            request,
            exc,
            plugin=plugin,
            provider=provider,
            account_id=account_id,
            profile_name=profile_name,
            profile=profile,
            connection=connection,
            credential_name=credential_name,
            auth_type=auth_type,
        )
    except Exception as failure:
        logger.error(
            "dispatch failure handling error type=%s provider=%s account=%s profile=%s",
            type(failure).__name__,
            provider,
            account_id,
            profile_name,
        )
        return _unknown_provider_exception()


def _retry_after_headers(exc: Exception) -> dict[str, str]:
    seconds = parse_retry_after_seconds(exc)
    if seconds is None:
        return {}
    # delta-seconds is an integer; round up so clients do not retry early.
    return {"Retry-After": str(math.ceil(seconds))}


async def _dispatch_with_backpressure(
    request: Request,
    plugin: Any,
    provider: str,
    body: dict[str, Any],
) -> Any:
    """Run ``plugin.chat_completion`` under the gateway's backpressure stack:
    a per-provider concurrency slot wrapping the overload-retry loop.

    The slot is held across retries so a provider's concurrent-pressure
    ceiling includes backoff time — preventing the thundering-herd quota
    re-exhaustion that pure reactive retry could not solve.
    """
    settings = request.app.state.settings
    async with provider_slot(request.app, provider, effective_provider_limit(settings, provider)):
        return await with_overload_retry(
            lambda: plugin.chat_completion(body),
            policy=RetryPolicy.from_settings(settings),
        )


# WHY (FINDING B): the client-facing message is gateway-authored per machine
# code — NEVER str(exc), which serializes the raw LiteLLM/provider text (and any
# secret embedded in it) into the response, logs, and (for a 401, via
# _dispatch_failure_response) persisted connection error state.
# INVARIANT: this generic sanitizer applies only to RAW LiteLLM/provider
# exceptions (route Branch B); errors already authored safely by gateway policy
# (route Branch A HTTPExceptions) keep their curated detail unchanged.
_PROVIDER_ERROR_MESSAGE = {
    "bad_request": "The upstream provider rejected the request.",
    "auth_required": "The stored provider credential was rejected.",
    "rate_limited": "The upstream provider is rate limiting requests.",
    "provider_unavailable": "The upstream provider is temporarily unavailable.",
    "provider_error": "The upstream provider returned an error.",
}


def _sanitized_provider_status(exc: Exception) -> int | None:
    """A validated provider HTTP error status (400-599), else ``None``.

    # WHY (FINDING B / blocker E): never ``int(status_code)`` — a malformed
    # provider status (e.g. 'not-a-status' or the Unicode '²') would raise and
    # 500. One strict shared validator (rejects bool/str/float) is used here and
    # by the OpenRouter plugin/provenance so the three sites cannot diverge.
    """
    try:
        status = getattr(exc, "status_code", None)
    except Exception:
        return None
    return valid_http_error_status(status)


def _provider_error_code(status: int, *, validated: bool) -> str:
    if status == 400:
        return "bad_request"
    if status == 401:
        return "auth_required"
    if status == 429:
        return "rate_limited"
    if validated and status >= 500:
        return "provider_unavailable"
    # An absent/malformed status resolves to 502 but stays "provider_error"
    # (mirrors the OpenRouter plugin's _embedded_error_exception): only a
    # provider-validated 5xx earns the more specific "provider_unavailable".
    return "provider_error"


def _litellm_http_exception(exc: Exception) -> HTTPException:
    status = _sanitized_provider_status(exc)
    resolved = status if status is not None else 502
    code = _provider_error_code(resolved, validated=status is not None)
    return HTTPException(
        status_code=resolved,
        detail={"code": code, "message": _PROVIDER_ERROR_MESSAGE[code]},
        headers=_retry_after_headers(exc),
    )


def _unknown_provider_exception() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "provider_error", "message": _PROVIDER_ERROR_MESSAGE["provider_error"]},
    )


async def _stream(plugin: Any, body: dict[str, Any]):
    try:
        async for chunk in plugin.chat_completion_stream(body):
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        # INVARIANT: provider-controlled exception text and traceback data stay out of logs.
        logger.error(
            "stream failed type=%s plugin=%s",
            type(exc).__name__,
            type(plugin).__name__,
        )
        err = {
            "error": {
                "code": "provider_error",
                "message": _PROVIDER_ERROR_MESSAGE["provider_error"],
            }
        }
        yield f"data: {json.dumps(err)}\n\n"
