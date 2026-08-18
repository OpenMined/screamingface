# Implementation plan: direct OpenAI Platform API-key provider

## 1. Status and authority

This is the implementation plan for P0 issue
[OME-864](https://linear.app/openmined/issue/OME-864/add-direct-openai-platform-api-key-provider-to-aigateway).
Implementation and owner-authorized live verification completed on 2026-08-18. Per owner ruling,
Linear remained unchanged during this increment.

The completed bounded live pass covers readiness, all fourteen concrete seeds, and one end-to-end
AIGateway route request. Secret material and account identity are not recorded in this plan.

`docs/spec/2026-08-17-OME-864-direct-openai-provider.md` owns scope and acceptance when planning
artifacts differ. Per the owner ruling, Linear OME-864 remains unchanged for now; its broader wording
does not expand this reviewed implementation increment.

Planning assumptions to confirm before implementation:

1. The P0 increment is API-key-only and uses the existing `/v1/chat/completions` public contract.
2. The P0 increment is non-streaming.
3. Every P0 call is proven to remain on OpenAI Chat Completions; Responses API is separate.
4. Direct model IDs use `openai/<model>` and never replace `codex/<model>`.
5. The owner-approved seed contains fourteen locked-runtime chat models; live account evidence
   is required before release, not before source implementation.
6. P0 dispatch is restricted to the registered seed so model listing, detailed contracts, and chat
   enforcement describe the same set. Unlisted models are a follow-up.
7. OpenAI inherits the standard AIGateway global `CacheBypass`; support caching for OpenAI is a
   separate, not-yet-filed projection task under OME-787 scope.
8. No explicit organization/project selector is added in P0.
9. No Tortoise model, migration, signal, new dependency, hosted credential, or URL4 mirror is added.

## 2. Architecture

### 2.1 Provider flow

```text
POST /v1/chat/completions model=openai/<model>
  -> provider-neutral strip_dispatch_controls
  -> registry.get("openai")
  -> plugin.strip_provider_dispatch_controls
  -> global cache plan -> global_cache_projection bypass (no read/write)
  -> account profile/connection target resolution (may raise; no secret read)
  -> OpenAI API-key max_tokens rule projection
  -> OpenAI request preparation
  -> non-streaming gate
  -> account-scoped ApiKeyStrategy
  -> _inject_credentials reads the selected secret
  -> OpenAIProviderPlugin.chat_completion()
  -> request-local AsyncOpenAI(key, official base, Omit headers)
  -> LiteLLM 1.95.0 OpenAI Chat Completions transform
  -> https://api.openai.com/v1/chat/completions
```

No central provider switch is introduced. The first model-ID segment remains the only provider
selector.

### 2.2 Credential flow

```text
generic API-key route
  -> OpenAIApiKeyValidator authentication stage
  -> OpenAIApiKeyValidator readiness stage
  -> profile path: ProfileIndexStore upsert + ApiKeyStrategy.persist_credentials
     OR connection path: OAuthConnectionStore create/reactivate + ApiKeyStrategy.persist_credentials
  -> each path's existing Tortoise transaction and lock ordering
  -> ORMStore
  -> SecretStoreMixin encryption
  -> credential_blobs
```

Both surfaces store into the account-scoped credential slot selected by the generic route. The
plugin supplies only its service namespace and Bearer-header builder. Failed validation happens
before either transaction; failed replacement must preserve the prior key and metadata.

### 2.3 Plugin responsibilities

`OpenAIProviderPlugin` owns:

- settings and model seeds;
- API-key capability, strategy, and validator;
- model-ID validation while preserving one `openai/` prefix into LiteLLM;
- the `max_tokens` rule and observation;
- fixed-origin and Chat Completions request preparation;
- the request-local `AsyncOpenAI` client, ambient header suppression, and Responses bridge skip;
- explicit global-cache bypass inherited from the provider base;
- safe 401 credential invalidation policy;
- final LiteLLM dispatch controls.

Core continues to own:

- plugin discovery and registry uniqueness;
- caller authentication and account selection;
- profile/connection persistence;
- provider-neutral control stripping;
- fail-closed parameter classification;
- cache orchestration;
- credential injection ordering;
- overload/backpressure policy;
- error rendering and profile-state mutation;
- accounting session lifecycle, which resolves OpenAI to unsupported in P0.

### 2.4 Tortoise boundary

Tortoise ORM `1.1.7` is already initialized with the existing auth, credential, OAuth, cache, and
secret model packages. This task changes no model state, so migration autodetection must have no
operation to generate.

Do not:

- add `openai_provider.models` to `TORTOISE_CONFIG`;
- create an OpenAI credential table;
- add fields to `CredentialBlob`, `OAuthConnection`, `Profile`, or `Account`;
- call `generate_schemas()` in production;
- introduce Aerich;
- use Tortoise signals for provider behavior.

The explicit service methods and existing transaction remain the observable write path.

## 3. Intended files

### 3.1 New production files

```text
apps/aigateway/src/aigateway/plugins/openai_provider/__init__.py
apps/aigateway/src/aigateway/plugins/openai_provider/settings.py
apps/aigateway/src/aigateway/plugins/openai_provider/parameters.py
apps/aigateway/src/aigateway/plugins/openai_provider/api_key_validation.py
apps/aigateway/src/aigateway/plugins/openai_provider/plugin.py
```

Keep `plugin.py` as composition, not a policy dump. Do not create `global_cache.py`; OME-864 always
uses the inherited bypass and the later OpenAI caching task owns projection code.

### 3.2 Existing production files expected to remain unchanged

```text
apps/aigateway/src/aigateway/core/loader.py
apps/aigateway/src/aigateway/core/registry.py
apps/aigateway/src/aigateway/core/api_key_strategy.py
apps/aigateway/src/aigateway/core/credential_blob/
apps/aigateway/src/aigateway/core/oauth/models/
apps/aigateway/src/aigateway/db.py
apps/aigateway/src/aigateway/routes/auth.py
apps/aigateway/src/aigateway/routes/oauth_connections.py
apps/aigateway/src/aigateway/routes/chat.py
apps/aigateway/src/aigateway/routes/models.py
apps/aigateway/src/aigateway/routes/providers.py
apps/aigateway/src/aigateway/migrations/
apps/aigateway/pyproject.toml
apps/aigateway/uv.lock
```

If implementation requires changing one of these, stop and show why the existing generic port is
insufficient before widening scope.

### 3.3 Tests

Prefer new focused files:

```text
apps/aigateway/tests/unit/openai/test_settings.py
apps/aigateway/tests/unit/openai/test_provider.py
apps/aigateway/tests/unit/openai/test_api_key_validation.py
apps/aigateway/tests/unit/openai/test_parameters.py
apps/aigateway/tests/unit/openai/test_dispatch_wire.py
apps/aigateway/tests/unit/openai/test_security.py
apps/aigateway/tests/unit/openai/test_cache_bypass.py
apps/aigateway/tests/live/test_openai_live.py
```

One existing file necessarily changes:

```text
apps/aigateway/tests/unit/core/test_codex_namespace_guard.py
```

Its literal `registry.get("openai") is None` assertion conflicts with the new feature. Retain all
Codex-prefix and owner-resolution assertions, replace only the obsolete absence claim, and add the
stronger invariant that overlapping GPT family names remain independently owned by their canonical
prefixes. Record the required append-only exception in the future work ledger before editing.

Generic conformance files should not need provider-specific edits; their discovery sweep should
pick up the new plugin automatically.

## 4. Design decisions

### D1. A normal auto-discovered provider

Use `aigateway.plugins.openai_provider` and export `PLUGIN = OpenAIProviderPlugin()`. The package name
already satisfies the loader's `*_provider` rule. No manifest, entry point, or central inventory is
added.

### D2. Separate namespaces, even for the same model family

The owning plugin is encoded in the canonical ID:

```text
codex/gpt-5.x   -> CodexProviderPlugin -> ChatGPT subscription/OAuth endpoint
openai/gpt-5.x  -> OpenAIProviderPlugin -> OpenAI Platform/API-key endpoint
```

Do not infer provider ownership from a bare model family name or from LiteLLM metadata. Never rename
Codex entries into the OpenAI namespace.

### D3. Existing API-key persistence only

Implement:

```python
supports_api_key() -> True
api_key_strategy_for(...) -> ApiKeyStrategy(...)
api_key_validator() -> OpenAIApiKeyValidator(...)
```

The service locator must include the account-scoped credential name passed by the generic route.
Use `account="default"` only because account isolation is already embedded in that service string,
matching the existing provider strategy pattern.

For API-key validation, only an approved authentication evidence tuple containing HTTP 401 plus the
matching structured OpenAI type/code proves the submitted key invalid. The separate dispatch-error
hook receives only HTTP status, so it follows the existing provider contract: dispatch 401 may mark
only the selected stored target errored; permission, quota, rate, timeout, and 5xx do not.

### D4. Curated seed-only dispatch

`OpenAIPluginSettings` uses `AIGW_OPENAI_` and contains:

```text
default_models: list[str]
validation_model: str
```

The approved values are:

```text
default_models:
  - openai/gpt-5.6-sol
  - openai/gpt-5.6-terra
  - openai/gpt-5.6-luna
  - openai/gpt-5.5
  - openai/gpt-5.1
  - openai/gpt-5
  - openai/gpt-5-mini
  - openai/gpt-5-nano
  - openai/gpt-4.1
  - openai/gpt-4.1-mini
  - openai/gpt-4o
  - openai/gpt-4o-mini
  - openai/o3
  - openai/o4-mini
validation_model: openai/gpt-5-nano
```

The original offline seed used the official `gpt-5.6` family alias. Owner-authorized live evidence
showed that Chat Completions resolves that alias to `gpt-5.6-sol`, while `/v1/models` publishes the
three concrete `gpt-5.6-{sol,terra,luna}` IDs and not the alias. The owner therefore replaced the
alias with all three concrete variants so the gateway catalog exposes the actual capability/cost
choices without a duplicate default-to-Sol row.

Before release:

1. Obtain owner authorization for one bounded Models API query and one minimal readiness completion.
2. Intersect the requested product lineup with the selected account's `GET /v1/models` result.
3. Prove each seed against the intended Chat Completions endpoint.
4. Exclude non-chat, Responses-only, embedding, image, audio, moderation, fine-tuning, and admin IDs.
5. Record the verification date and account-independent model IDs without storing account data.

Validate configured gateway IDs as one `openai/` prefix followed by a bounded ASCII model token.
Reject empty IDs, additional path segments, URL schemes, query/fragment syntax, controls,
whitespace, percent escapes, and backslashes. Reject syntactically valid but unregistered IDs in P0
so `/v1/models`, `/v1/model-parameters`, conformance, and dispatch expose one coherent model set.
Implement this as a settings `@field_validator` over `default_models` and `validation_model`; there
is no plugin-level `validate_model_id` hook.

### D5. Two-stage validation

Implement `OpenAIApiKeyValidator` by adapting the established OpenRouter validator shape with the
existing `ValidationHttpSession`:

- Authentication: fixed-origin `GET /v1/models`, expecting an OpenAI list object.
- Readiness: fixed-origin `POST /v1/chat/completions`, non-streaming, minimal input, and the configured
  validation model.

Use gateway-authored results only. Do not return upstream bodies/messages. Before implementation,
record a finite classification table whose keys combine HTTP status with the exact structured OpenAI
`error.type` and `error.code`; admit only tuples proven by official documentation or bounded live
negative fixtures. A status alone is never actionable. Unlisted tuples, unknown 4xx/5xx, malformed
payloads, redirects, oversized bodies, compression violations, and transport exceptions remain
`unavailable`. In particular, an ambiguous `429` is not automatically `rate_limited` or `no_quota`.

Name both core stages, `ApiKeyValidationStage.AUTHENTICATION` and `.READINESS`, and account for all
eight states: `VALID`, `INVALID`, `EXPIRED`, `NO_QUOTA`, `PERMISSION_DENIED`, `RATE_LIMITED`,
`UNAVAILABLE`, and `MISCONFIGURED`. `ApiKeyValidationService` downgrades an authentication-only
`VALID` result to `MISCONFIGURED`, so readiness is a core-enforced persistence invariant.

The readiness request may cost money. The route/API documentation and live-test instructions must
state that before callers persist a key.

### D6. Chat Completions only

The provider's contract is endpoint-specific, not merely response-shape compatible.

The locked runtime has four bridge triggers. P0 handles them without a combination override:

- set private pinned kwarg `_skip_responses_api_bridge=True` request-locally, defeating the global
  `route_all_chat_openai_to_responses` flag without mutating it;
- reject IDs with the extra `responses/` segment in settings validation;
- assert every approved seed resolves to LiteLLM `mode="chat"`; a Responses-only seed fails closed;
- enable neither tools nor reasoning controls, making the GPT-5 combination trigger unreachable.

There is no runtime final-URL policy seam after LiteLLM preparation, so do not promise runtime URL
interception. Treat the full no-network `acompletion()` test as the endpoint contract for locked
LiteLLM `1.95.0`; dependency upgrades must keep the private skip kwarg and final-wire contract green.

Return `False` from `supports_chat_streaming()`. The route then rejects `stream:true` before
`_inject_credentials()`.

### D7. Fixed-origin and ambient-context isolation

`prepare_chat_body()` and `chat_completion()` must collectively enforce:

- official `api_base=https://api.openai.com/v1`;
- selected request-local `api_key` injected only after preparation;
- verified TLS;
- a provider-owned HTTP client with `trust_env=False` and redirects disabled;
- `caching=False` and no-store cache controls;
- configured `num_retries=0` and `max_retries=0`;
- request-local `_skip_responses_api_bridge=True`;
- no caller or global fallbacks, alternate model lists, callbacks, mock response, custom logger, or
  provider-mode controls;
- no key in JSON, metadata, logs, callbacks, or exception text.

RED final-wire tests poison at least:

```text
body.api_key
body.api_base / body.base_url
body.headers / body.extra_headers
body.fallbacks / body.model_list
body.callbacks / body.success_callback / body.failure_callback
body.custom_llm_provider / body.azure / body.text_completion
litellm.api_key / litellm.openai_key / litellm.api_base / litellm.headers
litellm.proxy_auth / litellm.model_fallbacks / litellm.drop_params
litellm.additional_drop_params / litellm.callbacks / litellm.pre_call_rules / litellm.post_call_rules
OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_API_BASE
OPENAI_ORGANIZATION / OPENAI_ORG_ID / OPENAI_PROJECT_ID / OPENAI_CUSTOM_HEADERS
route_all_chat_openai_to_responses
```

The installed runtime forwards ambient organization and project headers when it owns client
construction. P0 instead builds a request-local `AsyncOpenAI` inside `chat_completion()` after the
gateway has injected the selected key. Construct it with the selected key, official base,
`max_retries=0`, and `default_headers` mapping `OpenAI-Organization` and `OpenAI-Project` to OpenAI
Python `Omit()` sentinels; pass it through LiteLLM's `client=` seam and close it after the
non-streaming response. The pinned final-wire contract preserves the selected Bearer key and Chat
Completions URL while suppressing both headers even when LiteLLM assigns `client.organization`.
The SDK client owns an explicitly closed HTTP client with verified TLS, `trust_env=False`, and
redirects disabled. Non-empty LiteLLM proxy auth, global headers, fallbacks, callbacks, rules, or
drop-parameter state fail closed before SDK client construction.

Do not pass `organization=None` or `project=None` as the fix: `None` means unset and causes OpenAI
Python to read `OPENAI_ORG_ID` / `OPENAI_PROJECT_ID`. Refuse dispatch when
`OPENAI_CUSTOM_HEADERS` is non-empty; arbitrary ambient header names are not covered by the two fixed
sentinels. Declaring accounting unsupported prevents the taxonomy session from replacing this client
with `AccountingAsyncHTTPHandler`. P0 accepts a fresh, explicitly closed SDK client per dispatch
rather than adding credential-keyed client pooling or core lifecycle state. Use the OpenAI Python
runtime already required by locked LiteLLM; do not add a project dependency or replace LiteLLM as
the dispatch layer.

### D8. Provider-local parameter contract

P0 enables exactly `max_tokens` as the smallest useful universal Chat Completions subset. Reuse
`MAX_TOKENS_SCHEMA` and construct `direct_rule("max_tokens", auth_modes=("api_key",),
schema=MAX_TOKENS_SCHEMA, cache_behavior="bypass", ...)`. A keyed rule is forbidden while OpenAI
inherits `CacheBypass`; OME-787 requires the projection to land before any later promotion to
`keyed`.

For each rule:

- define a bounded `ParameterSchema`;
- declare `applicable_auth_modes=("api_key",)`;
- declare the direct projection through `direct_rule`;
- declare `cache_behavior="bypass"`;
- add a labelled installed-transform observation;
- prove the exact final OpenAI JSON field;
- prove unsupported families/modes remain disabled;
- prove both family wire shapes: `max_tokens` for GPT-4.x/4o and `max_completion_tokens` for
  GPT-5/o-series.

Tools, tool choice, structured output, reasoning controls, and model-family-specific promotions are
out of scope. Do not override `validate_chat_parameter_combination()` because no enabled P0 pair has
a cross-field constraint. Stop sequences and broader sampling controls are follow-ups. Dynamic
Models API evidence never enables a parameter.

### D9. Global-cache bypass

P0 inherits the provider base's standard `CacheBypass`. Every OpenAI request skips AIGateway global
cache lookup and storage, so a cache hit cannot bypass ambient-context, endpoint-mode, credential,
or dispatch guards. Do not add an OpenAI projection, adapter revision, or OpenAI cache-key semantics
in OME-864. A to-be-filed "Support caching for OpenAI" sub-issue under OME-787 defines those after
endpoint selection and ambient isolation are stable.

### D10. Accounting unsupported in P0

Do not implement `usage_accounting_strategy()` or `usage_accounting.py`. The taxonomy resolves a
missing duck-typed contribution to exact `UsageAccountingStrategy.unsupported()`, creates no
collector, and does not inject its shared `AccountingAsyncHTTPHandler` into `body["client"]`.

Native OpenAI dispatch expects an `AsyncOpenAI` SDK client and calls `.chat.completions`; the current
accounting handler is a LiteLLM `AsyncHTTPHandler` with no `.chat`. The experimental ambient
`EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER` route is forbidden. Token, attempt, latency, completion
ID, and direct-cost normalization all move to a separate SDK-client accounting capability task.

### D11. Sanitized errors

Reuse the shared route taxonomy. The plugin adds only provider-specific facts needed to classify
credential validity and sanitize failures.

- API-key validation requires an approved invalid-key status/type/code tuple. On later chat dispatch,
  HTTP 401 may mark only the selected OpenAI profile/connection errored because the existing core
  invalidation hook receives status only.
- 403, quota, rate limit, timeout, and 5xx do not invalidate the key.
- Raw OpenAI error bodies and SDK/LiteLLM exception messages never reach client detail or persisted
  connection errors.
- Safe status and bounded `Retry-After` may survive through the existing gateway contract.
- Conversion failures and unknown exceptions become generic provider errors.
- The request-local OpenAI SDK client and LiteLLM dispatch both receive configured retries of zero.

## 5. TDD implementation sequence

### Phase 0 - Authorize and frame

- Obtain approval for the canonical OME-864 spec and this plan.
- Do not modify Linear OME-864 during this increment. File the separate OpenAI cache-projection
  follow-up under OME-787 later; it is not a Phase-1 prerequisite.
- Record that implementation is offline and live release remains blocked until an approved key,
  bounded validation spend, and dated Chat Completions evidence are available; never store the key
  or account-sensitive evidence in planning artifacts.
- Build the finite validation classification table from exact `status + error.type + error.code`
  evidence; every unproven tuple maps to `unavailable`.
- Fix the minimum rule as `max_tokens` using `MAX_TOKENS_SCHEMA`, `direct_rule`, API-key applicability,
  and `cache_behavior="bypass"`; retain both GPT-4.x/4o and GPT-5/o-series wire assertions.
- Confirm OME-864 remains assigned to Dmitry and move it to `In Progress` when implementation starts.
- Create an `OME-864-<description>` branch from fresh `origin/main` in an isolated worktree because the
  shared checkout is dirty.
- Load the project-local Python SDLC specialization.
- Create the required `docs/work/YYYY-MM-DD-OME-864-<description>.md` ledger from the repository
  template.
- Confirm `docs/tasks/2026-08-17-OME-864-direct-openai-provider.md` reflects the current Linear
  status; Linear remains authoritative.
- Record the Codex-test append-only exception before changing that test. Run the append-only gate
  normally first and confirm the exact flagged list contains only
  `tests/unit/core/test_codex_namespace_guard.py`; only then rerun with the run-wide skip and record
  both outputs in the ledger.
- Confirm installed dependency versions and run the baseline AIGateway gate.
- Confirm the approved seed is visible before release.

### Phase 1 - RED: discovery, namespace, and credentials

Add failing tests proving:

- `openai_provider` is discovered through the existing loader;
- the plugin contributes API-key auth and no OAuth config;
- approved seeds canonicalize under `openai/`;
- syntactically valid but unregistered OpenAI models fail before credential access;
- Codex models remain under and resolve to `codex/`;
- overlapping bare GPT names are independently owned by their prefixes;
- generic provider/model routes surface OpenAI without central branches;
- a duplicate `custom_llm_provider="openai"` registration fails startup;
- `ApiKeyStrategy` uses the account-scoped OpenAI service locator;
- every seed lands in the same first green increment as the `max_tokens` API-key rule,
  `MAX_TOKENS_SCHEMA`, labelled observation, explicit bypass disposition, and focused
  installed-transform final-wire proof;
- no model, migration, or dependency change is required.

Implement the minimal settings, plugin, real seed, rule, and observation together. There is no green
intermediate state with `openai_provider/plugin.py` present and zero conformance models.

### Phase 2 - RED: API-key validation

Add failing deterministic transport tests for:

- fixed-origin Models authentication;
- fixed-origin minimal Chat Completions readiness;
- valid only after readiness;
- all eight validation states and both `ApiKeyValidationStage` values;
- authentication-only `VALID` is downgraded to `MISCONFIGURED` by the core service;
- every approved `status + error.type + error.code` tuple and conservative `unavailable` fallback;
- ambiguous `429`, malformed, oversized, redirect, compressed, timeout, and cancellation behavior;
- no raw body/key reflection;
- configurable validation model must exist in the reviewed seed and stay on Chat Completions.

Implement `OpenAIApiKeyValidator` and integrate it through the generic hook.

### Phase 3 - RED: owned SDK client, isolation, and endpoint mode

Add failing real-LiteLLM/no-network wire tests for:

- first, a full no-network `acompletion()` proves the supplied `AsyncOpenAI` survives to the wire;
- exactly one `openai/` prefix reaches LiteLLM unchanged and LiteLLM emits one bare upstream model;
- official host and `/v1/chat/completions` path;
- selected account Bearer key wins every key fallback;
- key absent from JSON and logs;
- caller routing/header/callback/retry/cache/mock controls cannot reach the wire;
- `OPENAI_ORGANIZATION`, `OPENAI_ORG_ID`, and `OPENAI_PROJECT_ID` cannot emit organization/project
  headers because the client carries `Omit()` sentinels;
- `organization=None` / `project=None` is covered as an explicit negative test;
- non-empty `OPENAI_CUSTOM_HEADERS` fails before the selected key is sent;
- `_skip_responses_api_bridge=True` defeats a true process-global Responses flag;
- every seed remains LiteLLM `mode="chat"`, and `responses/` IDs are rejected;
- TLS verification and zero configured LiteLLM/OpenAI SDK retries;
- the request-local client is closed after dispatch;
- `stream:true` fails before `_inject_credentials()` reads the credential secret.

Implement the smallest request preparation and dispatch boundary that satisfies these tests. Do not
add shared client lifecycle state, accounting handler injection, or process-global mutation.

### Phase 4 - RED: minimum parameter-contract hardening

For the one Phase-0-approved minimum rule, complete failing tests in this order:

1. schema admission and rejection;
2. API-key auth applicability;
3. observation/evidence composition;
4. conservative `/v1/models` summary;
5. detailed contract shape;
6. exact final-wire JSON;
7. cache classification;
8. both family-specific final-wire names for the one caller path.

Do not add another parameter family, generic passthrough, tools, structured output, reasoning, or a
field enabled only by discovery. Do not override `validate_chat_parameter_combination()`; those are
sequential follow-up promotions.

### Phase 5 - RED: cache and accounting boundaries

Add failing tests proving:

- every OpenAI request returns the standard provider projection `CacheBypass`;
- OpenAI requests perform no AIGateway global cache read or write even when cache is enabled;
- ambient-context and Responses guards cannot be skipped through a pre-existing OpenAI cache row;
- OpenAI resolves to `UsageAccountingStrategy.unsupported()`;
- no taxonomy accounting handler overwrites the provider-owned `AsyncOpenAI` client;
- unsupported accounting emits no fabricated token, attempt, latency, ID, or cost evidence.

Do not add OpenAI cache projection or accounting mapper code.

### Phase 6 - RED: route and lifecycle integration

Add route-level tests covering:

- provider and model listing;
- profile API-key create, failed-validation no-write, successful replacement, failed replacement
  preserving the old key, select, account isolation, and delete through `upsert_api_key_profile()`;
- API-key connection create, failed-validation no-write, successful replacement, failed replacement
  preserving the old key, select, account isolation, and delete through
  `create_api_key_connection()` / `set_connection_api_key()`;
- unknown/unsupported params fail before key read;
- 401 invalidates only the selected target;
- non-auth failures preserve the target;
- safe errors and no raw markers;
- existing providers remain unchanged.

No Tortoise schema work occurs. Run the existing clean-migration smoke only as a regression check,
not to generate a migration.

### Phase 7 - Owner-gated live verification

With explicit authorization and a bounded real key:

- call `GET /v1/models` and record only approved model IDs and date;
- verify the validation model with the minimum readiness request;
- run one direct non-streaming completion through the AIGateway route;
- verify the selected model, endpoint family, response shape, and sanitized logs;
- do not record the API key, prompt, organization/project identity, raw headers, or raw provider
  error body;
- leave the live test marked `live` and skipped by default.

If the approved key, budget, seed, or validation model is withdrawn, stop implementation and return
to owner review; do not substitute guessed defaults.

### Phase 8 - Gates and review

- Run focused OpenAI, Codex namespace, conformance, both credential surfaces, SDK-client isolation,
  and cache-bypass tests.
- Run the canonical AIGateway gate from the repository root.
- Run the no-Enterprise import guard.
- Review the actual diff for accidental core/provider branches, schema/dependency changes, secret
  exposure, Responses support, streaming, and URL4 scope.
- Confirm every new hand-maintained source file follows the SDLC 450-line convention and the
  automated complexity, statement, branch, and return limits.
- Confirm the only edited pre-existing test is the documented stronger Codex namespace guard.
- Update the work ledger with checks actually run and residual release blockers.
- Do not stage, commit, push, or create a PR without separate authorization.

## 6. Test matrix

| Area | Required proof |
|---|---|
| Discovery | Normal `*_provider` loading; no loader/registry branch |
| Namespace | `openai/*` owns direct API; `codex/*` remains OAuth subscription |
| Auth | API key only; profile and API-key connection lifecycles both preserve atomic isolation |
| Tortoise | Existing models/transaction; no model registration or migration change |
| Validation | Core-enforced authentication + readiness stages; all eight states |
| Models | Curated live-verified seed only; unregistered IDs rejected before credential access |
| Endpoint | Pinned official origin; locked LiteLLM final-wire proof for `/v1/chat/completions` |
| Responses | Request-local private skip defeats global flag; seed modes and IDs exclude other triggers |
| Streaming | Rejected before `_inject_credentials()` reads the credential secret |
| Isolation | Owned `AsyncOpenAI` suppresses org/project; ambient custom headers fail closed |
| Parameters | `max_tokens` + schema + bypass rule + observation land with the real seed |
| Cache | Standard `CacheBypass` for every OpenAI request; no global read or write |
| Accounting | Unsupported; no shared handler injection or fabricated evidence |
| Errors | Validation uses approved tuples; dispatch 401 alone may invalidate only the selected target |
| Regression | Existing providers and full AIGateway gates remain green |
| Live | Owner-gated, bounded, skipped by default |

## 7. Stop conditions

Return to owner review instead of broadening scope if any of these occurs:

- live verification requires unbounded spend or storing sensitive account evidence;
- a seed or required parameter can only use Responses API;
- the locked LiteLLM version stops honoring `_skip_responses_api_bridge=True` or the supplied
  `AsyncOpenAI` client;
- API-key publication requires a new model, field, migration, or credential table;
- plugin loading requires a central OpenAI branch;
- implementation requires adding a new package dependency or replacing LiteLLM dispatch; using the
  already-installed OpenAI SDK required by locked LiteLLM for request-local client construction is
  expected;
- streaming becomes necessary for P0 acceptance;
- URL4 model mirroring or hosted/shared credentials are pulled into the task;
- a prior test must be deleted or weakened beyond the documented Codex guard repointing.

## 8. Definition of done

- A normally auto-discovered `openai` provider supports direct account-scoped OpenAI Platform API
  keys under `openai/<model>`.
- Codex remains OAuth-only and retains exclusive ownership of `codex/<model>`.
- The generic encrypted API-key lifecycle is reused without schema, migration, signal, route, or
  dependency changes.
- Every allowed P0 dispatch is non-streaming and proven to reach only the official Chat Completions
  endpoint.
- Caller and ambient OpenAI routing/auth context cannot alter the selected account request.
- `max_tokens` is the only enabled P0 parameter, uses `MAX_TOKENS_SCHEMA`, is cache-bypassed, and is
  evidenced and final-wire proven under both family-specific upstream field names.
- Validation authenticates and proves readiness with documented quota impact.
- Both generic API-key persistence surfaces prove create, failed-validation no-write, replacement
  preservation on failure, account isolation, selection, and deletion.
- Every OpenAI request uses the standard global `CacheBypass`; OpenAI cache projection is absent.
- OpenAI usage accounting is unsupported in P0; no shared accounting handler replaces the
  request-local SDK client and no accounting evidence is fabricated.
- Provider errors and logs expose no key, prompt, raw body, or raw exception text.
- The approved model seed has dated direct-OpenAI live evidence, or release remains explicitly
  blocked pending that evidence.
- Existing provider behavior remains green.
- The documented Codex test exception strengthens rather than removes namespace ownership coverage.
- Focused tests and the complete AIGateway gate pass.
- Work ledger and branch/commit/PR references use `OME-864`.
