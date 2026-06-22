"""POST /v1/chat/completions — resolves profile auth + merges defaults, dispatches via LiteLLM."""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    UnsupportedParamsError,
)

from ..core.auth.middleware import CurrentAccount
from ..core.concurrency import effective_provider_limit, provider_slot
from ..core.credential_strategy_cache import credential_strategy_cache
from ..core.errors import AuthError, CredentialNotFoundError
from ..core.oauth.models import OAuthConnection
from ..core.oauth.store import OAuthConnectionStore, credential_key_for
from ..core.plugin_base import credential_strategy_from
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import (
    AuthType,
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
)
from ..core.registry import ProviderRegistry
from ..core.request_cache.keys import (
    KEY_VERSION,
    CacheBypass,
    CacheControls,
    CacheKeyResult,
    build_cache_key,
    parse_cache_controls,
)
from ..core.request_cache.store import RequestCacheStore, RequestCacheWrite
from ..core.retry import RetryPolicy, parse_retry_after_seconds, with_overload_retry

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_PROFILE_NAME = "default"


_BUCKET_A_FIELDS = (
    "model",
    "max_tokens",
    "temperature",
    "timeout_seconds",
    "reasoning_effort",
)


def _has_system_message(body: dict[str, Any]) -> bool:
    return any(m.get("role") == "system" for m in body.get("messages", []))


def _should_apply_profile_default(plugin: Any, field: str) -> bool:
    checker = getattr(plugin, "should_apply_profile_default", None)
    return bool(checker(field)) if callable(checker) else True


def _allows_chatless_profile(plugin: Any) -> bool:
    checker = getattr(plugin, "allows_chatless_profile", None)
    return bool(checker()) if callable(checker) else False


def _invalidate_profile_session(plugin: Any, profile_name: str) -> None:
    invalidator = getattr(plugin, "invalidate_profile_session", None)
    if callable(invalidator):
        invalidator(profile_name)


def _should_mark_profile_error_on_dispatch_status(plugin: Any, status_code: int) -> bool:
    checker = getattr(plugin, "should_mark_profile_error_on_dispatch_status", None)
    return bool(checker(status_code)) if callable(checker) else False


def _oauth_connection_store(request: Request) -> OAuthConnectionStore:
    store = getattr(request.app.state, "oauth_connections", None)
    if isinstance(store, OAuthConnectionStore):
        return store
    store = OAuthConnectionStore()
    request.app.state.oauth_connections = store
    return store


async def _active_oauth_connection_for_profile(
    request: Request,
    *,
    account_id: str,
    provider: str,
    profile_name: str,
) -> OAuthConnection | None:
    connections = await _oauth_connection_store(request).list(
        account_id,
        provider=provider,
        status="active",
    )
    if not connections:
        return None

    for connection in connections:
        if connection.label == profile_name:
            return connection

    if profile_name == _DEFAULT_PROFILE_NAME and len(connections) == 1:
        return connections[0]

    if profile_name == _DEFAULT_PROFILE_NAME:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "connection_ambiguous",
                "provider": provider,
                "message": (
                    "Multiple active connections exist. Select one by setting "
                    "X-Profile to the connection label."
                ),
            },
        )
    raise HTTPException(
        status_code=404,
        detail={
            "code": "connection_not_found",
            "provider": provider,
            "requested_label": profile_name,
            "valid_labels": [connection.label for connection in connections],
        },
    )


async def _credential_target_for_chat(
    request: Request,
    *,
    account_id: str,
    provider: str,
    profile_name: str,
    plugin: Any,
) -> tuple[Profile | None, OAuthConnection | None, ProfileDefaults]:
    idx: ProfileIndexStore = request.app.state.profile_index
    profile = await idx.get(account_id, provider, profile_name)
    if profile is None:
        connection = await _active_oauth_connection_for_profile(
            request,
            account_id=account_id,
            provider=provider,
            profile_name=profile_name,
        )
        if connection is not None:
            return None, connection, ProfileDefaults()
        if not _allows_chatless_profile(plugin):
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "profile_not_found",
                    "provider": provider,
                    "name": profile_name,
                },
            )
        return None, None, ProfileDefaults()

    if profile.state == ProfileState.PENDING:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "profile_pending_auth",
                "provider": provider,
                "name": profile_name,
            },
        )
    if profile.state == ProfileState.ERROR:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "provider": provider,
                "name": profile_name,
                "reauth_url": f"/v1/auth/{provider}/profiles/{profile_name}",
            },
        )
    return profile, None, profile.defaults


def _strategy_for_credential_target(
    request: Request,
    plugin: Any,
    provider: str,
    *,
    account_id: str,
    profile_name: str,
    profile: Profile | None,
    connection: OAuthConnection | None,
) -> tuple[Any, str | None, AuthType]:
    """Resolve (strategy, credential_name, auth_type) for the chat credential
    target, branching on the target's auth_type discriminator."""
    auth_type: AuthType
    if connection is not None:
        credential_name = credential_key_for(account_id, connection.id)
        auth_type = connection.auth_type or "oauth"
    elif profile is not None:
        credential_name = credential_name_for(account_id, profile_name)
        auth_type = profile.auth_type
    else:
        return None, None, "oauth"
    # Share ONE strategy instance per credential across concurrent requests so its
    # asyncio.Lock single-flights the OAuth refresh (SF-282). Building is only a
    # constructor call; the cache is evicted on every credential mutation.
    strategy = credential_strategy_cache(request.app).get_or_create(
        provider=provider,
        auth_type=auth_type,
        credential_name=credential_name,
        build=lambda: credential_strategy_from(
            plugin,
            credential_name,
            auth_type=auth_type,
            credential_store=request.app.state.credential_store,
            http_client_factory=getattr(request.app.state, f"{provider}_http_factory", None),
        ),
    )
    return strategy, credential_name, auth_type


def _reauth_url_for(
    provider: str,
    profile_name: str,
    auth_type: AuthType,
    *,
    connection_id: str | None = None,
) -> str:
    if connection_id is not None and auth_type == "api_key":
        # An api-key CONNECTION re-keys via its own replace route; never send the
        # user back to the legacy profile api-key endpoint, which would shadow
        # connections on chat (SF-291 review F3).
        return f"/v1/oauth/connections/{connection_id}/api-key"
    base = f"/v1/auth/{provider}/profiles/{profile_name}"
    return f"{base}/api-key" if auth_type == "api_key" else base


async def _mark_profile_error_fresh(
    request: Request,
    *,
    account_id: str,
    provider: str,
    profile_name: str,
) -> None:
    """Re-fetch the profile before flipping state so a long-running dispatch
    never clobbers concurrent index writes (e.g. a PUT api-key changing
    auth_type/account_label mid-flight) with its stale snapshot."""
    idx: ProfileIndexStore = request.app.state.profile_index
    fresh = await idx.get(account_id, provider, profile_name)
    if fresh is not None:
        fresh.state = ProfileState.ERROR
        await idx.upsert(fresh)


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
    await _mark_profile_error_fresh(
        request, account_id=account_id, provider=provider, profile_name=profile_name
    )
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


def _apply_defaults(body: dict[str, Any], defaults: ProfileDefaults, plugin: Any) -> dict[str, Any]:
    """Body wins per field. Fields the body omits get the profile default."""
    if (
        defaults.system_prompt
        and not _has_system_message(body)
        and _should_apply_profile_default(plugin, "system_prompt")
    ):
        body.setdefault("messages", [])
        body["messages"] = [
            {"role": "system", "content": defaults.system_prompt},
            *body["messages"],
        ]
    for field in _BUCKET_A_FIELDS:
        gateway_field = "timeout" if field == "timeout_seconds" else field
        if not _should_apply_profile_default(plugin, field):
            continue
        value = getattr(defaults, field)
        if value is not None and gateway_field not in body:
            body[gateway_field] = value
    return body


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


def _resolve_cache_plan(
    request: Request,
    *,
    account_id: str,
    profile_name: str,
    provider: str,
    body: dict[str, Any],
    controls: CacheControls,
) -> tuple[CacheKeyResult | None, str, str]:
    """Decide cache participation for this request.

    Returns ``(key, status, reason)`` where ``key`` is None whenever the
    request bypasses the cache. Status/reason feed the X-AIGW-Cache headers.
    """
    settings = request.app.state.settings
    if not settings.request_cache_enabled:
        return None, "bypass", "disabled"
    if not controls.use_cache:
        return None, "bypass", "not_requested"
    built = build_cache_key(
        account_id=account_id,
        profile_name=profile_name,
        provider=provider,
        normalized_body=body,
    )
    if isinstance(built, CacheBypass):
        return None, "bypass", built.reason
    return built, "miss", ""


def _set_cache_headers(
    response: Response, status: str, reason: str, key: CacheKeyResult | None
) -> None:
    response.headers["X-AIGW-Cache"] = status
    if reason:
        response.headers["X-AIGW-Cache-Reason"] = reason
    # Hash-derived prefix only — never prompt or response content.
    if key is not None and status in {"hit", "miss"}:
        response.headers["X-AIGW-Cache-Key"] = key.key_hash[:12]


async def _store_cached_response(
    request: Request,
    *,
    key: CacheKeyResult,
    account_id: str,
    result: Any,
    controls: CacheControls,
) -> str:
    """Persist a fresh response when allowed; returns the cache reason."""
    if controls.no_store:
        return "no_store"
    if not isinstance(result, dict):
        return "unsupported_fields"
    settings = request.app.state.settings
    payload_size = len(
        json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    if payload_size > settings.request_cache_max_response_bytes:
        return "too_large"
    ttl = min(
        controls.ttl or settings.request_cache_default_ttl_seconds,
        settings.request_cache_max_ttl_seconds,
    )
    store: RequestCacheStore = request.app.state.request_cache_store
    await store.set(
        RequestCacheWrite(
            key_hash=key.key_hash,
            key_version=KEY_VERSION,
            account_id=account_id,
            profile_name=key.profile_name,
            prompt_hash=key.prompt_hash,
            provider=key.provider,
            model=key.model,
            response=result,
            response_size_bytes=payload_size,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
        )
    )
    return "stored"


def _litellm_http_exception(exc: Exception) -> HTTPException:
    status = int(getattr(exc, "status_code", 502) or 502)
    code = "provider_error"
    if status == 400:
        code = "bad_request"
    elif status == 401:
        code = "auth_required"
    elif status == 429:
        code = "rate_limited"
    elif status >= 500:
        code = "provider_unavailable"
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": str(exc)},
        headers=_retry_after_headers(exc),
    )


async def _inject_credentials(
    request: Request,
    *,
    plugin: Any,
    provider: str,
    account_id: str,
    profile_name: str,
    profile: Profile | None,
    connection: OAuthConnection | None,
    body: dict[str, Any],
) -> tuple[str | None, AuthType]:
    """Resolve the profile/connection credential strategy and inject auth
    into ``body``; returns ``(credential_name, auth_type)`` for later dispatch
    failure handling. Raises 401 (marking profile/connection errored) when
    stored credentials are unusable."""
    strategy, credential_name, auth_type = _strategy_for_credential_target(
        request,
        plugin,
        provider,
        account_id=account_id,
        profile_name=profile_name,
        profile=profile,
        connection=connection,
    )
    if strategy is None and credential_name is not None and auth_type == "api_key":
        # Never fall through to an unauthenticated dispatch when the target
        # says api_key but the provider has no API-key strategy (SF-244 F15).
        raise HTTPException(
            status_code=400,
            detail={"code": "api_key_not_supported", "provider": provider},
        )
    if strategy is not None:
        try:
            headers = await strategy.get_authorization_header()
        except CredentialNotFoundError as exc:
            if credential_name is not None:
                credential_strategy_cache(request.app).evict(credential_name)
            if connection is not None:
                await _oauth_connection_store(request).mark_error(connection, str(exc))
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "auth_required",
                    "message": str(exc),
                    "reauth_url": _reauth_url_for(
                        provider,
                        profile_name,
                        auth_type,
                        connection_id=str(connection.id) if connection is not None else None,
                    ),
                },
            )
        except AuthError as exc:
            if credential_name is not None:
                credential_strategy_cache(request.app).evict(credential_name)
            if connection is not None:
                await _oauth_connection_store(request).mark_error(connection, str(exc))
                if credential_name is not None:
                    _invalidate_profile_session(plugin, credential_name)
            elif profile is not None:
                await _mark_profile_error_fresh(
                    request,
                    account_id=account_id,
                    provider=provider,
                    profile_name=profile_name,
                )
                if credential_name is not None:
                    _invalidate_profile_session(plugin, credential_name)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "auth_required",
                    "message": str(exc),
                    "reauth_url": _reauth_url_for(
                        provider,
                        profile_name,
                        auth_type,
                        connection_id=str(connection.id) if connection is not None else None,
                    ),
                },
            )
        auth_value = headers.pop("Authorization", None)
        if auth_value and auth_value.lower().startswith("bearer "):
            body["api_key"] = auth_value.split(" ", 1)[1]
        if headers:
            merged = dict(body.get("extra_headers") or {})
            merged.update(headers)
            body["extra_headers"] = merged
        if connection is not None:
            await _oauth_connection_store(request).touch_last_used(connection)

    return credential_name, auth_type


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, response: Response, current: CurrentAccount) -> Any:
    body = await request.json()
    if not isinstance(body, dict) or "model" not in body or "messages" not in body:
        raise HTTPException(status_code=400, detail="model and messages are required")

    # Popped immediately so the control object can never reach providers.
    cache_controls = parse_cache_controls(body)
    # The gateway owns upstream routing. A caller-supplied api_base would make
    # LiteLLM send the injected credential (API key / OAuth token) to an
    # arbitrary host — an exfiltration vector (SF-244 audit F03). Providers
    # that need one (ollama) set their own in prepare_chat_body.
    body.pop("api_base", None)

    profile_name = (request.headers.get("X-Profile") or "default").strip() or "default"
    model = body.get("model", "")
    provider = model.split("/", 1)[0] if "/" in model else None
    if not provider:
        raise HTTPException(status_code=400, detail="model must be provider-prefixed")

    registry: ProviderRegistry = request.app.state.providers
    plugin = registry.get(provider)
    if plugin is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    account_id = str(current.id)
    profile, connection, defaults = await _credential_target_for_chat(
        request,
        account_id=account_id,
        provider=provider,
        profile_name=profile_name,
        plugin=plugin,
    )

    body = plugin.prepare_chat_body(_apply_defaults(body, defaults, plugin))

    # Cache key is computed from the normalized body, before credential
    # injection, so no secret-bearing field can ever participate in the key.
    cache_key, cache_status, cache_reason = _resolve_cache_plan(
        request,
        account_id=account_id,
        profile_name=profile_name,
        provider=provider,
        body=body,
        controls=cache_controls,
    )

    if body.get("stream") and not plugin.supports_chat_streaming():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "streaming_not_supported",
                "provider": provider,
                "message": f"{provider} does not support streaming through this gateway yet",
            },
        )

    credential_name, auth_type = await _inject_credentials(
        request,
        plugin=plugin,
        provider=provider,
        account_id=account_id,
        profile_name=profile_name,
        profile=profile,
        connection=connection,
        body=body,
    )

    # NOTE: overload retry covers the non-streaming path only; streaming responses
    # commit a 200 status before dispatch, so a mid-stream 429/503 cannot be retried.
    if body.get("stream"):
        return StreamingResponse(
            _stream(plugin, body),
            media_type="text/event-stream",
            headers={"X-AIGW-Cache": "bypass", "X-AIGW-Cache-Reason": cache_reason or "stream"},
        )

    if cache_key is not None and not cache_controls.no_cache:
        cache_store: RequestCacheStore = request.app.state.request_cache_store
        cached = await cache_store.get(cache_key.key_hash, max_age_seconds=cache_controls.s_maxage)
        if cached is not None:
            _set_cache_headers(response, "hit", "", cache_key)
            logger.info(
                "request cache hit provider=%s model=%s account=%s profile=%s key=%s…",
                provider,
                cache_key.model,
                account_id,
                profile_name,
                cache_key.key_hash[:12],
            )
            return cached

    try:
        provider_response = await _dispatch_with_backpressure(request, plugin, provider, body)
    except HTTPException as exc:
        raise await _dispatch_failure_response(
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
    except (
        RateLimitError,
        UnsupportedParamsError,
        BadRequestError,
        AuthenticationError,
        APIError,
        APIConnectionError,
        ServiceUnavailableError,
        Timeout,
    ) as exc:
        raise await _dispatch_failure_response(
            request,
            _litellm_http_exception(exc),
            plugin=plugin,
            provider=provider,
            account_id=account_id,
            profile_name=profile_name,
            profile=profile,
            connection=connection,
            credential_name=credential_name,
            auth_type=auth_type,
        ) from exc
    dumpable = cast(Any, provider_response)
    result = dumpable.model_dump() if hasattr(dumpable, "model_dump") else provider_response

    if cache_key is not None:
        cache_reason = await _store_cached_response(
            request,
            key=cache_key,
            account_id=account_id,
            result=result,
            controls=cache_controls,
        )
    _set_cache_headers(response, cache_status, cache_reason, cache_key)
    if cache_status != "bypass":
        logger.info(
            "request cache %s reason=%s provider=%s account=%s profile=%s key=%s…",
            cache_status,
            cache_reason,
            provider,
            account_id,
            profile_name,
            cache_key.key_hash[:12] if cache_key is not None else "",
        )
    return result


async def _stream(plugin: Any, body: dict[str, Any]):
    try:
        async for chunk in plugin.chat_completion_stream(body):
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("stream failed")
        err = {"error": {"message": str(exc), "type": type(exc).__name__}}
        yield f"data: {json.dumps(err)}\n\n"
