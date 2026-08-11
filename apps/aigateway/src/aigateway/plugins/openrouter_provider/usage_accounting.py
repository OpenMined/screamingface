"""Pure OpenRouter mapper for the OME-303 accounting v1 contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...core.usage_accounting import (
    CacheReference,
    DirectCost,
    InputTokenUsage,
    OutputTokenUsage,
    PricingContext,
    ProviderExtension,
    ProviderExtensionFact,
    ProviderUsageAccountingEvidence,
    TokenUsage,
    UsageSource,
    canonical_amount,
)

__all__ = ["cache_reference_from_cached", "normalize_openrouter_usage_accounting"]

DIRECT_COST_UNIT = "openrouter_credits"
DIRECT_COST_SOURCE = "openrouter.usage.cost"
CACHED_DIRECT_COST_SOURCE = "cached_response.usage.cost"
EXTENSION_NAMESPACE = "openrouter.response_usage.v1"
_MAX_TOKEN_COUNT = 2**53 - 1

# OpenRouter exposes these provider-cost components without a documented currency/unit.
# They remain non-aggregable audit evidence until the provider contract supplies one.
_COST_DETAIL_FIELDS = {
    "upstream_inference_cost": "openrouter.usage.cost_details.upstream_inference_cost",
    "upstream_inference_prompt_cost": (
        "openrouter.usage.cost_details.upstream_inference_prompt_cost"
    ),
    "upstream_inference_completions_cost": (
        "openrouter.usage.cost_details.upstream_inference_completions_cost"
    ),
}


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


def _uncached_input(
    total: int | None, cache_read: int | None, cache_write: int | None
) -> int | None:
    if None in (total, cache_read, cache_write):
        return None
    uncached = total - cache_read - cache_write  # type: ignore[operator]
    return uncached if uncached >= 0 else None


def _tokens(usage: Mapping[str, Any], source: UsageSource) -> TokenUsage:
    prompt_details = _mapping(usage.get("prompt_tokens_details")) or {}
    completion_details = _mapping(usage.get("completion_tokens_details")) or {}
    input_total = _final_detail_or_none(usage.get("prompt_tokens"), source)
    output_total = _final_detail_or_none(usage.get("completion_tokens"), source)
    cache_read = _final_detail_or_none(prompt_details.get("cached_tokens"), source)
    cache_write = _cache_write_tokens(prompt_details, source)
    any_known = any(
        value is not None for value in (input_total, output_total, cache_read, cache_write)
    )
    status = "complete" if input_total is not None and output_total is not None else "partial"
    if not any_known:
        status = "unavailable"
    return TokenUsage(
        status=status,
        source=source,
        input=InputTokenUsage(
            total=input_total,
            uncached=_uncached_input(input_total, cache_read, cache_write),
            cache_read=cache_read,
            cache_write=cache_write,
        ),
        output=OutputTokenUsage(
            total=output_total,
            reasoning=_final_detail_or_none(completion_details.get("reasoning_tokens"), source),
        ),
    )


def _direct_cost(usage: Mapping[str, Any], *, source: str) -> DirectCost:
    if usage.get("cost") is None:
        return DirectCost.unavailable()
    amount = canonical_amount(usage.get("cost"))
    if amount is None:
        return DirectCost.invalid()
    return DirectCost.reported(amount=amount, unit=DIRECT_COST_UNIT, source=source)


def _provider_extensions(usage: Mapping[str, Any]) -> tuple[ProviderExtension, ...]:
    facts: list[ProviderExtensionFact] = []
    cost_details = _mapping(usage.get("cost_details")) or {}
    for name, source in _COST_DETAIL_FIELDS.items():
        if name not in cost_details:
            continue
        amount = canonical_amount(cost_details[name])
        if amount is not None:
            facts.append(
                ProviderExtensionFact(
                    name=name,
                    kind="decimal",
                    value=amount,
                    unit=None,
                    source=source,
                )
            )
    server_tools = _mapping(usage.get("server_tool_use")) or {}
    web_searches = _int_or_none(server_tools.get("web_search_requests"))
    if web_searches is not None:
        facts.append(
            ProviderExtensionFact(
                name="web_search_requests",
                kind="integer",
                value=web_searches,
                unit="requests",
                source="openrouter.usage.server_tool_use.web_search_requests",
            )
        )
    if not facts:
        return ()
    return (ProviderExtension(namespace=EXTENSION_NAMESPACE, facts=tuple(facts[:8])),)


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


def normalize_openrouter_usage_accounting(
    *,
    request_body: Mapping[str, Any],
    raw_response: Mapping[str, Any] | None,
    final_response: Mapping[str, Any] | None,
    failed: bool = False,
) -> ProviderUsageAccountingEvidence:
    """Normalize one observed OpenRouter attempt without reading request secrets/content."""
    del request_body, failed
    usage, source = _usage_and_source(raw_response, final_response)
    if usage is None:
        return ProviderUsageAccountingEvidence(
            supported=True,
            response_model=_response_model(raw_response, final_response),
            provider_response_id=_response_id(raw_response, final_response),
        )
    return ProviderUsageAccountingEvidence(
        supported=True,
        usage=_tokens(usage, source),
        pricing_context=PricingContext(),
        direct_cost=_direct_cost(usage, source=DIRECT_COST_SOURCE),
        response_model=_response_model(raw_response, final_response),
        provider_response_id=_response_id(raw_response, final_response),
        provider_extensions=_provider_extensions(usage),
    )


def cache_reference_from_cached(cached: Mapping[str, Any]) -> CacheReference | None:
    """Historical final-response evidence; never current spend or avoided-cost proof."""
    usage = _mapping(cached.get("usage"))
    if usage is None:
        return None
    tokens = _tokens(usage, "cached_converted_response")
    direct = _direct_cost(usage, source=CACHED_DIRECT_COST_SOURCE)
    return CacheReference(usage=tokens, direct_cost=direct)


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
