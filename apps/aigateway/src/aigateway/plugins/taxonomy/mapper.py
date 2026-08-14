"""Provider-neutral policy for bounded accounting mapper inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .types import MAX_TOKEN_COUNT, UsageSource


def bounded_count(value: object) -> int | None:
    """Return an exact JSON-safe nonnegative integer, never bool or coercion."""
    if type(value) is int and 0 <= value <= MAX_TOKEN_COUNT:
        return value
    return None


def mapping_or_none(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def final_detail_or_none(value: object, source: UsageSource) -> int | None:
    """Suppress synthetic zero details on converted/cache fallback evidence."""
    token_count = bounded_count(value)
    if source != "provider_raw_response" and token_count == 0:
        return None
    return token_count


def cache_write_tokens(prompt_details: Mapping[str, Any], source: UsageSource) -> int | None:
    """Read raw then converted cache-write aliases by presence, never truthiness."""
    for key in ("cache_write_tokens", "cache_creation_tokens"):
        if key in prompt_details:
            return final_detail_or_none(prompt_details[key], source)
    return None


def usage_and_source(
    raw_response: Mapping[str, Any] | None,
    final_response: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, UsageSource]:
    """Prefer raw provider evidence over the converted response fallback."""
    raw_usage = mapping_or_none((raw_response or {}).get("usage"))
    if raw_usage is not None:
        return raw_usage, "provider_raw_response"
    final_usage = mapping_or_none((final_response or {}).get("usage"))
    if final_usage is not None:
        return final_usage, "provider_converted_response"
    return None, "provider_raw_response"


def response_string(
    raw_response: Mapping[str, Any] | None,
    final_response: Mapping[str, Any] | None,
    *,
    field: str,
) -> str | None:
    """Return one non-empty response identifier, preferring raw evidence."""
    for candidate in (raw_response, final_response):
        value = (candidate or {}).get(field)
        if isinstance(value, str) and value:
            return value
    return None
