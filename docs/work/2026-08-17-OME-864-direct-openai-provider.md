---
ticket: OME-864
stack: aigateway
status: blocked
started: 2026-08-17
finished:
---

# OME-864 - Direct OpenAI Platform API-key provider

## Intent

Add direct, account-scoped OpenAI Platform API-key dispatch under `openai/*` while preserving the
existing `codex/*` OAuth and `openrouter/openai/*` routes. The P0 increment is seed-only,
non-streaming, Chat Completions-only, globally cache-bypassed, and usage-accounting unsupported.

## Planned changes

- Add `apps/aigateway/src/aigateway/plugins/openai_provider/` with settings, parameter contract,
  two-stage API-key validation, request isolation, and plugin composition.
- Add focused tests under `apps/aigateway/tests/unit/openai/` and an opt-in live test.
- Strengthen `apps/aigateway/tests/unit/core/test_codex_namespace_guard.py` to prove independent
  `codex/*` and `openai/*` ownership.
- Reuse generic profile/connection persistence without schema, migration, dependency, or core-route
  changes.

## Test plan

- RED first for plugin discovery, seed registration, API-key-only capability, `max_tokens` rule,
  bypass disposition, observation evidence, and namespace ownership.
- RED for bounded authentication/readiness validation and conservative typed-error classification.
- RED for request-local `AsyncOpenAI`, official endpoint, selected key, ambient-header suppression,
  Responses-bridge skip, retry/cache controls, client closure, and sanitized failures.
- RED for global `CacheBypass`, unsupported accounting, and both generic API-key persistence paths.
- Run focused suites, append-only verification, and the complete AIGateway gate.

## Acceptance

- The auto-discovered `openai` plugin serves only approved seeds and exposes API-key auth.
- `max_tokens` is the only enabled P0 optional field and is evidenced under both upstream wire names.
- Every dispatch remains on the official non-streaming Chat Completions endpoint with only the
  selected account key and no ambient organization/project/custom-header influence.
- Profile and API-key connection create/replace/select/delete flows preserve encryption,
  transactions, account isolation, and old state on failed replacement.
- OpenAI performs no AIGateway global-cache read/write and publishes no fabricated accounting.
- Existing providers remain green and the complete AIGateway gate passes.

## Process decisions

- Owner authorized implementation in the current checkout on branch
  `OME-864-direct-openai-provider`; no worktree is used.
- Owner instructed that Linear remain unchanged during this increment, so its status is not moved.
- `OPENAI_API_KEY` is currently unavailable locally. Live seed/readiness verification remains a
  release blocker unless the owner later supplies a safe local key and spend authorization.
- Owner selected the twelve-model seed documented in the canonical spec (the reviewed ten plus
  `openai/gpt-5.5` and `openai/gpt-5.6`), `openai/gpt-5-nano` for readiness, and offline
  implementation now with live verification deferred.

## Post-commit review remediation

- **Intent:** close the confirmed missing-live-test finding without guessing the unresolved live
  behavior of the reasoning-model readiness probe.
- **Planned changes:** add an owner-gated OpenAI live test that exercises the production API-key
  validator with `openai/gpt-5-nano`; make no production classifier, OpenRouter, core-port, or client
  lifecycle change without separate evidence and scope.
- **Test plan:** prove the test artifact is absent, add the live-marked test, verify it skips without
  explicit authorization/credentials, then run focused OpenAI tests and the full AIGateway gate.
- **Acceptance:** the test is collected only as `live`, skips unless `AIGW_LIVE=1` and a local
  `OPENAI_API_KEY` are both present, consumes no quota in normal gates, reports only sanitized
  validation state, and will fail if the current one-token reasoning probe rejects a valid key.

## Outcome (fill at the end - required before COMMIT)

- **Actual files:**
  - `apps/aigateway/src/aigateway/plugins/openai_provider/__init__.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/api_key_validation.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/parameters.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/plugin.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/settings.py`
  - `apps/aigateway/tests/unit/openai/test_openai_api_key_validation.py`
  - `apps/aigateway/tests/unit/openai/test_openai_dispatch.py`
  - `apps/aigateway/tests/unit/openai/test_openai_gateway_acceptance.py`
  - `apps/aigateway/tests/unit/openai/test_openai_persistence.py`
  - `apps/aigateway/tests/unit/openai/test_openai_provider.py`
  - `apps/aigateway/tests/unit/core/test_codex_namespace_guard.py`
- **Commits:** this OME-864 implementation commit (`feat(aigateway): add direct OpenAI API-key
  provider`)
- **Gates:** baseline full gate green; final focused regression set 90 passed; final full AIGateway
  lint, format, Pyright, no-enterprise, and coverage test gates green; final source audit found no
  remaining correctness or security findings
- **Deviations:**
  - Live seed/readiness verification is deferred by owner choice and remains the release blocker.
  - The append-only check is intentionally skipped for the one existing Codex namespace test whose
    old assertion prohibited the new provider by definition. The replacement strengthens the guard
    to prove independent overlapping `codex/*` and `openai/*` ownership. Running the check without
    that explicit exception fails only on this documented edit.
  - A pre-guard test accidentally reached OpenAI once with a synthetic invalid key. It consumed no
    account credential or inference spend and produced the bounded invalid-key tuple used by the
    conservative classifier.
  - Exact evidence is not available for expired, permission-denied, or rate-limited OpenAI tuples;
    those public states stay explicit but unpromoted, and candidate responses return `unavailable`.

### Post-commit live-test outcome

- **Actual files:**
  - `apps/aigateway/tests/live/test_openai_live.py`
  - `docs/work/2026-08-17-OME-864-direct-openai-provider.md`
- **Commits:** this follow-up commit (`test(aigateway): add OpenAI live readiness smoke`).
- **Checks:** missing-file RED confirmed; one live test collected; no-authorization and no-key paths
  each skipped without a network call; focused OpenAI/Codex regression `71 passed, 1 deselected`;
  isolated pre-existing auth timing failure passed on rerun; repeated full AIGateway gate green with
  the documented append-only exception.
- **Status:** the live-test scaffold is complete. Release remains blocked until an owner-authorized
  real-key run executes it; no production readiness behavior was guessed or changed.
