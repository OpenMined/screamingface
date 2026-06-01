from __future__ import annotations

from typing import Any

import httpx
import pytest

from aigateway.core.retry import (
    RetryPolicy,
    is_retryable_status,
    parse_retry_after_seconds,
    with_overload_retry,
)


class _StatusError(Exception):
    """Minimal stand-in for a LiteLLM exception carrying status_code + response."""

    headers: dict[str, str] | None = None

    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        if retry_after is not None:
            request = httpx.Request("POST", "https://example.test/v1/chat/completions")
            self.response = httpx.Response(
                status_code, headers={"retry-after": retry_after}, request=request
            )


def _policy(**kw: Any) -> RetryPolicy:
    base: dict[str, Any] = dict(
        max_retries=3,
        backoff_base_seconds=0.5,
        backoff_max_seconds=8.0,
        max_total_wait_seconds=30.0,
        jitter_seconds=0.0,  # deterministic in tests
    )
    base.update(kw)
    return RetryPolicy(**base)


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.mark.parametrize("status", [429, 503, 529])
def test_is_retryable_true_for_overload_statuses(status: int) -> None:
    assert is_retryable_status(_StatusError(status)) is True


@pytest.mark.parametrize("status", [400, 401, 500, 502])
def test_is_retryable_false_for_other_statuses(status: int) -> None:
    assert is_retryable_status(_StatusError(status)) is False


def test_is_retryable_false_without_status_code() -> None:
    assert is_retryable_status(ValueError("boom")) is False


def test_parse_retry_after_reads_integer_seconds() -> None:
    assert parse_retry_after_seconds(_StatusError(429, retry_after="7")) == 7.0


def test_parse_retry_after_malformed_returns_none() -> None:
    assert parse_retry_after_seconds(_StatusError(429, retry_after="not-a-number")) is None


def test_parse_retry_after_absent_returns_none() -> None:
    assert parse_retry_after_seconds(_StatusError(429)) is None


class _HeaderError(Exception):
    """Mimics FastAPI HTTPException: carries ``.headers`` but no ``.response``."""

    def __init__(self, status_code: int, headers: dict[str, str]) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self.headers = headers


def test_parse_retry_after_reads_exc_headers() -> None:
    assert parse_retry_after_seconds(_HeaderError(429, {"retry-after": "3"})) == 3.0


def test_parse_retry_after_headers_absent_returns_none() -> None:
    assert parse_retry_after_seconds(_HeaderError(429, {})) is None


def test_parse_retry_after_prefers_response_over_headers() -> None:
    exc = _StatusError(429, retry_after="2")
    exc.headers = {"retry-after": "9"}  # response header wins over exc.headers
    assert parse_retry_after_seconds(exc) == 2.0


def test_parse_retry_after_handles_fastapi_httpexception_header_casing() -> None:
    """FastAPI's ``HTTPException(headers=...)`` keeps the dict as-is, so the
    key is ``"Retry-After"`` (capitalized) — not the httpx-style lowercase.
    Regression for the live runtime path: the gemini plugin raises
    ``HTTPException(headers={"Retry-After": str(seconds)})``; if this lookup is
    case-sensitive the hint is silently dropped and retry falls back to
    exponential backoff."""
    from fastapi import HTTPException

    exc = HTTPException(status_code=429, detail={}, headers={"Retry-After": "4"})
    assert parse_retry_after_seconds(exc) == 4.0


@pytest.mark.asyncio
async def test_overload_then_success_returns_value() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    async def dispatch() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _StatusError(429, retry_after="2")
        return "ok"

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await with_overload_retry(dispatch, policy=_policy(), sleep=sleep)
    assert result == "ok"
    assert calls["n"] == 2
    assert slept == [2.0]  # Retry-After honored


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 503, 529])
async def test_each_overload_status_is_retried(status: int) -> None:
    calls = {"n": 0}

    async def dispatch() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _StatusError(status, retry_after="1")
        return "ok"

    result = await with_overload_retry(dispatch, policy=_policy(), sleep=_noop_sleep)
    assert result == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_always_overload_raises_original_after_max_retries() -> None:
    calls = {"n": 0}
    err = _StatusError(429, retry_after="1")

    async def dispatch() -> str:
        calls["n"] += 1
        raise err

    with pytest.raises(_StatusError) as excinfo:
        await with_overload_retry(dispatch, policy=_policy(max_retries=3), sleep=_noop_sleep)
    assert excinfo.value is err
    assert calls["n"] == 4  # 1 initial + 3 retries


@pytest.mark.asyncio
async def test_retry_after_path_gets_jitter() -> None:
    """The honored Retry-After delay must also receive jitter so concurrent
    siblings handed the same reset window de-synchronise instead of waking in
    lockstep and re-colliding."""
    slept: list[float] = []
    calls = {"n": 0}

    async def dispatch() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _StatusError(429, retry_after="5")
        return "ok"

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await with_overload_retry(dispatch, policy=_policy(jitter_seconds=0.5), sleep=sleep)
    assert result == "ok"
    assert len(slept) == 1
    # 5s Retry-After + jitter in [0, 0.5]
    assert 5.0 <= slept[0] <= 5.5


@pytest.mark.asyncio
async def test_exponential_backoff_when_no_retry_after() -> None:
    slept: list[float] = []

    async def dispatch() -> str:
        raise _StatusError(429)  # no Retry-After header

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    with pytest.raises(_StatusError):
        await with_overload_retry(
            dispatch,
            policy=_policy(max_retries=4, backoff_base_seconds=1.0, backoff_max_seconds=4.0),
            sleep=sleep,
        )
    # base*2**attempt = 1, 2, 4, 8 -> capped at backoff_max_seconds (4)
    assert slept == [1.0, 2.0, 4.0, 4.0]


@pytest.mark.asyncio
async def test_budget_stops_retrying_early() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    async def dispatch() -> str:
        calls["n"] += 1
        raise _StatusError(429, retry_after="10")

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    with pytest.raises(_StatusError):
        await with_overload_retry(
            dispatch,
            policy=_policy(max_retries=5, max_total_wait_seconds=15.0),
            sleep=sleep,
        )
    # waits 10 (total 10), next 10 would exceed 15 -> stop. 1 initial + 1 retry = 2 calls.
    assert slept == [10.0]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_max_retries_zero_disables_retry() -> None:
    calls = {"n": 0}

    async def dispatch() -> str:
        calls["n"] += 1
        raise _StatusError(429, retry_after="1")

    with pytest.raises(_StatusError):
        await with_overload_retry(dispatch, policy=_policy(max_retries=0), sleep=_noop_sleep)
    assert calls["n"] == 1  # no retry


@pytest.mark.asyncio
async def test_non_retryable_propagates_immediately() -> None:
    calls = {"n": 0}

    async def dispatch() -> str:
        calls["n"] += 1
        raise _StatusError(400)

    with pytest.raises(_StatusError):
        await with_overload_retry(dispatch, policy=_policy(), sleep=_noop_sleep)
    assert calls["n"] == 1
