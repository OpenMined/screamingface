"""The route-facing seam for OME-303 per-provider-call usage accounting.

FEATURE: an opt-in evidence contract on ``POST /v1/chat/completions``.

STORY: as a benchmark operator I send ``X-AIGW-Accounting: v1`` and receive every observed
local provider attempt, canonical usage and provider-authored cost evidence. Cache replay
is labelled historical evidence rather than current spend or counterfactual savings.

INVARIANT (the whole reason this is a header): the opt-in signal is TRANSPORT metadata.
It is not a body field, so it cannot reach provider parameter validation and cannot enter
the OME-305 effective request/cache key. A negotiated and a non-negotiated request with
otherwise identical bodies MUST produce the same ``key_hash`` — otherwise turning
accounting on would silently partition the shared cache in half.

INVARIANT: a non-negotiated request is byte-for-byte unaffected. No collector, no handler
injection, no metadata, no shape change.

INVARIANT (§6): metadata is attached to a COPY, and only after the request cache has
stored the provider's own JSON. See ``attach_success_metadata``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..core.plugin_base import ProviderPluginBase
from ..core.usage_accounting import CacheReference, ProviderUsageAccountingEvidence
from ..core.usage_accounting._classify import (
    classify_conversion_failure,
    classify_transport_failure,
)
from ..core.usage_accounting._collector import (
    RequestAccountingCollector,
    bound_collector,
    new_gateway_call_id,
)
from ..core.usage_accounting._handler import AccountingAsyncHTTPHandler
from ..core.usage_accounting._render import (
    CacheStatusWord,
    attach_metadata,
    merged_error_detail,
    render_aigw_metadata,
)

logger = logging.getLogger(__name__)

NEGOTIATION_HEADER: Final = "X-AIGW-Accounting"
NEGOTIATION_VERSION: Final = "v1"
_STATE_ATTR: Final = "aigw_accounting"

__all__ = [
    "NEGOTIATION_HEADER",
    "NEGOTIATION_VERSION",
    "AccountingSession",
    "accounting_error_response",
    "attach_hit_metadata",
    "attach_success_metadata",
    "begin_accounting",
    "bound_dispatch",
    "finalize_provider_evidence",
    "note_dispatch_failure",
    "streaming_rejection",
]


@dataclass
class AccountingSession:
    """Everything the route needs to account for one negotiated caller request."""

    provider: str
    supported: bool
    collector: RequestAccountingCollector | None
    gateway_call_id: str
    inject_shared_handler: bool
    dispatch_count: int = 0
    cache_status: CacheStatusWord = "bypass"

    def note_dispatch(self) -> None:
        """One gateway/plugin dispatch attempt is starting (an overload retry is a new one)."""
        self.dispatch_count += 1
        if self.collector is not None:
            self.collector.begin_dispatch()


def begin_accounting(
    request: Request, *, plugin: ProviderPluginBase, provider: str, model: str
) -> AccountingSession | None:
    """Open a session for a negotiated request, or ``None`` when not negotiated.

    Called BEFORE the cache stage so a hit still renders metadata — but note that the
    collector exists only to hold records, and a hit creates none. Nothing here reads a
    credential, dispatches, or touches the request body.
    """
    requested_version = request.headers.get(NEGOTIATION_HEADER)
    if requested_version is None:
        return None
    if requested_version.strip().lower() != NEGOTIATION_VERSION:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_accounting_version",
                "message": f"supported accounting version: {NEGOTIATION_VERSION}",
            },
        )
    strategy = plugin.usage_accounting_strategy()
    collector = (
        RequestAccountingCollector(
            provider=provider,
            requested_model=model,
            transport=strategy.capability,
        )
        if strategy.is_supported
        else None
    )
    session = AccountingSession(
        provider=provider,
        supported=strategy.is_supported,
        collector=collector,
        gateway_call_id=(
            collector.gateway_call_id if collector is not None else new_gateway_call_id()
        ),
        inject_shared_handler=strategy.uses_shared_litellm_http,
    )
    # Published so the app-wide HTTPException handler can render `_aigw` beside `detail`
    # for EVERY safe terminal error, including ones raised long before dispatch.
    setattr(request.state, _STATE_ATTR, session)
    # §9.24: the id is logged here so an operator can correlate a response with gateway
    # logs. Without this line `gateway_call_id` would be response-local only.
    logger.info(
        "usage accounting negotiated provider=%s gateway_call_id=%s supported=%s",
        provider,
        session.gateway_call_id,
        session.supported,
    )
    return session


def session_for(request: Request) -> AccountingSession | None:
    return getattr(request.state, _STATE_ATTR, None)


def streaming_rejection() -> HTTPException:
    """Refuse a negotiated ``stream:true`` BEFORE any provider dispatch (§3.3).

    WHY refuse rather than degrade: accounting a stream honestly would mean reading the
    SSE body to find its terminal usage frame, and the response hook that does the
    reading would consume the very stream the caller is waiting on. Silently returning
    empty accounting instead would be worse — it would report zero provider cost for a
    call that really happened. Non-negotiated streaming is untouched.
    """
    return HTTPException(
        status_code=400,
        detail={
            "code": "accounting_not_supported_for_streaming",
            "message": (
                "usage accounting is not available for streaming requests; "
                "retry without stream:true or without the accounting header"
            ),
        },
    )


def dispatch_body_with_accounting(
    body: dict[str, Any], session: AccountingSession | None, handler: Any
) -> dict[str, Any]:
    """Inject the gateway's observed LiteLLM client for an accounted dispatch.

    INVARIANT: injected ONLY for a negotiated request whose provider declared
    ``litellm_async_http_v1``. Every other request keeps LiteLLM's own client selection,
    so opting in cannot change the transport for traffic that did not ask for it.

    INVARIANT: a fresh dict. The caller's ``body`` is the one the cache keyed; a dispatch
    control written into it would leak into that identity.
    """
    if (
        session is None
        or session.collector is None
        or not session.inject_shared_handler
        or handler is None
    ):
        return body
    out = dict(body)
    out["client"] = handler
    return out


def accounting_handler(request: Request) -> AccountingAsyncHTTPHandler | None:
    """The app-lifetime observed handler, if the app built one."""
    return getattr(request.app.state, "usage_accounting_handler", None)


def bound_dispatch(session: AccountingSession | None):
    """Bind the collector for the duration of a dispatch, or do nothing.

    The handler is app-lifetime and shared; this binding is what makes its hooks write
    to THIS caller's records and no one else's.
    """
    if session is None or session.collector is None:
        return _NullBinding()
    return bound_collector(session.collector)


class _NullBinding:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> Literal[False]:
        return False


def safe_request_view(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """The only part of the dispatch body a provider mapper may see.

    INVARIANT: mappers never receive credentials or prompt content. By the time the
    route finalizes evidence, ``body`` carries the injected provider credential and the
    caller's full ``messages``; handing that to a plugin hook would give evidence
    normalization access to both, for no reason — it needs neither to read a ``usage``
    block. Least privilege, enforced structurally rather than by convention.
    """
    return {
        key: value
        for key, value in body.items()
        if key not in _MAPPER_HIDDEN_FIELDS and not isinstance(value, (list, dict))
    }


# Credentials, prompt content and transport controls. The value-shape filter above also
# drops anything structured, so a nested prompt cannot arrive through a new field name.
_MAPPER_HIDDEN_FIELDS: Final = frozenset(
    {"api_key", "messages", "system", "headers", "extra_headers", "client", "metadata"}
)


def finalize_provider_evidence(
    session: AccountingSession | None,
    *,
    plugin: ProviderPluginBase,
    request_body: Mapping[str, Any],
    final_response: Mapping[str, Any] | None,
) -> None:
    """Run the provider's pure mapper over each observed send's own raw evidence.

    The LAST succeeded send additionally receives ``final_response`` as a fallback: it is
    the one whose body became the caller's answer, so it is the only record for which the
    converted shape describes the same call.

    INVARIANT: totally non-raising. A mapper bug must never fail a provider response that
    has already been billed; it degrades the record to incomplete instead.
    """
    if session is None or session.collector is None:
        return
    collector = session.collector
    observed = collector.open_records()
    last_success = next(
        (call_id for call_id, _raw, ok in reversed(observed) if ok),
        None,
    )
    for call_id, raw_evidence, succeeded in observed:
        try:
            evidence = plugin.normalize_chat_usage_accounting(
                request_body=request_body,
                raw_response=raw_evidence,
                final_response=final_response if call_id == last_success else None,
                failed=not succeeded,
            )
        except Exception:
            logger.warning(
                "provider usage-accounting mapper failed provider=%s gateway_call_id=%s",
                session.provider,
                session.gateway_call_id,
            )
            continue
        if not isinstance(evidence, ProviderUsageAccountingEvidence):
            logger.warning(
                "provider usage-accounting mapper returned invalid evidence "
                "provider=%s gateway_call_id=%s",
                session.provider,
                session.gateway_call_id,
            )
            continue
        collector.apply_evidence(call_id, evidence)


def note_conversion_failure(session: AccountingSession | None) -> None:
    """The provider answered but local conversion of its response failed (§9.20)."""
    if session is None or session.collector is None:
        return
    outcome, failure_code = classify_conversion_failure()
    session.collector.mark_conversion_failed(outcome, failure_code)


def note_dispatch_failure(
    session: AccountingSession | None,
    exc: BaseException,
    *,
    provider_error_after_response: bool = False,
) -> None:
    """Finalize a transport escape or an HTTP-200 body rejected by provider validation."""
    if session is None or session.collector is None:
        return
    outcome, failure_code = classify_transport_failure(exc)
    finalized = session.collector.finalize_last_open_failure(
        outcome=outcome, failure_code=failure_code
    )
    if provider_error_after_response and not finalized:
        session.collector.mark_last_succeeded_provider_error()


def _metadata(
    session: AccountingSession,
    *,
    cache_status: CacheStatusWord,
    cache_reference: CacheReference | None = None,
) -> dict[str, Any]:
    return render_aigw_metadata(
        collector=session.collector,
        supported=session.supported,
        cache_status=cache_status,
        gateway_call_id=session.gateway_call_id,
        cache_reference=cache_reference,
        dispatched=session.dispatch_count > 0,
    )


def attach_success_metadata(
    result: dict[str, Any], session: AccountingSession | None, *, cache_status: CacheStatusWord
) -> dict[str, Any]:
    """Return the response body a negotiated caller receives on a miss/bypass.

    INVARIANT (§6): this runs AFTER ``store_global_response``. Two independent reasons —
    the cache row must stay provider-compatible for every future replay, and
    ``store_global_response`` measures ``response_size_bytes`` against what it is given,
    so attaching first could push an otherwise cacheable response over the size cap and
    silently cost the deployment a cache entry.
    """
    if session is None:
        return result
    try:
        return attach_metadata(result, _metadata(session, cache_status=cache_status))
    except Exception:
        logger.warning(
            "usage accounting success rendering failed gateway_call_id=%s",
            session.gateway_call_id,
        )
        return result


def attach_hit_metadata(
    cached: dict[str, Any], session: AccountingSession | None, *, plugin: ProviderPluginBase
) -> dict[str, Any]:
    """Return the response body a negotiated caller receives on a cache HIT.

    INVARIANT: ``attempts`` is empty and ``observed_new_attempts`` is ``0``.
    A hit performs no provider dispatch, so a synthetic record here would report spend
    that did not happen. Limited historical evidence goes under ``cache.reference`` and
    is structurally marked as not incurred by the current request.

    INVARIANT: ``cached`` is the store's replayed row. It is copied, never mutated.
    """
    if session is None:
        return cached
    reference: CacheReference | None = None
    try:
        reference = plugin.cache_reference_from_cached_response(cached)
    except Exception:
        logger.warning(
            "cache-reference mapper failed provider=%s gateway_call_id=%s",
            session.provider,
            session.gateway_call_id,
        )
    if reference is not None and not isinstance(reference, CacheReference):
        logger.warning(
            "cache-reference mapper returned invalid evidence provider=%s gateway_call_id=%s",
            session.provider,
            session.gateway_call_id,
        )
        reference = None
    try:
        return attach_metadata(
            cached, _metadata(session, cache_status="hit", cache_reference=reference)
        )
    except Exception:
        logger.warning(
            "usage accounting cache-hit rendering failed gateway_call_id=%s",
            session.gateway_call_id,
        )
        return cached


def accounting_error_response(request: Request, exc: HTTPException) -> JSONResponse | None:
    """A safe terminal error body carrying ``_aigw`` beside ``detail``, or ``None``.

    ``None`` means "not negotiated" — the caller gets today's unchanged error shape.

    INVARIANT: only the already-sanitized ``exc.detail`` is echoed. Raw provider bodies,
    prompts, generated text, credentials, headers and tracebacks are excluded upstream
    of here and nothing in the metadata can reintroduce them.
    """
    session = session_for(request)
    if session is None:
        return None
    try:
        return JSONResponse(
            status_code=exc.status_code,
            content=merged_error_detail(
                exc.detail, _metadata(session, cache_status=session.cache_status)
            ),
            headers=dict(exc.headers or {}),
        )
    except Exception:
        # INVARIANT: accounting may never make an error worse than it already was. This
        # renderer is reached from an APP-WIDE exception handler, so a failure here
        # would break error responses on every route in the gateway, not just this one.
        # Returning None falls back to Starlette's untouched handler.
        logger.warning(
            "accounting error rendering failed gateway_call_id=%s", session.gateway_call_id
        )
        return None
