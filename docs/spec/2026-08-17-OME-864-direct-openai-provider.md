# Add direct OpenAI Platform API-key provider to AIGateway

## Ticket metadata

| Field | Value |
|---|---|
| Linear | [OME-864](https://linear.app/openmined/issue/OME-864/add-direct-openai-platform-api-key-provider-to-aigateway) |
| Status | Pick Immediately |
| Priority | Urgent (Linear priority 1); P0 implementation scope |
| Labels | `aigateway`, `agentic`, `autonomous` |
| Assignee | Dmitry |
| Project | ScreamingFace V1 |

## Outcome

Add a first-class direct OpenAI Platform provider for users who connect their own OpenAI API key.
The provider is separate from both existing ways to reach OpenAI-family models:

- `codex/*` remains the OAuth-only ChatGPT subscription provider.
- `openrouter/openai/*` remains OpenRouter-routed access paid and governed through OpenRouter.
- `openai/*` becomes direct OpenAI Platform access paid and governed by the selected account's
  OpenAI API key.

The P0 increment uses the existing AIGateway `/v1/chat/completions` contract. It is deliberately
non-streaming and supports only models and parameter combinations proven to remain on OpenAI's Chat
Completions endpoint. It dispatches only the approved registered seed in P0 and explicitly bypasses
the AIGateway global exact-response cache. Native Responses API support, arbitrary unlisted models,
and OpenAI global-cache projection are separate follow-ups.

## Verified foundation

- `apps/aigateway` is the smallest relevant project root.
- Provider discovery loads direct `aigateway.plugins.*_provider` packages whose `plugin.py` exports
  a module-level `PLUGIN` instance of `ProviderPluginBase`.
- `custom_llm_provider` is the first segment of every canonical model ID and selects the plugin.
  Therefore `codex/gpt-*` and `openai/gpt-*` can coexist without a runtime routing collision.
- The existing generic API-key profile and connection routes call a provider's
  `api_key_strategy_for()` and `api_key_validator()` hooks. A new provider-specific auth route is
  unnecessary.
- `ApiKeyStrategy`, `ProfileIndexStore`, `OAuthConnection`, `ORMStore`, and encrypted
  `credential_blobs` already provide account-scoped API-key persistence and atomic publication.
- Locked runtime versions:
  - Python `3.12.9`
  - LiteLLM `1.95.0`
  - OpenAI Python `2.53.0`
  - Tortoise ORM `1.1.7`
- Pinned wire behavior transforms `model="openai/gpt-5"`, an explicit request-local key, and the
  official base into upstream model `gpt-5`, the selected Bearer key, and
  `https://api.openai.com/v1/chat/completions`, overriding API-key and base fallbacks.
- Without explicit suppression, ambient
  `OPENAI_ORGANIZATION` and `OPENAI_PROJECT_ID` are sent as `OpenAI-Organization` and
  `OpenAI-Project` even when the account-scoped key and official base are explicit.
- The pinned full-dispatch contract guarantees that a request-local
  `AsyncOpenAI` with `Omit()` default headers suppresses both organization and project headers,
  preserves the selected key and official Chat Completions URL, and survives LiteLLM mutating the
  supplied client's organization field.
- `_skip_responses_api_bridge=True` keeps both `openai/gpt-4o` and
  `openai/gpt-5` on `/v1/chat/completions` even when LiteLLM's global Responses flag is true.
- The existing `litellm_async_http` accounting capability is incompatible with native OpenAI
  dispatch: it injects an `AsyncHTTPHandler`, while LiteLLM's OpenAI path requires an `AsyncOpenAI`
  client and calls `.chat.completions`. P0 therefore declares accounting unsupported rather than
  widening core transport scope.
- LiteLLM `1.95.0` can implicitly bridge `acompletion()` to the Responses API based on a global
  flag, model metadata, a `responses/` model name, or selected GPT-5 parameter combinations.
- OpenAI's Models API reports availability and ownership, not a complete chat-capability schema.
  Its result cannot be copied wholesale into the AIGateway model seed.
- The provider-conformance suite auto-discovers every plugin and requires every conformance model
  to have non-empty, evidenced, auth-scoped parameter rules.
- OME-305 already owns the global exact-response cache framework. Providers without a proven pure
  projection safely bypass it; OME-787 is the intended parent for additional provider coverage, but
  its current table does not include OpenAI and needs a dedicated follow-up sub-issue.
- `tests/unit/core/test_codex_namespace_guard.py` currently asserts that no `openai` provider
  exists. The historical intent is to protect Codex ownership, but that literal assertion becomes
  invalid when this task lands and must be replaced by a stronger two-namespace ownership check.

Public OpenAI Python documentation confirms `AsyncOpenAI` custom HTTP-client construction and the
`OPENAI_ORG_ID` / `OPENAI_PROJECT_ID` environment contract. The private LiteLLM bridge-skip and
native `client=` behavior are locked-version contracts enforced by final-wire tests. Tortoise ORM
`1.1.7` confirms that a behavior-only provider addition using existing models requires no migration.

## Live-release blocker

Source implementation proceeds with deterministic offline coverage. Release remains blocked until
the owner provides all of the following without recording secret material in this specification:

- an OpenAI API key available through an approved local live-test mechanism;
- an explicit maximum spend for the bounded Models/readiness validation requests;
- live account confirmation for the approved production seed;
- live account confirmation for the approved low-cost validation model;
- dated evidence that every selected seed is visible to the account and reaches Chat Completions.

The owner-approved offline seed is:

```text
openai/gpt-5.6
openai/gpt-5.5
openai/gpt-5.1
openai/gpt-5
openai/gpt-5-mini
openai/gpt-5-nano
openai/gpt-4.1
openai/gpt-4.1-mini
openai/gpt-4o
openai/gpt-4o-mini
openai/o3
openai/o4-mini
```

The approved readiness model is `openai/gpt-5-nano`. Locked runtime metadata classifies all twelve
as direct OpenAI chat models. Live account visibility and real readiness remain release gates, not
source-implementation prerequisites.

Owner ruling: keep Linear OME-864 unchanged for now. This reviewed canonical spec and plan define the
implementation increment. The separate OpenAI caching issue may be filed later and is not a P0
prerequisite.

## Architecture constraints

### Provider package

Add `apps/aigateway/src/aigateway/plugins/openai_provider/` with a module-level `PLUGIN` and:

```text
custom_llm_provider = "openai"
provider_display_name = "OpenAI"
```

The package owns OpenAI settings, model seeds, API-key validation, the `max_tokens` parameter rule
and observation, request preparation, explicit cache bypass, and dispatch hardening. Do not add an
OpenAI branch to the loader, registry, chat route, model route, provider route, credential routes, or
core accounting taxonomy.

### Credential and Tortoise boundary

- Support API-key auth only. `oauth_config()` remains `None`.
- Reuse `ApiKeyStrategy` with an OpenAI-specific credential service namespace.
- Reuse the generic encrypted profile/connection lifecycle and its existing transaction ordering.
- Add no Tortoise model, field, migration, ORMStore change, repository, or signal.
- Never read or write an OS keychain under `apps/aigateway`.
- Never write plaintext secrets directly to `credential_blobs`; all writes continue through
  `ORMStore` and the active `SecretStoreMixin`.

### Model identity

- Public gateway IDs use `openai/<model>`.
- Validate configured IDs in the settings `@field_validator`; there is no plugin-level
  `validate_model_id` hook.
- The plugin validates exactly one `openai/` prefix and passes the prefixed ID unchanged into
  `litellm.acompletion()`; LiteLLM owns stripping that prefix for the upstream wire model.
- `/v1/models` contains a curated, live-verified seed of direct OpenAI chat-capable models.
- P0 dispatch is restricted to those registered seeds so `/v1/models`, `/v1/model-parameters`,
  parameter enforcement, and chat dispatch describe the same model set.
- Do not register `responses/<model>` aliases in this P0 task.

### Chat Completions boundary

- All P0 dispatches must reach `https://api.openai.com/v1/chat/completions`.
- `stream:true` is rejected before `_inject_credentials()` reads the credential secret.
- No allowed model or parameter combination may trigger LiteLLM's Responses bridge.
- Pass the pinned private LiteLLM kwarg `_skip_responses_api_bridge=True` request-locally so a
  process-global `route_all_chat_openai_to_responses` flag cannot redirect this provider.
- Every approved seed must remain `mode="chat"`; a Responses-only seed fails closed before dispatch.
- The official Chat Completions path is an executable contract of the locked LiteLLM `1.95.0`
  runtime, proven by no-network final-wire tests. P0 does not add runtime URL interception.
- Responses API, streaming, conversation state, and Responses-only tools remain separate work.

### Request and credential isolation

Before the account key is read, retain the existing provider-neutral stripping of caller-supplied
credentials, bases, headers, fallbacks, callbacks, retries, caches, mocks, and logging controls.
At the provider boundary:

- Pin `https://api.openai.com/v1` and verified TLS.
- Inject only the selected account-scoped API key.
- Set configured LiteLLM retries to zero and disable LiteLLM caching; AIGateway owns those policies.
- Build a request-local `AsyncOpenAI` after credential injection with the selected key, official
  base, `max_retries=0`, and `default_headers` containing `Omit()` for
  `OpenAI-Organization` and `OpenAI-Project`; pass it through LiteLLM's `client=` seam and close it
  after the non-streaming dispatch.
- Treat `organization=None` / `project=None` as unsafe: OpenAI Python interprets `None` as unset and
  reads `OPENAI_ORG_ID` / `OPENAI_PROJECT_ID` from the environment.
- Refuse dispatch when `OPENAI_CUSTOM_HEADERS` is non-empty; arbitrary ambient header names cannot
  be exhaustively neutralized by the two fixed `Omit()` entries.
- Prevent caller and ambient values from selecting the host, credential, organization, project,
  custom headers, callback destinations, or endpoint mode.
- Never mutate process environment variables or LiteLLM globals to obtain isolation.
- Never log or return keys, raw provider bodies, raw exception text, prompts, or complete request
  headers.

### Parameter contract

- `chat_parameter_rules()` remains the only enabling source.
- `chat_parameter_observations()` and any later discovery are evidence only and never enable a
  field.
- The plugin package, real seed, `max_tokens` rule, schema, observation, and final-wire proof land in
  one first green increment; a registered provider with zero conformance models is forbidden.
- P0 enables only `max_tokens` through `direct_rule`, reuses `MAX_TOKENS_SCHEMA`, and declares
  `cache_behavior="bypass"`. LiteLLM emits `max_tokens` for GPT-4.x/4o and
  `max_completion_tokens` for GPT-5/o-series; both wire shapes require tests.
- Do not override `validate_chat_parameter_combination()` in P0: tools and reasoning controls are
  disabled, so no enabled pair can trigger the Responses bridge.
- The P0 rule set is otherwise closed. Tools,
  structured output, reasoning controls, and broader parameter promotions are separate follow-ups.
- Every enabled field has a schema, projection, cache behavior, labelled evidence, and final-wire
  test through the installed transform.
- Unknown, disabled, malformed, or wrong-mode fields fail before credential access.

### API-key validation

Reuse the established OpenRouter two-stage validator shape through the existing provider-neutral
validation service and bounded validation transport:

1. Authenticate with the fixed-origin `GET https://api.openai.com/v1/models` endpoint.
2. Prove readiness with one minimal non-streaming Chat Completions request against an explicitly
   configured, live-verified low-cost validation model.

`ApiKeyValidationStage.AUTHENTICATION` and `.READINESS` are core-enforced: an authentication-only
`VALID` result is downgraded to `MISCONFIGURED` and cannot authorize persistence. The finite table
must cover all eight states: `VALID`, `INVALID`, `EXPIRED`, `NO_QUOTA`, `PERMISSION_DENIED`,
`RATE_LIMITED`, `UNAVAILABLE`, and `MISCONFIGURED`.

The second stage may consume quota and must be documented. Before implementation, define a finite
classification table keyed by exact HTTP status plus structured OpenAI `error.type` and
`error.code`, using only official or bounded live evidence. A status alone is not actionable;
unlisted tuples, ambiguous `429` responses, malformed payloads, and transport failures are
`unavailable`. Only a readiness-stage `valid` result authorizes persistence.

The implemented P0 evidence table is deliberately conservative:

- `(401, invalid_request_error, invalid_api_key)` is `invalid` at either stage, backed by a bounded
  synthetic-key fixture captured on 2026-08-17.
- The readiness-only OpenAI billing codes `credit_balance_exhausted`,
  `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`, and
  `organization_usage_limit_exceeded` are `no_quota` only with HTTP 429 and
  `error.type=insufficient_quota`.
- `expired`, `permission_denied`, and `rate_limited` remain explicit unpromoted states until an exact
  tuple has approved evidence. Candidate or status-only responses stay `unavailable`.
- Local unregistered validation configuration is `misconfigured`; malformed HTTP-200 success
  payloads are `unavailable`.

### Cache and accounting boundary

- P0 inherits the provider base's global `CacheBypass`; OpenAI requests perform no AIGateway global
  cache read or write.
- Support caching for OpenAI is a separate follow-up under the OME-787 projection-coverage scope,
  after endpoint selection and ambient-context isolation are stable.
- Keep LiteLLM's own cache disabled independently of the AIGateway global-cache bypass.
- P0 declares no OpenAI usage-accounting contribution, so the generic taxonomy resolves it to
  `UsageAccountingStrategy.unsupported()` and does not overwrite the provider-owned `client=`.
- Token, latency, completion-ID, attempt, and `DirectCost` normalization are deferred to a separate
  SDK-client accounting capability task. Do not add `usage_accounting.py` in OME-864.

## Scope

- Auto-discovered direct OpenAI provider package.
- API-key-only auth through existing generic routes and encrypted account-scoped storage.
- Curated direct OpenAI model seed; P0 dispatch is seed-only.
- Non-streaming Chat Completions dispatch through installed LiteLLM.
- Fixed official origin, TLS, credential isolation, ambient-context isolation, and sanitized errors.
- One provider-local `max_tokens` rule, observation, and final-wire proof.
- Two-stage API-key validation.
- Explicit AIGateway global-cache bypass for every OpenAI request.
- Provider discovery/model/provider route integration through existing generic code.
- Replacement of the obsolete `registry.get("openai") is None` test assertion with stronger
  Codex/OpenAI namespace ownership coverage.
- Deterministic unit, route, conformance, security, cache-bypass, and owner-gated live tests.

## Out of scope

- Codex OAuth changes or routing API keys through Codex.
- OpenRouter changes or OpenRouter model-seed changes.
- Hosted/shared OpenAI credentials.
- OpenAI Responses API and automatic Chat Completions-to-Responses bridging.
- Streaming/SSE.
- Arbitrary unlisted OpenAI model dispatch.
- AIGateway global-cache projection for OpenAI; that belongs to a to-be-filed OME-787 sub-issue.
- OpenAI usage-accounting instrumentation or a new SDK-client accounting capability.
- Function tools, structured output, reasoning controls, and parameter promotion beyond the minimal
  universally proven P0 subset.
- Realtime, audio, image, embedding, moderation, batch, fine-tuning, assistants, vector-store, and
  admin endpoints.
- Explicit client-selectable OpenAI organization/project headers.
- Runtime registration of the complete account model catalog.
- A direct OpenAI SDK transport replacing LiteLLM.
- New dependencies, database state, migrations, signals, billing tables, or pricing calculations.
- URL4 Cloud `url4.toml` mirroring unless separately requested after the direct seed is approved.

## Acceptance criteria

- `plugins/openai_provider/plugin.py` is discovered without a central loader or registry change.
- `GET /v1/providers` exposes `openai` with API-key auth after the plugin contributes models.
- `GET /v1/models` exposes approved `openai/<model>` rows with conservative parameter summaries.
- Every `openai/<model>` seed resolves to the OpenAI plugin; every `codex/<model>` seed continues to
  resolve to Codex.
- The Codex namespace regression keeps its original ownership guarantee while permitting the new
  direct OpenAI namespace.
- A valid account-scoped OpenAI key can be created, replaced, selected, and deleted through existing
  generic routes.
- Credential publication remains encrypted and transactional with no schema or migration change.
- Approved status/type/code tuples return the matching sanitized actionable states; every unlisted
  or ambiguous tuple, including ambiguous `429`, returns `unavailable`.
- API-key validation reaches readiness and documents that its minimal completion can consume quota.
- The approved seed and validation model are selected before source implementation; every seed is
  present in a live account catalog and passes an owner-gated real Chat Completions smoke.
- Final-wire tests prove the official host, `/v1/chat/completions`, exactly one stripped gateway
  prefix at the upstream wire while the prefixed ID reaches LiteLLM, the selected Bearer key,
  verified TLS, and no key in JSON.
- Poisoned caller controls, LiteLLM globals, OpenAI environment keys/bases, ambient organization and
  project values, custom headers, callbacks, and Responses bridge flags cannot alter the wire.
- `stream:true` fails before `_inject_credentials()` reads the credential secret; profile/connection
  target resolution and request preparation still occur first.
- The plugin package, production seed, `max_tokens` rule, schema, observation, bypass disposition,
  and final-wire proof land in one first green increment.
- Unknown or unsupported fields fail closed before credential access.
- OpenAI accounting is explicitly unsupported in P0, no shared accounting handler overwrites the
  provider-owned `AsyncOpenAI` client, and no provider accounting evidence is fabricated.
- Every OpenAI request reports AIGateway global-cache bypass and performs no global cache read or
  write.
- Profile API-key and API-key connection lifecycles both cover create, failed-validation no-write,
  failed replacement preserving prior state, account isolation, selection, and deletion.
- Raw provider error bodies, exception messages, prompts, keys, and headers do not reach responses,
  logs, persisted errors, or cache rows.
- Existing Anthropic, Antigravity, Codex, Gemini, Hugging Face, Ollama, and OpenRouter behavior
  remains unchanged.
- Focused tests and the complete AIGateway quality gate pass.
- The opt-in live test remains skipped unless explicitly enabled with a real OpenAI key.

## Delivery requirements

- Use `OME-864` for the branch, work ledger, commit body, and PR references.
- Before source edits, load the project-local Python SDLC specialization and create the required
  `docs/work/YYYY-MM-DD-OME-864-<description>.md` ledger from the repository template.
- Use TDD with failing tests first.
- Preserve prior tests. The one existing Codex namespace test contains a now-impossible literal
  absence assertion; changing it requires an explicit append-only exception while retaining and
  strengthening the original Codex ownership behavior.
- Keep new hand-maintained Python files within the SDLC's 450-line convention and split by cohesive
  responsibility rather than by line count alone. Automated gates additionally enforce complexity,
  statement, branch, return, formatting, typing, no-Enterprise, test, and 80% coverage constraints.
- Do not stage, commit, push, or create a PR without separate authorization.
