---
ticket: OME-889
stack: repo
status: done
started: 2026-08-19
finished: 2026-08-19
---

# OME-889 — Raise the local stack's OpenRouter gateway concurrency to match the Engine's 32-call fan-out

## Intent

Short-term unblock for the ~600s eval failures `OME-886` diagnoses: one Engine run fans out
up to 32 concurrent model calls (`DEFAULT_RUN_CONCURRENCY`, `packages/url4/src/url4/dag/node.py`),
but the local stack launches the gateway at its code default of 4 concurrent calls per
provider. Queued calls wait inside the gateway's semaphore with no admission deadline and
burn the Engine's 600s per-call HTTP budget — full local HealthBench evals die at ~600.1s on
calls that never reached OpenRouter. Matching the local gateway's OpenRouter admission to a
single run's worst-case fan-out removes the queue entirely.

## Planned changes

- `packages/screamingface/justfile` — add
  `AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES='{"openrouter": 32}'` to the gateway launch env
  in `stack-up`, with a WHY comment.
- (owner-directed scope addition, replacing canceled `OME-891`)
  `apps/aigateway/src/aigateway/core/concurrency.py` — INFO log when a provider's
  semaphore is created/rebuilt, so the gateway log itself proves which limit is in force:
  `provider concurrency limit applied provider=openrouter limit=32`. Once per provider per
  process; re-logged only when the configured limit changes. Structured admission telemetry
  stays with `OME-886`.
- `apps/aigateway/src/aigateway/logs.py` (new) + `create_app()` wiring in `main.py` —
  found live-testing the log line: aigateway never configures app logging, so every
  `aigateway.*` INFO record fell through to `logging.lastResort` (WARNING+) and was
  discarded in every deployment. Same defect the engine fixed in
  `screamingface_engine/logs.py`; mirrored here (apps must not import each other's
  internals). `AIGW_LOG_LEVEL` env, default INFO, idempotent handler, propagate off.

## Test plan

- No test harness covers the justfile (shell recipe, env-line only). Verification is
  behavioral: `just stack-up`, then confirm the gateway process env carries the override
  (`ps eww <pid>` / log line) — the invariant protected is "local gateway admits ≥ one run's
  full fan-out for openrouter".
- Log line (append-only additions to `apps/aigateway/tests/unit/test_concurrency.py`):
  (1) first acquisition for a provider logs provider + effective limit at INFO;
  (2) re-acquisition at the same limit does NOT log again (no per-request noise);
  (3) a limit change logs the new limit (invariant: the log always reflects the limit in
  force). Gates: full aigateway stack via `run_gates.py aigateway`.

## Acceptance

- `stack-up` launches the gateway with the openrouter override set to 32; other providers
  keep the default of 4; recipe behavior otherwise unchanged.
- PR open, CI green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `packages/screamingface/justfile` (as planned) + this ledger + the
  `docs/tasks/` mirror + (owner-directed addition) `apps/aigateway/src/aigateway/core/
  concurrency.py` and `apps/aigateway/tests/unit/test_concurrency.py`.
- **Commits:** 0b5d4dc8 — fix(py-screamingface): raise local stack openrouter gateway
  concurrency to 32; 9689fac4 — feat(aigateway): log the concurrency limit applied per
  provider; e0766e22 — fix(aigateway): configure app logging so INFO records actually
  emit (live test showed the line missing: uvicorn leaves the root logger handler-less,
  so all aigateway.* INFO fell through to lastResort at WARNING; mirrored the engine's
  logs.py).
- **Gates:** justfile env verified through the real settings parser
  (`effective_provider_limit("openrouter") == 32`, others 4). Log line: TDD (3 appended
  tests, RED first) + `run_gates.py aigateway` ALL GREEN (ruff check/format, pyright,
  no-enterprise check, pytest cov≥80, append-only test check).
- **Deviations:** scope grew by owner decision — the observability log line originally
  filed as `OME-891` was folded in here and `OME-891` canceled.
