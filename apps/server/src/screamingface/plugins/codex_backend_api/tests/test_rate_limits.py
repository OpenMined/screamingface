"""Unit tests for OpenAI rate-limit header parsing."""

from __future__ import annotations

import httpx

from screamingface.plugins.codex_backend_api.rate_limits import extract_openai_rate_limits


def _headers(items: dict[str, str]) -> httpx.Headers:
    return httpx.Headers(items)


def test_extracts_known_keys_and_aliases_remaining() -> None:
    h = _headers(
        {
            "x-ratelimit-remaining-tokens": "1234",
            "x-ratelimit-remaining-requests": "5",
            "x-ratelimit-reset-tokens": "60s",
        }
    )
    out = extract_openai_rate_limits(h)
    assert out["remaining_tokens"] == 1234
    assert out["remaining_requests"] == 5
    assert out["tokens_remaining"] == 1234
    assert out["requests_remaining"] == 5
    assert out["reset_tokens"] == "60s"  # non-numeric stays str


def test_ignores_unrelated_headers() -> None:
    h = _headers({"content-type": "application/json", "x-other": "v"})
    assert extract_openai_rate_limits(h) == {}


def test_coerces_floats() -> None:
    h = _headers({"x-ratelimit-reset-seconds": "1.5"})
    out = extract_openai_rate_limits(h)
    assert out["reset_seconds"] == 1.5
