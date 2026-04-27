"""Rate-limit header parsing for OpenAI's ``api.openai.com`` responses.

OpenAI ships ``x-ratelimit-*`` headers; we normalize the prefix off
and coerce numeric values. Callers also expect ``tokens_remaining`` /
``requests_remaining`` aliases for the legacy ``remaining_*`` names.
"""

from __future__ import annotations

import httpx


def extract_openai_rate_limits(headers: httpx.Headers) -> dict[str, str | int | float]:
    prefix = "x-ratelimit-"
    result: dict[str, str | int | float] = {}
    for key, value in headers.items():
        if not key.lower().startswith(prefix):
            continue
        short_key = key[len(prefix) :].replace("-", "_")
        try:
            result[short_key] = int(value)
        except ValueError:
            try:
                result[short_key] = float(value)
            except ValueError:
                result[short_key] = value
    if "remaining_tokens" in result:
        result["tokens_remaining"] = result["remaining_tokens"]
    if "remaining_requests" in result:
        result["requests_remaining"] = result["remaining_requests"]
    return result
