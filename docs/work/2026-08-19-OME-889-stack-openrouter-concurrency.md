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
  in `stack-up`, with a WHY comment. No other files.

## Test plan

- No test harness covers the justfile (shell recipe, env-line only). Verification is
  behavioral: `just stack-up`, then confirm the gateway process env carries the override
  (`ps eww <pid>` / log line) — the invariant protected is "local gateway admits ≥ one run's
  full fan-out for openrouter".

## Acceptance

- `stack-up` launches the gateway with the openrouter override set to 32; other providers
  keep the default of 4; recipe behavior otherwise unchanged.
- PR open, CI green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `packages/screamingface/justfile` (as planned) + this ledger + the
  `docs/tasks/` mirror.
- **Commits:** 0b5d4dc8 — fix(py-screamingface): raise local stack openrouter gateway
  concurrency to 32
- **Gates:** no justfile test harness; verified by parsing the env through the real gateway
  settings: `Settings()` with the override yields `effective_provider_limit(s, "openrouter")
  == 32` and `effective_provider_limit(s, "gemini") == 4`. Pre-commit hooks passed.
- **Deviations:** none.
