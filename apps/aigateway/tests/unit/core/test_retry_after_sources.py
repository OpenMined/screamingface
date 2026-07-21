"""Retry-After header sources + precedence (OME-428 third-review blocker C).

# STORY: as the gateway I must honor an upstream provider's validated
# ``Retry-After`` on a real transport 429/503 so clients back off correctly.
# INVARIANT: litellm 1.87.0 exposes the wire header on
# ``exc.litellm_response_headers`` (``exc.response.headers`` is empty for its
# OpenRouter transport errors), so the parser must read that source. Precedence
# is fixed and total: ``response.headers`` → ``litellm_response_headers`` →
# ``exc.headers`` (the FastAPI ``HTTPException`` path). Only an ASCII integer
# delta-seconds is a valid hint; an embedded HTTP-200 error (no headers) never
# fabricates one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aigateway.core.retry import RetryPolicy, parse_retry_after_seconds, with_overload_retry


def _exc(**attrs: object) -> BaseException:
    exc = RuntimeError("boom")
    for key, value in attrs.items():
        setattr(exc, key, value)
    return exc


def test_litellm_response_headers_is_honored() -> None:
    # The real litellm-1.87.0 OpenRouter transport shape: wire header only on
    # litellm_response_headers; no usable response.headers.
    exc = _exc(litellm_response_headers={"retry-after": "7"})
    assert parse_retry_after_seconds(exc) == 7.0


def test_response_headers_take_precedence_over_litellm_response_headers() -> None:
    exc = _exc(
        response=SimpleNamespace(headers={"retry-after": "3"}),
        litellm_response_headers={"retry-after": "5"},
    )
    assert parse_retry_after_seconds(exc) == 3.0


def test_litellm_response_headers_take_precedence_over_exc_headers() -> None:
    exc = _exc(
        litellm_response_headers={"retry-after": "5"},
        headers={"Retry-After": "9"},
    )
    assert parse_retry_after_seconds(exc) == 5.0


def test_exc_headers_still_read_for_httpexception_path() -> None:
    # Regression: the FastAPI HTTPException path (case-insensitive key) still works.
    exc = _exc(headers={"Retry-After": "4"})
    assert parse_retry_after_seconds(exc) == 4.0


def test_no_headers_anywhere_returns_none() -> None:
    # An embedded HTTP-200 error carries no headers -> never fabricate a hint.
    assert parse_retry_after_seconds(_exc()) is None


def test_non_finite_in_litellm_response_headers_is_rejected() -> None:
    exc = _exc(litellm_response_headers={"retry-after": "Infinity"})
    assert parse_retry_after_seconds(exc) is None


def test_malformed_litellm_response_header_falls_back_to_none() -> None:
    exc = _exc(litellm_response_headers={"retry-after": "soon"})
    assert parse_retry_after_seconds(exc) is None


@pytest.mark.parametrize(("raw", "expected"), [("0", 0.0), ("7", 7.0)])
def test_parsed_value_is_the_validated_delta_seconds(raw: str, expected: float) -> None:
    exc = _exc(litellm_response_headers={"retry-after": raw})
    assert parse_retry_after_seconds(exc) == expected


@pytest.mark.parametrize("raw", ["-3", "+7", "1.5", "1e3", "４２９"])
def test_non_integer_delta_seconds_are_rejected(raw: str) -> None:
    exc = _exc(litellm_response_headers={"retry-after": raw})
    assert parse_retry_after_seconds(exc) is None


def test_invalid_earlier_source_does_not_hide_valid_later_source() -> None:
    exc = _exc(
        response=SimpleNamespace(headers={"retry-after": "-1"}),
        litellm_response_headers={"retry-after": "7"},
    )
    assert parse_retry_after_seconds(exc) == 7.0


@pytest.mark.parametrize("digits", [309, 5_000])
@pytest.mark.asyncio
async def test_large_integer_hint_exceeding_budget_raises_original_without_overflow(
    digits: int,
) -> None:
    exc = _exc(
        status_code=429,
        response=SimpleNamespace(headers={"retry-after": "9" * digits}),
    )
    calls = {"n": 0}

    async def dispatch() -> None:
        calls["n"] += 1
        raise exc

    with pytest.raises(RuntimeError) as excinfo:
        await with_overload_retry(
            dispatch,
            policy=RetryPolicy(max_retries=3, max_total_wait_seconds=30.0),
        )

    assert excinfo.value is exc
    assert calls["n"] == 1
