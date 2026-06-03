"""Reactive backpressure: retry rate-limited / overloaded upstream dispatches.

Status-code driven (duck-typed on ``status_code``), so it covers LiteLLM's
``RateLimitError`` / ``ServiceUnavailableError`` (which carry ``status_code``)
and any exception exposing one of the retryable codes. Stdlib-only.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# 429 rate-limited, 503 service-unavailable, 529 overloaded (Anthropic).
RETRYABLE_STATUS_CODES = frozenset({429, 503, 529})


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    max_total_wait_seconds: float = 30.0
    jitter_seconds: float = 0.25

    @classmethod
    def from_settings(cls, settings: Settings) -> RetryPolicy:
        return cls(
            max_retries=settings.retry_max_attempts,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
            backoff_max_seconds=settings.retry_backoff_max_seconds,
            max_total_wait_seconds=settings.retry_max_total_wait_seconds,
            jitter_seconds=settings.retry_jitter_seconds,
        )


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    # bool is an int subclass; reject it explicitly.
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    return code


def is_retryable_status(exc: BaseException) -> bool:
    return _status_code(exc) in RETRYABLE_STATUS_CODES


def _seconds_from_headers(headers: Any) -> float | None:
    if headers is None:
        return None
    raw = _case_insensitive_header(headers, "retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form unsupported -> backoff fallback
    return max(0.0, value)


def _case_insensitive_header(headers: Any, name: str) -> Any:
    """Read ``name`` from ``headers`` regardless of key casing.

    ``httpx.Headers`` is case-insensitive natively, but FastAPI's
    ``HTTPException`` stores ``headers`` as the literal dict passed in
    (so the key is whatever the caller wrote, typically ``"Retry-After"``).
    A plain ``dict.get("retry-after")`` would miss it and silently drop the
    hint.
    """
    target = name.lower()
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value is not None:
        return value
    items = getattr(headers, "items", None)
    if items is None:
        return None
    for key, val in items():
        if isinstance(key, str) and key.lower() == target:
            return val
    return None


def parse_retry_after_seconds(exc: BaseException) -> float | None:
    """Read an integer ``Retry-After`` (delta-seconds) off the exception.

    Checks ``exc.response.headers`` first (LiteLLM exceptions) then
    ``exc.headers`` (FastAPI ``HTTPException`` — how the aigateway provider
    plugins surface upstream 429s, e.g. the Gemini reset hint). Returns
    ``None`` for absent/malformed/HTTP-date values so the caller falls back to
    exponential backoff. Never raises.
    """
    response_headers = getattr(getattr(exc, "response", None), "headers", None)
    seconds = _seconds_from_headers(response_headers)
    if seconds is not None:
        return seconds
    return _seconds_from_headers(getattr(exc, "headers", None))


async def with_overload_retry[T](
    dispatch: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> T:
    """Run ``dispatch``; retry on retryable overload statuses with backoff.

    Honors ``Retry-After`` when present, else exponential backoff + jitter.
    Bounded by ``max_retries`` and a cumulative ``max_total_wait_seconds``
    budget. Re-raises the original exception on exhaustion or non-retryable
    errors.
    """
    attempt = 0
    total_waited = 0.0
    while True:
        try:
            return await dispatch()
        except Exception as exc:
            if not is_retryable_status(exc) or attempt >= policy.max_retries:
                raise
            delay = parse_retry_after_seconds(exc)
            if delay is None:
                delay = min(
                    policy.backoff_base_seconds * 2**attempt,
                    policy.backoff_max_seconds,
                )
            # Jitter both paths (backoff *and* honored Retry-After): concurrent
            # siblings handed the same reset window must de-synchronise, else
            # they wake in lockstep and re-collide on the next window.
            delay += random.uniform(0.0, policy.jitter_seconds)
            if total_waited + delay > policy.max_total_wait_seconds:
                raise
            attempt += 1
            total_waited += delay
            logger.warning(
                "aigw upstream overload (status=%s); retry %d/%d after %.2fs",
                _status_code(exc),
                attempt,
                policy.max_retries,
                delay,
            )
            await sleep(delay)
