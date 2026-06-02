# AIGateway Reactive Overload Backpressure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AIGateway absorb transient upstream overload (HTTP 429/529/503) by retrying the chat dispatch with `Retry-After`-aware backoff before forwarding the error.

**Architecture:** A self-contained higher-order retry helper (`core/retry.py`, stdlib-only, duck-typed on `status_code`) wraps the single non-streaming dispatch in `routes/chat.py`. Tunable via 5 `AIGW_RETRY_*` settings. On exhaustion the original exception is re-raised, so existing error mapping is unchanged. Streaming is out of scope.

**Tech Stack:** Python 3, FastAPI, pydantic-settings, pytest / pytest-asyncio, httpx, LiteLLM exceptions.

**Spec:** `docs/superpowers/specs/2026-05-29-aigateway-429-backpressure-design.md`
**Asana:** SF-232 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215231263845954

**Working directory for all commands:** `apps/aigateway`. Test runner: `uv run pytest`.

---

## File Structure

- **Create** `apps/aigateway/src/aigateway/core/retry.py` — `RetryPolicy`, `is_retryable_status`, `parse_retry_after_seconds`, `with_overload_retry`. The entire backpressure mechanism. Single responsibility.
- **Modify** `apps/aigateway/src/aigateway/config.py` — add 5 retry settings to `Settings`.
- **Modify** `apps/aigateway/src/aigateway/routes/chat.py` — wrap the dispatch; reuse the helper's `Retry-After` parser in `_retry_after_headers`.
- **Create** `apps/aigateway/tests/unit/test_retry.py` — helper unit tests.
- **Modify** `apps/aigateway/tests/unit/test_chat_x_profile.py` — route-level retry tests.

---

## Task 1: Retry settings on `Settings`

**Files:**
- Modify: `apps/aigateway/src/aigateway/config.py`
- Test: `apps/aigateway/tests/unit/test_config_retry.py` (create)

The `Settings` model uses `env_prefix="AIGW_"`, so a field `retry_max_attempts` is populated by `AIGW_RETRY_MAX_ATTEMPTS` automatically — no `validation_alias` needed. `retry_max_attempts` is the number of **retries** (extra tries after the first); `0` disables retry.

- [ ] **Step 1: Write the failing test**

Create `apps/aigateway/tests/unit/test_config_retry.py`:

```python
from __future__ import annotations

from aigateway.config import Settings


def test_retry_settings_defaults() -> None:
    s = Settings()
    assert s.retry_max_attempts == 3
    assert s.retry_backoff_base_seconds == 0.5
    assert s.retry_backoff_max_seconds == 8.0
    assert s.retry_max_total_wait_seconds == 30.0
    assert s.retry_jitter_seconds == 0.25


def test_retry_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIGW_RETRY_MAX_ATTEMPTS", "0")
    monkeypatch.setenv("AIGW_RETRY_MAX_WAIT", "12.5")
    s = Settings()
    assert s.retry_max_attempts == 0
    assert s.retry_max_total_wait_seconds == 12.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_config_retry.py -v`
Expected: FAIL — `AttributeError`/validation error: `Settings` has no `retry_max_attempts`.

- [ ] **Step 3: Add the settings fields**

In `apps/aigateway/src/aigateway/config.py`, add inside the `Settings` class, after the `public_url` field (line 33) and before the validators:

```python
    retry_max_attempts: int = Field(
        default=3, validation_alias="AIGW_RETRY_MAX_ATTEMPTS"
    )
    retry_backoff_base_seconds: float = Field(
        default=0.5, validation_alias="AIGW_RETRY_BACKOFF_BASE"
    )
    retry_backoff_max_seconds: float = Field(
        default=8.0, validation_alias="AIGW_RETRY_BACKOFF_MAX"
    )
    retry_max_total_wait_seconds: float = Field(
        default=30.0, validation_alias="AIGW_RETRY_MAX_WAIT"
    )
    retry_jitter_seconds: float = Field(
        default=0.25, validation_alias="AIGW_RETRY_JITTER"
    )
```

(Explicit `validation_alias` is used so the env var names stay stable/short — `AIGW_RETRY_MAX_WAIT` rather than the field-derived `AIGW_RETRY_MAX_TOTAL_WAIT_SECONDS`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_config_retry.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/aigateway/src/aigateway/config.py apps/aigateway/tests/unit/test_config_retry.py
git commit -m "feat(aigateway): add AIGW_RETRY_* backpressure settings

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215231263845954"
```

---

## Task 2: The retry helper (`core/retry.py`)

**Files:**
- Create: `apps/aigateway/src/aigateway/core/retry.py`
- Test: `apps/aigateway/tests/unit/test_retry.py` (create)

The helper is status-code-driven (duck-typed). LiteLLM's `RateLimitError`/`ServiceUnavailableError` already expose `status_code` (429/503) — confirmed by `chat.py:_litellm_http_exception` reading `getattr(exc, "status_code", ...)` — so a generic check covers both LiteLLM exceptions and any exception carrying a `status_code`.

- [ ] **Step 1: Write the failing tests**

Create `apps/aigateway/tests/unit/test_retry.py`:

```python
from __future__ import annotations

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

    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        if retry_after is not None:
            request = httpx.Request("POST", "https://example.test/v1/chat/completions")
            self.response = httpx.Response(
                status_code, headers={"retry-after": retry_after}, request=request
            )


def _policy(**kw) -> RetryPolicy:
    base = dict(
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_retry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aigateway.core.retry'`.

- [ ] **Step 3: Implement the helper**

Create `apps/aigateway/src/aigateway/core/retry.py`:

```python
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
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

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


def parse_retry_after_seconds(exc: BaseException) -> float | None:
    """Read an integer ``Retry-After`` (delta-seconds) off the exception's response.

    Returns ``None`` for absent/malformed/HTTP-date values so the caller falls
    back to exponential backoff. Never raises.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form unsupported -> backoff fallback
    return max(0.0, value)


async def with_overload_retry(
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
                ) + random.uniform(0.0, policy.jitter_seconds)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_retry.py -v`
Expected: PASS (all parametrizations).

- [ ] **Step 5: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/aigateway/src/aigateway/core/retry.py apps/aigateway/tests/unit/test_retry.py
git commit -m "feat(aigateway): add with_overload_retry backpressure helper

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215231263845954"
```

---

## Task 3: Wire the helper into the chat route

**Files:**
- Modify: `apps/aigateway/src/aigateway/routes/chat.py`
- Test: `apps/aigateway/tests/unit/test_chat_x_profile.py`

Wrap the single non-streaming dispatch (`chat.py:319`, `response = await plugin.chat_completion(body)`) in `with_overload_retry`, and route `_retry_after_headers` through the shared parser (DRY).

- [ ] **Step 1: Write the failing route tests**

Append to `apps/aigateway/tests/unit/test_chat_x_profile.py` (imports `httpx`, `RateLimitError`, `patch`, `AsyncMock`, `ProfileIndexStore`, `Profile`, `ProfileState`, `profile_id_for` are already present at the top of the file):

```python
def _seed_anthropic_profile(credential_blobs, account_id: str):
    _seed_authenticated_profile(credential_blobs, account_id)
    idx = ProfileIndexStore(credential_store=credential_blobs.store)
    return idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )


@pytest.mark.asyncio
async def test_chat_retries_rate_limit_then_succeeds(
    credential_blobs, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    await _seed_anthropic_profile(credential_blobs, account_id)

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, headers={"retry-after": "1"}, request=request)
    calls = {"n": 0}

    async def flaky_chat_completion(_self, _body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitError(
                "limited",
                llm_provider="anthropic",
                model="anthropic/claude-sonnet-4-5",
                response=response,
            )
        return SimpleNamespace(
            model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]}
        )

    with (
        patch(
            "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
            flaky_chat_completion,
        ),
        patch("aigateway.core.retry.asyncio.sleep", new_callable=AsyncMock),
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert calls["n"] == 2  # gateway absorbed the 429


@pytest.mark.asyncio
async def test_chat_retries_service_unavailable_then_succeeds(
    credential_blobs, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    await _seed_anthropic_profile(credential_blobs, account_id)

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(503, request=request)
    calls = {"n": 0}

    async def flaky_chat_completion(_self, _body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ServiceUnavailableError(
                "overloaded",
                llm_provider="anthropic",
                model="anthropic/claude-sonnet-4-5",
                response=response,
            )
        return SimpleNamespace(
            model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]}
        )

    with (
        patch(
            "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
            flaky_chat_completion,
        ),
        patch("aigateway.core.retry.asyncio.sleep", new_callable=AsyncMock),
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_chat_persistent_rate_limit_still_returns_429(
    credential_blobs, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    await _seed_anthropic_profile(credential_blobs, account_id)

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, headers={"retry-after": "1"}, request=request)
    calls = {"n": 0}

    async def always_limited(_self, _body):
        calls["n"] += 1
        raise RateLimitError(
            "limited",
            llm_provider="anthropic",
            model="anthropic/claude-sonnet-4-5",
            response=response,
        )

    with (
        patch(
            "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
            always_limited,
        ),
        patch("aigateway.core.retry.asyncio.sleep", new_callable=AsyncMock),
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "1"
    assert resp.json()["detail"]["code"] == "rate_limited"
    assert calls["n"] == 4  # 1 initial + 3 retries (default AIGW_RETRY_MAX_ATTEMPTS=3)
```

Add these imports to the top of the test file (alongside existing imports at lines 1-11):

```python
from types import SimpleNamespace
```
```python
from litellm.exceptions import RateLimitError, ServiceUnavailableError
```
(Replace the existing `from litellm.exceptions import RateLimitError` line at line 11 with the combined import above.)

**Also update the existing regression test so it stays fast.** Once retry is wired, `test_chat_maps_litellm_rate_limit_to_429` (lines 722-761) raises 429 on every attempt and would otherwise sleep `7s × 3` of real time. Wrap its `patch(...)` in a `with` that also patches sleep, and assert the retry count. Change its `with patch(...)` block (lines 747-757) to:

```python
    with (
        patch(
            "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
            fake_chat_completion,
        ),
        patch("aigateway.core.retry.asyncio.sleep", new_callable=AsyncMock),
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
```

The existing assertions (status 429, `retry-after == "7"`, `code == "rate_limited"`) stay unchanged — the gateway exhausts retries and forwards the original 429.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_chat_x_profile.py -k "retries or persistent_rate_limit" -v`
Expected: FAIL — the 429-then-success / 503-then-success cases return 429/503 (no retry yet); `calls["n"] == 1`. (`test_chat_persistent_rate_limit_still_returns_429` may pass on status but FAIL on `calls["n"] == 4`.)

- [ ] **Step 3: Add the import and policy in `chat.py`**

In `apps/aigateway/src/aigateway/routes/chat.py`, add to the imports (after the existing relative imports block, around line 28):

```python
from ..core.retry import RetryPolicy, parse_retry_after_seconds, with_overload_retry
```

- [ ] **Step 4: Route `_retry_after_headers` through the shared parser**

Replace the existing `_retry_after_headers` (lines 198-202):

```python
def _retry_after_headers(exc: Exception) -> dict[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = headers.get("retry-after") if headers is not None else None
    return {"Retry-After": retry_after} if retry_after else {}
```

with:

```python
def _retry_after_headers(exc: Exception) -> dict[str, str]:
    seconds = parse_retry_after_seconds(exc)
    if seconds is None:
        return {}
    # delta-seconds is an integer; round up so clients do not retry early.
    return {"Retry-After": str(math.ceil(seconds))}
```

Add `import math` to the top-level imports (after `import logging`, line 6).

- [ ] **Step 5: Wrap the dispatch with retry**

In `chat_completions()`, replace the single dispatch line (line 319):

```python
        response = await plugin.chat_completion(body)
```

with:

```python
        policy = RetryPolicy.from_settings(request.app.state.settings)
        response = await with_overload_retry(
            lambda: plugin.chat_completion(body), policy=policy
        )
```

Leave the surrounding `try` / `except HTTPException` / `except (RateLimitError, ...)` blocks unchanged — they map the re-raised exception on exhaustion exactly as before. Add a one-line comment above the streaming branch (line 315, `if body.get("stream"):`) noting streaming retry is a deliberate follow-up:

```python
    # NOTE: overload retry covers the non-streaming path only; streaming responses
    # commit a 200 status before dispatch, so a mid-stream 429/503 cannot be retried.
    if body.get("stream"):
```

- [ ] **Step 6: Run the new route tests to verify they pass**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_chat_x_profile.py -k "retries or persistent_rate_limit" -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the existing rate-limit regression + full chat suite**

Run: `cd apps/aigateway && uv run pytest tests/unit/test_chat_x_profile.py -v`
Expected: PASS — including the pre-existing `test_chat_maps_litellm_rate_limit_to_429` (status 429, `retry-after: 7` preserved, `code == "rate_limited"`).

- [ ] **Step 8: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/aigateway/src/aigateway/routes/chat.py apps/aigateway/tests/unit/test_chat_x_profile.py
git commit -m "feat(aigateway): retry 429/529/503 on chat dispatch with backoff

https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215231263845954"
```

---

## Task 4: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full aigateway unit suite**

Run: `cd apps/aigateway && uv run pytest -q`
Expected: PASS — no regressions across the gateway. If a lint/format hook runs on commit, ensure it is clean (`uv run ruff check . && uv run ruff format --check .` if configured).

- [ ] **Step 2: Manual smoke (optional but recommended)**

Start the gateway with an aggressive-but-safe retry budget and a low-quota or stubbed provider that returns 429, issue a url4 query through the screamingface server, and confirm the gateway logs:

```
aigw upstream overload (status=429); retry 1/3 after 1.00s
```

and the query succeeds. Then set `AIGW_RETRY_MAX_ATTEMPTS=0`, repeat, and confirm the old immediate-429 behavior returns (no retry log line).

---

## Notes for the implementer

- **DRY:** `parse_retry_after_seconds` is the single `Retry-After` parser; `_retry_after_headers` and the retry loop both use it.
- **YAGNI:** No proactive throttling, no per-key cooldown, no streaming retry, no retry on OAuth/health calls — all explicitly out of scope (see spec).
- **TDD:** Every task is test-first; the helper is fully unit-tested in isolation before wiring.
- **Determinism in tests:** the helper unit tests set `jitter_seconds=0.0`; route tests patch `aigateway.core.retry.asyncio.sleep` so no real waiting occurs.
- **Kill-switch:** `AIGW_RETRY_MAX_ATTEMPTS=0` restores today's behavior exactly (verified by Task 2 unit test + Task 4 manual step).
