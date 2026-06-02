# Design: Reactive Overload Backpressure (Retry + Backoff) in AIGateway

**Date:** 2026-05-29
**Asana:** SF-232 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215231263845954
**Status:** Design approved (brainstorming) — pending implementation plan

## Context

url4 queries are routed through the local AIGateway (`apps/aigateway`, a LiteLLM-based
FastAPI service) to upstream model providers (Anthropic, Gemini, …). When an upstream
provider is overloaded or rate-limits us, LiteLLM raises a corresponding error (HTTP 429,
529, or 503). Today the gateway **catches the error and immediately forwards it** to the
caller (the screamingface server / url4 executor) — there is **no server-side retry,
backoff, or absorption**. The result: transient provider overload surfaces as a hard url4
failure.

**Goal:** Make AIGateway *absorb* transient overload responses by retrying the upstream
dispatch with backoff before giving up — honoring `Retry-After`, capped by a bounded attempt
count and a cumulative-wait budget. If retries are exhausted, behavior is unchanged (the
original status + `Retry-After` are forwarded exactly as today).

### Decisions locked during brainstorming

- **Layer:** Service side — inside `apps/aigateway` (benefits every caller, not just url4).
- **Mechanism:** Reactive retry + backoff only (no proactive throttling / per-key cooldown).
- **Retryable statuses:** `{429 rate-limited, 529 overloaded, 503 service-unavailable}` —
  all share the same correct remedy (wait + retry).
- **Wait budget:** A **fixed** config ceiling (`AIGW_RETRY_MAX_WAIT`), independent of the
  inbound request — tuned to sit under the caller's timeout. (Not derived per-request.)
- **Streaming:** **Out of scope.** `StreamingResponse` returns HTTP 200 before dispatch runs,
  so a mid-stream overload cannot be cleanly retried. The url4 → `AigwBackend` path is
  non-streaming, so the motivating case is fully covered. Streaming is a documented follow-up.
- **API shape:** Higher-order function (`with_overload_retry(dispatch, …)`), not a context
  manager (a `with` body runs once and cannot retry) and not the tenacity-style attempt
  iterator (would hand-roll a library under the no-new-deps rule). HOF is the minimal correct
  fit for our single call site.
- **Delivery:** A single SF ticket (SF-232).

There is a **proven blueprint in-repo**: the Gemini *client-side* backend
(`apps/server/.../gemini_backend_api/backend.py`) already does retry-with-backoff
(`MAX_429_RETRIES = 3`, `MAX_TOTAL_429_WAIT_SECONDS = 30`, `Retry-After`/`retryDelay`
parsing). We mirror that pattern on the **service side**, where one wrap covers all providers.

## Architecture & component boundaries

One new self-contained unit plus three touch-points:

### `apps/aigateway/src/aigateway/core/retry.py` (new)

The entire backpressure mechanism, isolated and independently testable. Depends only on
stdlib (`asyncio`, `random`) and the *shape* of the exception (duck-typed `status_code`) — no
LiteLLM import at module level. Public surface:

- `RetryPolicy` (frozen dataclass): `max_retries`, `backoff_base_seconds`,
  `backoff_max_seconds`, `max_total_wait_seconds`, `jitter_seconds`; plus
  `RetryPolicy.from_settings(settings)`.
- `is_retryable_status(exc) -> bool` — true for LiteLLM `RateLimitError` /
  `ServiceUnavailableError`, **or** any exception whose `status_code` ∈ `{429, 529, 503}`.
  Single source of truth for "should we back off?".
- `parse_retry_after_seconds(exc) -> float | None` — reads `Retry-After` (integer
  delta-seconds) off `exc.response.headers`; malformed/HTTP-date/absent → `None`; negative
  clamped to 0.
- `async with_overload_retry(dispatch, *, policy, sleep=asyncio.sleep) -> Any` — the loop.
  `sleep` is injectable for tests. Re-raises the **original** exception on exhaustion.

### `apps/aigateway/src/aigateway/config.py` (modify)

Add 5 fields to the existing pydantic `Settings` (env prefix `AIGW_`):

```python
retry_max_attempts: int = 3                 # AIGW_RETRY_MAX_ATTEMPTS  (0 disables)
retry_backoff_base_seconds: float = 0.5     # AIGW_RETRY_BACKOFF_BASE
retry_backoff_max_seconds: float = 8.0      # AIGW_RETRY_BACKOFF_MAX
retry_max_total_wait_seconds: float = 30.0  # AIGW_RETRY_MAX_WAIT
retry_jitter_seconds: float = 0.25          # AIGW_RETRY_JITTER
```

**Count semantics (explicit, to remove ambiguity):** `retry_max_attempts` is the number of
**retries** — i.e. *additional* tries after the first dispatch. It maps directly to
`RetryPolicy.max_retries` in `from_settings`. So `retry_max_attempts = 3` means at most **4**
total dispatch calls (1 initial + 3 retries), and `retry_max_attempts = 0` means exactly 1
call with no retry (the kill-switch / today's behavior).

`Settings` is already attached to `app.state.settings` in `main.py:create_app`, so the route
reads it via `request.app.state.settings`.

### `apps/aigateway/src/aigateway/routes/chat.py` (modify)

Wrap the single non-streaming dispatch in `with_overload_retry`; delegate `Retry-After`
parsing to the new helper (DRY — removes the inline copy in `_retry_after_headers`).

## Control flow (the retry loop)

```
attempt = 0
total_waited = 0.0
while True:
    try:
        return await dispatch()          # plugin.chat_completion(body)
    except Exception as exc:
        if not is_retryable_status(exc) or attempt >= policy.max_retries:
            raise                          # non-overload, or out of attempts → original exc
        delay = parse_retry_after_seconds(exc)
        if delay is None:                  # provider gave no hint → exponential backoff
            delay = min(policy.backoff_base_seconds * 2**attempt,
                        policy.backoff_max_seconds) + uniform(0, policy.jitter_seconds)
        if total_waited + delay > policy.max_total_wait_seconds:
            raise                          # budget exhausted → forward original
        attempt += 1
        total_waited += delay
        logger.warning("aigw overload (%s); retry %d after %.2fs", _status(exc), attempt, delay)
        await sleep(delay)
```

Properties:
- **`Retry-After` wins** when present; otherwise exponential backoff + jitter, capped
  per-attempt by `backoff_max_seconds`.
- **Two independent ceilings** — attempt count and cumulative wait budget; whichever trips
  first stops retrying.
- **`max_retries = 0` ⇒ zero retries**, exactly today's behavior (clean kill-switch).
- Re-raises the **original** exception, so existing error mapping runs unchanged.

Wiring in `chat_completions()` (non-streaming branch only):

```python
policy = RetryPolicy.from_settings(request.app.state.settings)
try:
    response = await with_overload_retry(lambda: plugin.chat_completion(body), policy=policy)
except HTTPException as exc:        # unchanged profile-error marking
    ...
except (RateLimitError, ServiceUnavailableError, ...) as exc:
    raise _litellm_http_exception(exc) from exc
```

## Error handling & edge cases

- **Exhaustion is transparent** — the loop re-raises the original exception, so `chat.py`
  maps it exactly as today (`_litellm_http_exception` → status + `Retry-After`; the
  `HTTPException` branch's profile-error marking still fires for custom-plugin overloads).
  No new error surface.
- **`Retry-After` parsing is defensive** — integer delta-seconds only; non-numeric/HTTP-date
  → `None` → backoff fallback; never crashes on a malformed header; negatives clamped to 0.
- **Non-retryable exceptions** (401, 400, connection errors, anything outside `{429,529,503}`)
  bypass the loop on the first check and propagate immediately — no added latency.
- **Budget edge** — if the *next* delay would exceed `max_total_wait_seconds`, give up rather
  than sleep a partial amount. Upper bound on added latency ≈ `max_total_wait_seconds`.
- **Streaming untouched** — `_stream()` keeps current behavior; a one-line comment marks
  streaming retry as a deliberate follow-up.
- **Observability** — one `WARNING` per retry (status, attempt, delay); silent on the happy
  path.

## Testing

### Unit — `tests/unit/test_retry.py` (pure helper, inject no-op `sleep`)

- `is_retryable_status` true for `RateLimitError`, `ServiceUnavailableError`, and bare
  exceptions with `status_code` ∈ {429, 529, 503}; false for 401/400/500/connection errors.
- Overload-then-success: raises 429 once then returns a value → returns it; dispatch called
  twice; slept once.
- Each retryable status (429, 529, 503) triggers a retry (parametrized).
- Always-overload → raises the *original* after exactly `max_retries` retries
  (`max_retries + 1` dispatch calls).
- `Retry-After` honored: present → slept delay equals it; absent → `base·2^n` capped at
  `backoff_max_seconds`, plus jitter within `[0, jitter_seconds]`.
- Budget cap: next delay would exceed `max_total_wait_seconds` → stops early, raises original
  (did not sleep the over-budget amount).
- Kill-switch: `max_retries = 0` → no retry, immediate raise.
- Malformed `Retry-After` (`"abc"`, HTTP-date) → backoff fallback, no crash.

### Route — `tests/unit/test_chat_x_profile.py` (existing `authenticated_client` fixture; patch `asyncio.sleep` to no-op)

- 429-then-200: patch `plugin.chat_completion` to raise once then succeed → endpoint returns
  **200**; plugin called twice (gateway absorbed it).
- Always-429 regression: existing `test_chat_maps_litellm_rate_limit_to_429` stays green →
  **429** with `Retry-After` preserved; dispatch attempted `max_retries + 1` times.
- 503 absorbed-then-success: mirrors the 429 case (proves the broadened status set is wired
  through the route, not just the helper).

## Verification (end-to-end)

1. `cd apps/aigateway && uv run pytest tests/unit/test_retry.py tests/unit/test_chat_x_profile.py -q`
   — all green.
2. Manual: start aigateway, force a 429 (tiny `AIGW_RETRY_MAX_WAIT` + stubbed provider, or a
   low-quota key), issue a url4 query through the screamingface server, and confirm the
   gateway logs `aigw overload … retry N after …s` and the query succeeds instead of failing.
   Set `AIGW_RETRY_MAX_ATTEMPTS=0` and confirm the old immediate-error behavior returns.
3. Run the broader aigateway unit suite to confirm no regressions in chat dispatch.

## Acceptance criteria

- Gateway retries `{429, 529, 503}` up to `AIGW_RETRY_MAX_ATTEMPTS`, honoring `Retry-After` /
  exponential backoff, bounded by the cumulative-wait budget.
- Exhaustion forwards the original status + `Retry-After` unchanged.
- `AIGW_RETRY_MAX_ATTEMPTS=0` restores today's immediate-error behavior.
- Unit + route tests green; no new runtime dependency.

## Out of scope (deliberate)

- Streaming retry (see Context).
- Proactive throttling / concurrency limits / per-key cooldown state. This design is purely
  **reactive** — it absorbs *transient* overload but will not help under *sustained* rate
  pressure, which would need proactive mechanisms. A separate ticket if/when needed.
- Retry on the gateway's other outbound calls (OAuth token exchange, health checks).
