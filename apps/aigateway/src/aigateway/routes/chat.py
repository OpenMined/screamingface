"""POST /v1/chat/completions — resolves profile auth + merges defaults, dispatches via LiteLLM.

Helper seams live in sibling modules (OME-428 Phase 1 split):
``chat_credentials`` (profile/connection resolution, defaults, credential
injection) and ``chat_dispatch`` (backpressure, error mapping, request cache,
streaming). This module keeps only the router and the request orchestration.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
    UnprocessableEntityError,
    UnsupportedParamsError,
)

from ..core.auth.middleware import CurrentAccount
from ..core.parameter_projection import (
    IncompatibleParametersError,
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from ..core.registry import ProviderRegistry
from ..core.request_cache.keys import parse_cache_controls
from ..core.request_cache.store import RequestCacheStore
from ..core.request_hardening import chat_body_shape_error, strip_dispatch_controls
from .chat_credentials import (
    _apply_defaults,
    _credential_target_for_chat,
    _inject_credentials,
    resolved_auth_mode,
)
from .chat_dispatch import (
    _dispatch_with_backpressure,
    _litellm_http_exception,
    _resolve_cache_plan,
    _safe_dispatch_failure_response,
    _set_cache_headers,
    _store_cached_response,
    _stream,
    _unknown_provider_exception,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _parameter_rejection_exception(
    exc: UnsupportedParametersError,
    *,
    provider: str,
    profile_name: str,
    default_paths: frozenset[str],
) -> HTTPException:
    """Render a classification failure against the source that actually caused it.

    WHY two codes (OME-638): profile defaults are classified in the SAME pass as
    caller fields, so one rejection map can mix an operator-configuration fault
    with a request fault. Reporting a stored default under
    ``unsupported_parameters`` would send the caller hunting through a request
    that does not contain the named field, so a rejection caused solely by
    defaults gets its own code and names the profile instead. 400 either way,
    matching ``api_key_not_supported`` — stored configuration this provider
    cannot serve is a bad request, not a server fault.

    INVARIANT: the caller-facing ``rejected`` map lists only paths the CALLER
    supplied. Defaults occupy only omitted paths, so the two sets are disjoint and
    neither error can echo the other's fields.

    WHY a caller fault wins when both are present: the request has to be fixed
    regardless, and it is the only half the caller can act on. The profile half is
    logged for the operator rather than dropped.
    """
    caller_rejected = {
        path: reason for path, reason in exc.rejected.items() if path not in default_paths
    }
    if caller_rejected:
        return HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_parameters",
                "provider": provider,
                "rejected": caller_rejected,
                "message": (
                    "one or more parameters are not enabled for this model; "
                    "see the model parameter contract"
                ),
            },
        )
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_profile_defaults",
            "provider": provider,
            "profile": profile_name,
            "rejected": exc.rejected,
            "message": (
                "the stored profile defaults are not enabled for this model; "
                "see the model parameter contract"
            ),
        },
    )


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, response: Response, current: CurrentAccount) -> Any:
    try:
        body = await request.json()
    except ValueError:
        # Malformed JSON is untrusted input, not a server fault (OME-428 D6).
        raise HTTPException(status_code=400, detail="request body must be valid JSON") from None
    shape_error = chat_body_shape_error(body)
    if shape_error is not None:
        raise HTTPException(status_code=400, detail=shape_error)

    # Popped immediately so the control object can never reach providers.
    cache_controls = parse_cache_controls(body)
    # The gateway owns upstream routing and credentials. Caller-supplied
    # LiteLLM control-plane fields (api_key/api_base/base_url/fallbacks/
    # model_list/...) would let LiteLLM send the injected credential to an
    # arbitrary host or bend dispatch behavior (SF-244 audit F03, OME-428 D6).
    # Providers that need an api_base (ollama) set their own in
    # prepare_chat_body; the gateway credential is injected after this strip.
    body = strip_dispatch_controls(body)

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

    # OME-479 §4.5 tier (a): neutralize this provider's own LiteLLM control-plane
    # fields (caching/guardrails/prompt-management/named-credential selectors)
    # BEFORE classification, so they are authorized structurally instead of being
    # rejected as unknown model params. Pairs with the provider-neutral
    # strip_dispatch_controls already applied at ingress; the default is identity.
    body = plugin.strip_provider_dispatch_controls(body)

    auth_mode = resolved_auth_mode(profile, connection, plugin=plugin)

    # OME-638: merge the gateway-trusted profile defaults BEFORE classification, so
    # a stored default is authorized by the same rule set, the same schema and the
    # same resolved auth mode as a caller-supplied value — one pass, one projection,
    # no second validation path to drift. Placed after both control-plane strips so
    # those keep seeing caller input only; ProfileDefaults is a closed model of six
    # typed fields and can carry no dispatch control.
    # INVARIANT: the body still wins per field, so a default occupies only a path
    # the caller omitted — which is what makes ``default_paths`` a sound attribution.
    body, default_paths = _apply_defaults(body, defaults, plugin)

    # OME-479 §4.5: classify every optional parameter against the provider's enabled
    # rule set for the REAL (never caller-declared) auth mode, and project accepted
    # fields into a fresh normalized body. This runs before provider normalization,
    # cache planning, and (crucially) credential injection — so unknown, disabled,
    # wrong-auth, malformed and duplicate-channel parameters fail closed with
    # HTTP-safe paths before any credential is read or any provider is dispatched.
    try:
        body = classify_and_project_chat_parameters(
            body,
            rules=plugin.chat_parameter_rules(model=model, auth_type=auth_mode),
            auth_mode=auth_mode,
        )
    except UnsupportedParametersError as exc:
        rejected_defaults = sorted(default_paths & exc.rejected.keys())
        if rejected_defaults:
            # The caller cannot fix a stored default and may never see it (a caller
            # fault outranks it in the response), so it goes to the operator's own
            # channel. Reason codes only — the classifier never carries raw values.
            logger.warning(
                "profile defaults rejected provider=%s account=%s profile=%s paths=%s",
                provider,
                account_id,
                profile_name,
                ",".join(rejected_defaults),
            )
        raise _parameter_rejection_exception(
            exc,
            provider=provider,
            profile_name=profile_name,
            default_paths=default_paths,
        ) from None

    # OME-640: a per-path rule cannot say "these two accepted fields cannot travel
    # together on THIS model under THIS auth mode", so the provider gets one seam
    # to say it — on the projected body, still ahead of provider preparation,
    # cache planning, credential access and dispatch. The default accepts
    # everything, so a provider that states no cross-field constraint is unaffected.
    try:
        plugin.validate_chat_parameter_combination(body, model=model, auth_mode=auth_mode)
    except IncompatibleParametersError as exc:
        if default_paths & set(exc.paths):
            # A stored default can be one half of the conflict, and the caller may
            # not know it exists — so the operator gets their own channel, exactly
            # as for a rejected default. Paths and the provider's own reason only.
            logger.warning(
                "profile defaults in a refused parameter combination "
                "provider=%s account=%s profile=%s paths=%s",
                provider,
                account_id,
                profile_name,
                ",".join(sorted(default_paths & set(exc.paths))),
            )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "incompatible_parameters",
                "provider": provider,
                "conflict": list(exc.paths),
                "message": exc.reason,
            },
        ) from None

    body = plugin.prepare_chat_body(body)

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
        raise await _safe_dispatch_failure_response(
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
        ) from None
    except (
        RateLimitError,
        UnsupportedParamsError,
        BadRequestError,
        AuthenticationError,
        PermissionDeniedError,
        NotFoundError,
        UnprocessableEntityError,
        InternalServerError,
        APIError,
        APIConnectionError,
        ServiceUnavailableError,
        Timeout,
    ) as exc:
        raise await _safe_dispatch_failure_response(
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
        ) from None
    except Exception as exc:
        # WHY (OME-428 third-review blocker B): the two branches above enumerate
        # the curated HTTPException and the KNOWN litellm exception families. Any
        # OTHER escape (a RuntimeError, a ValueError, a new litellm type, a
        # malformed-conversion error) must still render a sanitized status — never
        # an uncontrolled ASGI 500 whose traceback leaks the raw provider
        # message/prompt.
        # INVARIANT: an unclassified exception always yields a fixed sanitized
        # 502 `provider_error`; arbitrary attributes/chains are not trusted and
        # cannot trigger credential invalidation.
        logger.error(
            "unhandled dispatch error type=%s provider=%s account=%s profile=%s",
            type(exc).__name__,
            provider,
            account_id,
            profile_name,
        )
        raise await _safe_dispatch_failure_response(
            request,
            _unknown_provider_exception(),
            plugin=plugin,
            provider=provider,
            account_id=account_id,
            profile_name=profile_name,
            profile=profile,
            connection=connection,
            credential_name=credential_name,
            auth_type=auth_type,
        ) from None
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
