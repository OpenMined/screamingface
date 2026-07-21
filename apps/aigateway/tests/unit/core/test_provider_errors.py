"""Non-retryable provenance for provider-manufactured errors (OME-428 CODE-2).

An error a plugin manufactures from an already-returned upstream response
(e.g. an embedded 429 inside a nominal HTTP-200 body) must never re-enter the
overload-retry loop: the upstream call already happened and may already be
billed. Actual transport failures (real 429/503 exceptions) keep retrying.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from aigateway.core.provider_errors import NonRetryableProviderError
from aigateway.core.retry import RetryPolicy, is_retryable_status, with_overload_retry


def _policy() -> RetryPolicy:
    return RetryPolicy(
        max_retries=3,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
        max_total_wait_seconds=30.0,
        jitter_seconds=0.0,
    )


def test_marked_error_is_an_http_exception() -> None:
    # INVARIANT: routes/chat.py catches HTTPException on the dispatch-failure
    # path (credential marking); the marker type must stay isinstance-compatible.
    exc = NonRetryableProviderError(status_code=429, detail={"code": "rate_limited"})
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 429
    assert exc.detail == {"code": "rate_limited"}


@pytest.mark.parametrize("status", [429, 503, 529])
def test_marked_overload_statuses_are_not_retryable(status: int) -> None:
    assert is_retryable_status(NonRetryableProviderError(status_code=status, detail={})) is False


@pytest.mark.parametrize("status", [429, 503, 529])
def test_plain_http_exception_overload_statuses_stay_retryable(status: int) -> None:
    # Control: the provenance marker, not the exception type, disables retry —
    # transport-shaped HTTPExceptions from other plugins keep the retry loop.
    assert is_retryable_status(HTTPException(status_code=status, detail={})) is True


@pytest.mark.asyncio
async def test_marked_error_dispatches_exactly_once() -> None:
    calls = {"n": 0}

    async def dispatch() -> str:
        calls["n"] += 1
        raise NonRetryableProviderError(status_code=429, detail={"code": "rate_limited"})

    with pytest.raises(NonRetryableProviderError):
        await with_overload_retry(dispatch, policy=_policy())
    assert calls["n"] == 1
