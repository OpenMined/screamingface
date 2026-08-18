---
ticket: OME-864
stack: aigateway
status: done
started: 2026-08-17
finished: 2026-08-18
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
- Owner initially selected the twelve-model seed documented in the canonical spec (the reviewed ten
  plus `openai/gpt-5.5` and the `openai/gpt-5.6` family alias), `openai/gpt-5-nano` for readiness,
  and offline implementation with live verification deferred. The authorized live pass later
  superseded the family alias with the three concrete Sol, Terra, and Luna variants.

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

## Authorized live verification and readiness remediation

- **Intent:** resolve the readiness false negative from owner-authorized live evidence while keeping
  validation quota and latency bounded.
- **Observed evidence:** the first live run timed out during the authentication stage; a direct safe
  probe then returned `GET /v1/models` HTTP 200 with the expected list shape. The next live run
  reached readiness and returned `unavailable`. A diagnostic request with
  `max_completion_tokens: 1` returned HTTP 400 `invalid_request_error` before generation, while the
  same request with `16` returned HTTP 200 `chat.completion`, `finish_reason: length`, an empty
  string `content`, and exactly 16 reasoning/completion tokens. No raw provider message, prompt,
  credential, organization, or project identity was recorded.
- **Seed evidence:** the original eleven non-alias IDs were visible in `/v1/models`; `gpt-5.6` was
  absent and its retrieve endpoint returned `404 model_not_found`, but Chat Completions accepted the
  alias and returned concrete model `gpt-5.6-sol`. The live catalog lists
  `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`, and locked LiteLLM 1.95.0 classifies all three
  as OpenAI chat models. Owner decision: replace the alias with those three concrete variants,
  yielding fourteen visible seeds and explicit capability/cost choices.
- **Final-wire evidence:** the first end-to-end gateway route reached OpenAI but returned sanitized
  HTTP 400. Direct Luna dispatch passed; production-plugin dispatch failed. Offline capture proved
  LiteLLM emitted `ssl_verify: true` inside the provider JSON, and a bounded direct request with that
  field returned HTTP 400 `unknown_parameter` for `ssl_verify`. Removing the body control preserved
  TLS on the owned `httpx.AsyncClient(verify=True, trust_env=False)` and made the route pass.
- **Planned changes:** retain the bounded readiness parameter, set its live-verified budget to 16,
  update the exact wire-contract assertion, and pin the observed empty-string length response as a
  valid readiness result. Replace the `gpt-5.6` family alias with the three live-listed concrete
  variants and update catalog/dispatch/persistence contracts. Do not remove the budget or widen any
  error tuple.
- **Test plan:** run the focused validator tests, rerun the owner-gated live test, then run the full
  AIGateway gate with the existing append-only exception.
- **Acceptance:** the production validator sends `max_completion_tokens: 16`, accepts the observed
  structurally valid empty-string completion, the live test reaches `VALID` at `READINESS`, no key is
  exposed, and all non-live gates remain green.

### Authorized live-remediation outcome

- **Actual files:**
  - `apps/aigateway/src/aigateway/plugins/openai_provider/plugin.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/api_key_validation.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/settings.py`
  - `apps/aigateway/tests/live/test_openai_live.py`
  - `apps/aigateway/tests/unit/openai/test_openai_api_key_validation.py`
  - `apps/aigateway/tests/unit/openai/test_openai_dispatch.py`
  - `apps/aigateway/tests/unit/openai/test_openai_gateway_acceptance.py`
  - `apps/aigateway/tests/unit/openai/test_openai_persistence.py`
  - `apps/aigateway/tests/unit/openai/test_openai_provider.py`
  - `docs/plan/2026-08-17-OME-864-direct-openai-provider.md`
  - `docs/spec/2026-08-17-OME-864-direct-openai-provider.md`
  - `docs/tasks/2026-08-17-OME-864-direct-openai-provider.md`
  - `docs/work/2026-08-17-OME-864-direct-openai-provider.md`
- **Commits:** this live-remediation commit (`fix(aigateway): apply OpenAI live verification
  fixes`).
- **Checks:** validator unit suite `24 passed`; owner-gated readiness passed; end-to-end gateway route
  passed; all fourteen concrete seeds passed the production-plugin sweep; focused OpenAI/Codex
  regression `74 passed, 3 live deselected`; the pre-existing auth timing test flaked once and passed
  in isolation; repeated full AIGateway lint, format, Pyright, no-enterprise, and coverage gates
  green with the documented append-only exception.
- **Status:** readiness and final-wire behavior are live-confirmed. All OME-864 code and
  provider-verification gates are complete; no credential, raw provider message, prompt,
  organization, or project identity was recorded.
