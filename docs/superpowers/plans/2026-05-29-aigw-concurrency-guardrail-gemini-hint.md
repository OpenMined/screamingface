# AIGateway Concurrency Guardrail + Gemini Retry-After Hint — Implementation Plan

> **For agentic workers:** TDD, task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stop the url4 leaderboard fan-out from hard-failing on provider 429s by (A) honoring the provider's *actual* reset window and (B) bounding concurrent upstream calls per provider so the fan-out cannot self-exhaust a quota.

**Architecture:** Two additions to `apps/aigateway`, both wrapping the existing `with_overload_retry` from SF-232.
- **A** — make the reset hint survive: the Gemini plugin parses `retryDelay` / "reset after Ns" from the 429 body and attaches a `Retry-After` header to the `HTTPException` it raises; `core/retry.parse_retry_after_seconds` is generalized to read `exc.headers` (FastAPI `HTTPException`) in addition to `exc.response.headers` (LiteLLM exceptions). So retry waits the real window instead of guessing.
- **B** — a proactive per-provider concurrency limiter: `AIGW_PROVIDER_MAX_CONCURRENCY` (0 = unlimited) gates concurrent upstream dispatches per provider via an `asyncio.Semaphore` registry on `app.state`. `chat.py` acquires the provider slot around `with_overload_retry`, so only N calls hit a provider at once and quota resets aren't immediately re-consumed.

**Tech Stack:** Python 3.12+, FastAPI, pydantic-settings, pytest/pytest-asyncio, httpx, LiteLLM.

**Asana:** SF-233. **Branch:** `SF-233-aigw-concurrency-guardrail-gemini-hint` (stacked on SF-232). **Working dir:** `apps/aigateway`, runner `uv run pytest`.

---

## Task A1: `parse_retry_after_seconds` reads `exc.headers`

**Files:** Modify `src/aigateway/core/retry.py`; Test `tests/unit/test_retry.py`.

- [ ] Test: an exception exposing `.headers = {"retry-after": "3"}` (no `.response`) → `parse_retry_after_seconds` returns `3.0`; precedence: `.response.headers` checked first, then `.headers`.
- [ ] Implement: after the `response.headers` lookup, fall back to `getattr(exc, "headers", None)` and read `retry-after` there too. Keep the defensive float-parse (malformed/HTTP-date → None, negatives clamped).
- [ ] Run `uv run pytest tests/unit/test_retry.py -q`; commit.

## Task A2: Gemini plugin propagates the reset hint

**Files:** Modify `src/aigateway/plugins/gemini_provider/chat_handler.py`, `src/aigateway/plugins/gemini_provider/plugin.py`; Test `tests/unit/gemini/` (or `test_retry.py` for the parser helper).

- [ ] Add `parse_gemini_retry_after(response_text: str, headers) -> float | None` in `chat_handler.py`: prefer a `Retry-After` header; else parse `"retryDelay": "Ns"` from the body JSON; else regex `reset after (\d+(?:\.\d+)?)s`. Returns None when nothing matches.
- [ ] In `_error_from_response`, when status is retryable, compute the hint from the **full** `response.text` (before the 500-char preview truncation) and stash it on the `CustomLLMError` (`err.retry_after = seconds`).
- [ ] In `plugin.chat_completion`'s `except CustomLLMError`, if `getattr(exc, "retry_after", None)` is set, pass `headers={"Retry-After": str(math.ceil(seconds))}` into the `HTTPException`.
- [ ] Tests: a 429 body with `"reset after 3s"` → parser returns 3.0; a `retryDelay: "5s"` → 5.0; neither → None.
- [ ] Run tests; commit.

## Task B1: `AIGW_PROVIDER_MAX_CONCURRENCY` setting

**Files:** Modify `src/aigateway/config.py`; Test `tests/unit/test_config_retry.py`.

- [ ] Test: default `provider_max_concurrency == 4`; `AIGW_PROVIDER_MAX_CONCURRENCY=0` → 0.
- [ ] Implement: `provider_max_concurrency: int = Field(default=4, validation_alias="AIGW_PROVIDER_MAX_CONCURRENCY")`.
- [ ] Run; commit.

## Task B2: per-provider semaphore + wire into dispatch

**Files:** Create `src/aigateway/core/concurrency.py`; Modify `src/aigateway/routes/chat.py`; Test `tests/unit/test_concurrency.py`, `tests/unit/test_chat_x_profile.py`.

- [ ] `concurrency.py`: `@asynccontextmanager async def provider_slot(app, provider, limit)` — `limit <= 0` yields immediately; else get-or-create an `asyncio.Semaphore(limit)` from `app.state.provider_semaphores` (keyed by provider, re-created if the configured limit changed) and `async with` it.
- [ ] Test (`test_concurrency.py`): with `limit=2`, a third concurrent entrant blocks until one exits (assert max observed concurrency == 2); `limit=0` never blocks.
- [ ] `chat.py`: extract `async def _dispatch_with_backpressure(request, plugin, provider, body)` that acquires `provider_slot(...)` around `with_overload_retry(lambda: plugin.chat_completion(body), policy=RetryPolicy.from_settings(settings))`; call it from `chat_completions` (1 statement — also keeps the function under the PLR0915 limit).
- [ ] Route test: existing retry/regression tests stay green; add one asserting a `limit=1` serializes two concurrent chat calls (or simply that dispatch still works with the guardrail in place).
- [ ] Run `uv run pytest tests/unit/test_chat_x_profile.py tests/unit/test_concurrency.py -q`; commit.

## Task B3: full verification + PR

- [ ] `uv run pytest -q` (full suite green).
- [ ] `uv run ruff check .` + `uv run ruff format --check .` + `uv run pyright` all clean.
- [ ] Push `SF-233-...`; open PR with base `SF-232-aigateway-overload-backpressure` (stacked; auto-retargets to main as the stack merges). No merge.

## Notes
- **DRY:** one reset-hint parser per provider; `parse_retry_after_seconds` is the single consumer in the retry loop.
- **Semaphore wraps retry** (not vice-versa) so a provider slot is held across backoff — bounding *total* concurrent upstream pressure, including retries.
- **Codex** has the same body-hint shape; the `retry.py` generalization already benefits it, and adding `parse_*_retry_after` there is an easy follow-up (out of scope here).
