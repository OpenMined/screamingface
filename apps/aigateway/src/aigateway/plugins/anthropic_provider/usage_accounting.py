"""Pure Anthropic mapper for the OME-303 accounting v1 contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...core.usage_accounting import (
    CacheReference,
    CacheWriteTTL,
    DirectCost,
    InputTokenUsage,
    OutputTokenUsage,
    PricingContext,
    ProviderExtension,
    ProviderExtensionFact,
    ProviderUsageAccountingEvidence,
    TokenUsage,
    UsageSource,
)

__all__ = ["cache_reference_from_cached", "normalize_anthropic_usage_accounting"]

EXTENSION_NAMESPACE = "anthropic.usage.v1"
_MAX_TOKEN_COUNT = 2**53 - 1
_SERVICE_TIERS = frozenset({"standard", "priority", "batch"})


def _int_or_none(value: object) -> int | None:
    if type(value) is int and 0 <= value <= _MAX_TOKEN_COUNT:
        return value
    return None


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _final_detail_or_none(value: object, source: UsageSource) -> int | None:
    token_count = _int_or_none(value)
    if source != "provider_raw_response" and token_count == 0:
        return None
    return token_count


def _cache_write_tokens(prompt_details: Mapping[str, Any], source: UsageSource) -> int | None:
    for key in ("cache_write_tokens", "cache_creation_tokens"):
        if key in prompt_details:
            return _final_detail_or_none(prompt_details[key], source)
    return None


def _inclusive_input(
    uncached: int | None, cache_read: int | None, cache_write: int | None
) -> int | None:
    if uncached is None or cache_read is None or cache_write is None:
        return None
    total = uncached + cache_read + cache_write
    return total if total <= _MAX_TOKEN_COUNT else None


def _cache_ttl_rows(usage: Mapping[str, Any], source: UsageSource) -> tuple[CacheWriteTTL, ...]:
    creation = _mapping(usage.get("cache_creation")) or {}
    rows: list[CacheWriteTTL] = []
    for key, ttl in (
        ("ephemeral_5m_input_tokens", 300),
        ("ephemeral_1h_input_tokens", 3600),
    ):
        tokens = _final_detail_or_none(creation.get(key), source)
        if tokens is not None:
            rows.append(CacheWriteTTL(ttl_seconds=ttl, tokens=tokens))
    return tuple(rows)


def _tokens(usage: Mapping[str, Any], source: UsageSource) -> TokenUsage:
    converted_shape = source == "provider_converted_response" or (
        source == "cached_converted_response"
        and any(key in usage for key in ("prompt_tokens", "completion_tokens"))
    )
    if converted_shape:
        prompt_details = _mapping(usage.get("prompt_tokens_details")) or {}
        completion_details = _mapping(usage.get("completion_tokens_details")) or {}
        input_total = _final_detail_or_none(usage.get("prompt_tokens"), source)
        if input_total is None:
            input_total = _final_detail_or_none(usage.get("input_tokens"), source)
        output_total = _final_detail_or_none(usage.get("completion_tokens"), source)
        if output_total is None:
            output_total = _final_detail_or_none(usage.get("output_tokens"), source)
        any_known = input_total is not None or output_total is not None
        return TokenUsage(
            status=(
                "complete"
                if input_total is not None and output_total is not None
                else ("partial" if any_known else "unavailable")
            ),
            source=source,
            input=InputTokenUsage(
                total=input_total,
                cache_read=_final_detail_or_none(prompt_details.get("cached_tokens"), source),
                cache_write=_cache_write_tokens(prompt_details, source),
            ),
            output=OutputTokenUsage(
                total=output_total,
                reasoning=_final_detail_or_none(completion_details.get("reasoning_tokens"), source),
            ),
        )

    uncached = _final_detail_or_none(usage.get("input_tokens"), source)
    output_total = _final_detail_or_none(usage.get("output_tokens"), source)
    cache_read = _final_detail_or_none(usage.get("cache_read_input_tokens"), source)
    cache_write = _final_detail_or_none(usage.get("cache_creation_input_tokens"), source)
    input_total = _inclusive_input(uncached, cache_read, cache_write)
    ttl_rows = _cache_ttl_rows(usage, source)
    output_details = _mapping(usage.get("output_tokens_details")) or {}
    complete = input_total is not None and output_total is not None
    any_known = any(
        value is not None for value in (uncached, output_total, cache_read, cache_write)
    )
    ttl_mismatch = bool(ttl_rows) and (
        cache_write is None or sum(row.tokens for row in ttl_rows) != cache_write
    )
    return TokenUsage(
        status=(
            "complete"
            if complete and not ttl_mismatch
            else ("partial" if any_known else "unavailable")
        ),
        source=source,
        input=InputTokenUsage(
            total=input_total,
            uncached=uncached,
            cache_read=cache_read,
            cache_write=cache_write,
            cache_write_by_ttl=ttl_rows,
        ),
        output=OutputTokenUsage(
            total=output_total,
            reasoning=_final_detail_or_none(output_details.get("reasoning_tokens"), source),
        ),
    )


def _pricing_context(usage: Mapping[str, Any]) -> PricingContext:
    tier = usage.get("service_tier")
    return PricingContext(service_tier=tier if tier in _SERVICE_TIERS else None)


def _provider_extensions(usage: Mapping[str, Any]) -> tuple[ProviderExtension, ...]:
    server_tools = _mapping(usage.get("server_tool_use")) or {}
    facts: list[ProviderExtensionFact] = []
    for name in ("web_search_requests", "web_fetch_requests"):
        count = _int_or_none(server_tools.get(name))
        if count is not None:
            facts.append(
                ProviderExtensionFact(
                    name=name,
                    kind="integer",
                    value=count,
                    unit="requests",
                    source=f"anthropic.usage.server_tool_use.{name}",
                )
            )
    if not facts:
        return ()
    return (ProviderExtension(namespace=EXTENSION_NAMESPACE, facts=tuple(facts)),)


def _usage_and_source(
    raw_response: Mapping[str, Any] | None, final_response: Mapping[str, Any] | None
) -> tuple[Mapping[str, Any] | None, UsageSource]:
    raw_usage = _mapping((raw_response or {}).get("usage"))
    if raw_usage is not None:
        return raw_usage, "provider_raw_response"
    final_usage = _mapping((final_response or {}).get("usage"))
    if final_usage is not None:
        return final_usage, "provider_converted_response"
    return None, "provider_raw_response"


def normalize_anthropic_usage_accounting(
    *,
    request_body: Mapping[str, Any],
    raw_response: Mapping[str, Any] | None,
    final_response: Mapping[str, Any] | None,
    failed: bool = False,
) -> ProviderUsageAccountingEvidence:
    """Normalize one Anthropic attempt; Anthropic has no direct-cost response field."""
    del request_body, failed
    usage, source = _usage_and_source(raw_response, final_response)
    if usage is None:
        return ProviderUsageAccountingEvidence(
            supported=True,
            direct_cost=DirectCost.absent(),
            response_model=_response_model(raw_response, final_response),
            provider_response_id=_response_id(raw_response, final_response),
        )
    return ProviderUsageAccountingEvidence(
        supported=True,
        usage=_tokens(usage, source),
        pricing_context=_pricing_context(usage),
        direct_cost=DirectCost.absent(),
        response_model=_response_model(raw_response, final_response),
        provider_response_id=_response_id(raw_response, final_response),
        provider_extensions=_provider_extensions(usage),
    )


def cache_reference_from_cached(cached: Mapping[str, Any]) -> CacheReference | None:
    """Historical evidence for the cached final Anthropic response."""
    usage = _mapping(cached.get("usage"))
    if usage is None:
        return None
    return CacheReference(
        usage=_tokens(usage, "cached_converted_response"),
        direct_cost=DirectCost.absent(),
    )


def _response_model(
    raw_response: Mapping[str, Any] | None, final_response: Mapping[str, Any] | None
) -> str | None:
    for candidate in (raw_response, final_response):
        model = (candidate or {}).get("model")
        if isinstance(model, str) and model:
            return model
    return None


def _response_id(
    raw_response: Mapping[str, Any] | None, final_response: Mapping[str, Any] | None
) -> str | None:
    for candidate in (raw_response, final_response):
        identifier = (candidate or {}).get("id")
        if isinstance(identifier, str) and identifier:
            return identifier
    return None
