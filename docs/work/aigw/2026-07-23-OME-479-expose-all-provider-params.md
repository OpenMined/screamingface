---
ticket: OME-479
stack: aigateway
status: done
started: 2026-07-23
finished: 2026-07-30
---

# OME-479 - Effective model capabilities and detailed parameter discovery

## Intent

Make the approved all-model-provider-api-params implementation plan real: expose an
effective, machine-readable capability summary on every `/v1/models` row, add an optional
profile-bound detailed `/v1/model-parameters` contract, and make ordinary model/body parameters
cheap to enable via one provider-local projection rule — while dispatch fails closed on unknown or
disabled parameters. Provider observation (raw support) stays separate from gateway enablement
(what the gateway validates + forwards); only `gateway.status == "enabled"` authorizes submission.

## Planned changes

- **Phase 1** `core/chat_parameters.py`: frozen Pydantic v2 value types + rule algebra
  (`ParameterProjectionRule`, `ProviderParameterObservation`, `ParameterContractEntry`,
  `ModelParameterContract`, `ToolCapability`, `TransportCapability`), deterministic ordering,
  conservative auth-mode intersection for the profile-independent summary.
- **Phase 2** canonical model identity (`ModelEntry.canonical_id(provider)` helper) + extend
  `routes/models.py` with `supported_parameters`, `supported_tools`,
  `unsupported_parameter_behavior="reject"`, `parameter_contract_url`. Seed provider-local rule
  sets that represent proven current behavior.
- **Phase 3** `routes/model_parameters.py`: local (no-network) profile-bound detailed contract;
  `Cache-Control: private, no-store`, `Vary: Authorization, X-Profile`, opaque
  `context.revision`/`contract_id`.
- **Phase 4** fail-closed classification + `provider_params` wrapper projection in the chat
  pipeline (`core/request_hardening.py` classify + `routes/chat.py`), one P0 promotion
  (`provider_params.top_k` for OpenRouter) with final-transform + cache-isolation proof.
- **Phases 5-9** bounded public discovery transport + per-provider observation overlays
  (OpenRouter, Hugging Face P0; Anthropic, Gemini P1) — additive; do not change the locked
  contract; a newly observed field stays `disabled` until a local rule exists.
- **Phase 10** registry conformance suite + final review.
- New focused test files under `tests/unit/core/`, `tests/unit/`, and per-provider suites
  (append-only; no prior assertion weakened).

## Test plan

- RED-first per phase (invalid/duplicate paths, deterministic ordering, fail-closed enums,
  summary intersection, canonical-id resolution + no cross-provider collision, private/no-store
  headers, opaque revisions, unknown/disabled/nested-alias/duplicate-channel rejection before
  credential injection, wrapper full-consumption, cache keyed two-value isolation vs bypass).
- Full non-live suite + `run_gates.py aigateway` (ruff, format, pyright, enterprise guard,
  pytest cov>=80) green at P0 checkpoint and completion. Baseline before work: 1298 passed,
  40 skipped.

## Acceptance

- Every `/v1/models` `id` is canonical, provider-prefixed, resolves to its plugin, dispatchable
  unchanged; rows carry deterministic sorted summary arrays + literal `reject` + relative detail URL.
- Inline `supported_parameters` == exactly the enabled detailed entries; one rule source drives
  list, detail, and dispatch (removing a rule updates all three).
- Unknown/disabled client parameters fail with HTTP 400 before credential access + dispatch.
- Every enabled parameter declares schema, projection, auth applicability, cache behavior; each has
  final-transform (or captured HTTP body) proof + cache keyed/bypass proof.
- Streaming reported as separate transport; Codex never classified as OpenAI.
- No new dependency, Tortoise model, migration, durable parameter state, or credentialed discovery.
- Existing provider/hardening/cache/error/credential tests remain green.

## Outcome (fill at the end - required before COMMIT)

### Progress log (per-phase; final Outcome finalized at unit completion)

**Phase 1 — contract value types + rule algebra — DONE.**
- Files: `src/aigateway/core/chat_parameters.py` (new); `tests/unit/core/test_chat_parameter_contract.py` (new, 43 tests).
- Frozen Pydantic v2 value objects (`ParameterProjectionRule`, `ProviderParameterObservation`,
  `ParameterContractEntry`, `ToolCapability`, `TransportCapability`) + pure algebra (`normalize_rules`,
  `compose_contract_entries`, `inline_supported_parameters`, `supported_tool_types`). Hashable via
  tuple fields; `schema` aliased to attr `parameter_schema` to avoid shadowing `BaseModel.schema()`.

**Phase 2 — canonical IDs + inline `/v1/models` summary — DONE.**
- Files: `src/aigateway/core/model_capabilities.py` (new — `canonical_model_id` + summary projection);
  `src/aigateway/routes/models.py` (modified — inline summary fields);
  `tests/unit/core/test_model_capabilities.py` (new, 17 tests);
  `tests/unit/core/test_models_route_contract.py` (new — route summary contract).
- Every row carries `supported_parameters`, `supported_tools`, `unsupported_parameter_behavior="reject"`,
  `parameter_contract_url`, and a canonical provider-prefixed `id`. Summary uses the conservative
  auth-mode intersection (path shown iff `available_auth_modes ⊆ rule.applicable_auth_modes`).

**Phase 3 — local profile-bound detailed `/v1/model-parameters` — DONE.**
- Files: `src/aigateway/core/model_parameter_contract.py` (new — pure composer + opaque digests);
  `src/aigateway/routes/model_parameters.py` (new — GET route);
  `src/aigateway/core/plugin_base.py` (modified — added `chat_parameter_observations` +
  `chat_transport_capabilities` hooks, both default `()`);
  `src/aigateway/routes/chat_credentials.py` (modified — extracted `auth_mode_for_target`, chat path
  delegates to it); `src/aigateway/core/chat_parameters.py` (added `ToolCapability.to_dict()`);
  `src/aigateway/main.py` (modified — registered the router);
  `tests/unit/core/test_model_parameter_contract.py` (new, 9 pure tests);
  `tests/unit/test_model_parameters_route.py` (new, 8 route tests).
- Locked v1 envelope; `Cache-Control: private, no-store`; `Vary: Authorization, X-Profile`. Auth mode
  derived from stored profile/connection (never caller-declared). Opaque one-way `contract_id` /
  `context.revision` digests fold model + auth-mode + scope + context-identity + evidence-revision +
  projection-revision; raw inputs never echoed (privacy test). Model-existence check precedes profile
  resolution; unknown provider/unprefixed → 400, unknown model → 404 `model_not_found`.

**Phase 4 — fail-closed dispatch classification + projection — IN PROGRESS.**
- Design (locked, ≥95%): a new pure core module `core/parameter_projection.py` holds a
  provider-agnostic `classify_and_project_chat_parameters(body, *, rules, auth_mode)` — the
  SAME rule source that drives the summary/detail now decides dispatch. Wired into
  `routes/chat.py` AFTER profile/auth resolution and BEFORE `_apply_defaults` +
  `prepare_chat_body` + `_inject_credentials` (credential injection never moves earlier).
- Ordering rationale: classify the CALLER body before profile defaults merge, so
  gateway-trusted defaults (temperature/max_tokens/reasoning_effort/timeout injected by
  `_apply_defaults` only when absent) never face the allowlist — shrinking required rules to
  caller-sent fields.
- Two-tier classification (§4.5): required-protocol/gateway-owned/transport fields
  (`model`, `messages`, `stream`, `extra_headers`, `metadata`, `timeout`) are authorized
  structurally (never need a rule); LiteLLM control-plane fields are already removed by
  `strip_dispatch_controls` upstream. Every OTHER optional field needs an enabled rule for the
  real auth mode or it rejects (unknown / wrong-auth / malformed / duplicate-channel /
  wrapper-not-object) with HTTP-safe paths, before credential access.
- Generic dotted-path projection (`provider_target`): `direct` rules land at their
  request_path; `provider_native` rules land at their target (e.g. `extra_body.top_k`).
  `provider_params` is consumed key-by-key and NEVER splatted into the dispatch body.
- Seed set (every field backed by an EXISTING capture/boundary test — §12):
  - OpenRouter (api_key): `temperature`, `max_tokens`, `provider`, `plugins`, `route`,
    `models` (direct) — proven by `test_openrouter_security.py::test_ordinary_openrouter_fields_pass_through`;
    plus P0 `provider_params.top_k` → `extra_body.top_k` (provider_native).
  - Anthropic (api_key+oauth): `reasoning_effort` (direct, enum incl. `none`) — proven by
    `test_chat_x_profile.py` (caller `reasoning_effort` reaches the anthropic dispatch body;
    `should_apply_profile_default("reasoning_effort")==False` means it is caller-only).
  - gemini/ollama/codex/huggingface: no rules — their route POSTs send no caller optional
    params, so fail-closed is correct with zero seeding.
- Cache: all P0 rules declare `cache_behavior="bypass"`; `build_cache_key` already bypasses on
  any non-prompt field, so isolation holds with ZERO cache-key change (no `keyed` two-value
  proof owed).
- Design resolution (global fail-closed now vs deferred per-provider overlays Phases 5-9):
  seeding each provider's ALREADY-PROVEN caller params at the flip (backed by existing capture
  tests), leaving richer observation/tool overlays to later phases — no test regresses, no
  field enabled without boundary proof.

#### Phase 4 GREEN — full-suite oracle corrections (this iteration)

The full non-live suite is the oracle for the fail-closed flip's blast radius. Running it
surfaced 3 regressions the per-phase seed reasoning had missed; both root causes fixed by
correcting production code (no prior test touched):

- **A — anthropic seed was too narrow.** `test_chat_request_cache.py::test_unsupported_field_bypasses`
  proves a caller sends bare `temperature` to Anthropic and expects DISPATCH (cache-bypass,
  reason `unsupported_fields`), not rejection. The prior ledger claim "anthropic = only
  `reasoning_effort`" was wrong. FIX: seed `temperature` (TEMPERATURE_SCHEMA, both auth modes,
  `cache_behavior="bypass"`). Cache isolation is unaffected — the key builder independently
  bypasses on any non-prompt field. (gemini/ollama/codex/huggingface remain rule-less: the suite
  sends them no caller optional params, so fail-closed with zero seeding stays correct.)

- **B — litellm orchestration control-plane vs fail-closed contradiction.**
  `test_openrouter_control_plane_isolation.py` proves caller-sent litellm ORCHESTRATION fields
  (`caching`, `guardrails`, `guardrail_config`, `disable_global_guardrails`, `prompt_id/_variables/
  _label/_version`, `cache_key`, `preset_cache_key`, `litellm_credential_name`) are NEUTRALIZED and
  the request PROCEEDS (200) — a deliberate SF-244 isolation property. These are NOT model params;
  the global `strip_dispatch_controls` does not cover them (the OpenRouter plugin owns their
  neutralization via `_strip_openrouter_litellm_controls`, historically inside `prepare_chat_body`
  — which runs AFTER classification). The new classifier sat between ingress-strip and that
  neutralizer and 400-rejected them.
  - Contradiction: fail-closed rejection of unknown fields ⟂ control-plane neutralize-and-proceed.
  - **Resolution:** neutralize the provider's OWN control-plane BEFORE
    classification, so the classifier only ever adjudicates genuine model-param candidates. This is
    exactly plan §4.5 tier (a) — transport/gateway-owned fields authorized structurally, no rule.
  - Mechanism: new port `ProviderPluginBase.strip_provider_dispatch_controls(body)` (default
    IDENTITY; pairs with the global `strip_dispatch_controls`). OpenRouter overrides it, delegating
    to the existing `_strip_openrouter_litellm_controls`. The route calls it after plugin resolution
    and before classify. `prepare_chat_body` is LEFT UNCHANGED (idempotent second strip = defense in
    depth), so no `prepare_chat_body` test can regress. Both isolation tests pass with assertions
    verbatim; fail-closed still rejects genuine unknown params (`banana`) and unruled
    `provider_params.*`.

### Phase 5 — Safe discovery transport + cache (DONE 2026-07-23)

Provider-agnostic foundation for the Phase 6-9 observation overlays. No new dependency
(reuses `asyncio`; concrete httpx adapter deferred with its test to Phase 6); no Tortoise
model, migration, durable catalog, or scheduler (plan §5.3, §11). Two SRP modules + two
test files (plan layout §7):

- `core/parameter_discovery.py` — bounded, sanitized HTTPS transport: origin allowlist, no
  redirects (status≠200 → fail), JSON content-type, byte cap, bounded JSON depth/nodes; a
  narrow injected `DiscoveryHttpClient` port; every failure raised as a sanitized
  `DiscoveryError` (no raw body/exception text). Provider integrations pass a FIXED https URL
  + their own allowed origins — never caller/response-derived (plan §5.2). The concrete httpx
  adapter is intentionally deferred to Phase 6 (lands with a `MockTransport` test alongside
  the first provider that consumes it) so this module stays pure, fully-tested logic.
- `core/parameter_discovery_cache.py` — bounded in-memory `ObservationCache`: injected
  monotonic clock, TTL, single-flight per key (asyncio.Lock), bounded stale-on-error window,
  LRU cap; keyed by `source + canonical model/backend + source revision` (revision mismatch
  invalidates). Returns a `CacheOutcome` labelled `fresh|stale|degraded`; cold failure yields
  a degraded outcome the provider maps to `unknown` observations — never fabricated fresh
  support (plan §5.3).

INVARIANT: discovery is NEVER on the chat dispatch critical path — chat uses rules only; the
transport/cache is invoked solely by the (Phase 6-9) detail-endpoint observation hooks.

**Outcome:** RED→GREEN both modules. Tests: 11 transport (happy path, non-allowlisted origin
never dials, non-https, redirect-not-followed, wrong/charset content-type, oversized,
malformed-json-sanitized asserts secret absent from error, too-deep, too-many-nodes,
sanitized transport error) + 10 cache (cold-miss, warm-hit-no-refresh, expired-ttl,
revision-invalidation, stale-within-window, degraded-beyond-window, cold-failure-degraded,
other-revision-not-served-stale, single-flight-runs-once, LRU-evicts-oldest) = **21 passed**.
Targeted gates green: `ruff check` ✓, `ruff format --check` ✓ (both modules + tests),
`pyright` 0 errors on both modules ✓, `check_no_enterprise` ✓.

### Phase 6 — OpenRouter P0 observation overlay (DONE 2026-07-23)

Wires OpenRouter public-catalog evidence into the detailed contract; dispatch stays rules-only
(fail-closed). Decomposed into focused implementation sub-iterations:

- **6a — pure catalog parsers + `ProviderDiscoverySnapshot` value type (fixture-tested).**
  - `core/chat_parameters.py`: add frozen `ProviderDiscoverySnapshot` (source_revision +
    `endpoint_observations` + `model_observations`, kept in SEPARATE fields so §5.1 "endpoint
    and model evidence stay distinct" holds structurally).
  - `plugins/openrouter_provider/discovery.py` (new): pure parsers — `parse_model_catalog_
    observations(catalog, upstream_model_id)` reads `data[].supported_parameters` (live shape
    verified: `data[]` with `id`, `supported_parameters`, `architecture`, `top_provider`,
    `context_length`); `parse_openapi_endpoint_observations(openapi, schema_name)` reads a
    standard OpenAPI-3 request schema's property names (OpenRouter publishes OpenAPI 3.0 at
    `/openapi.json`, `components.schemas`). Both emit `ProviderParameterObservation`
    (support=`supported`) with DISTINCT source labels `openrouter:models` / `openrouter:openapi`.
  - **DECISION (reversible, ledgered):** the parser maps OpenRouter-native params AIGateway
    addresses through the `provider_params.*` wrapper (currently `{top_k}`) to
    `provider_params.<name>`; standard/other params keep identity paths. This aligns `top_k`'s
    observation with its rule (`provider_params.top_k`) for a clean observed→ruled promotion,
    while `top_p` (standard, unruled) lands at identity → surfaces DISABLED
    (`projection_not_implemented`), satisfying the P0 "observed-but-unruled stays visible-but-
    rejected" checkpoint. Set grows as native rules are added. Honest-absence: a model missing
    from the catalog / a malformed row yields NO observations (never fabricated support, §5.3).
- **6b — async discovery hook + concrete httpx transport adapter — DONE 2026-07-23.**
  - `core/parameter_discovery.py`: added `HttpxDiscoveryClient` (the production
    `DiscoveryHttpClient`) — `follow_redirects=False`, bounded `aiter_bytes` read, every
    `httpx.HTTPError` translated to `DiscoveryError("unreachable")` with no cause chained out.
    Tested with `httpx.MockTransport`: status/content-type/body passthrough, 3xx NOT followed,
    transport fault sanitized (raw host string absent from the error).
  - `core/plugin_base.py`: added the async `discover_chat_parameter_snapshot(*, model, client,
    limits)` hook, default `None` (the async sibling of `chat_parameter_observations`; never
    enables a param; off the dispatch path).
  - `plugins/openrouter_provider/discovery.py`: added `discover_openrouter_snapshot(upstream_id,
    *, client, limits)` — fetches the FIXED `/api/v1/models` catalog via the Phase-5 bounded
    transport, parses per-model evidence, returns a snapshot; `DiscoveryError` → `None` (degrade
    to local); successful-fetch-but-model-absent → present-but-empty snapshot (honest, distinct
    from failure). Only the catalog is live-fetched this pass — the live OpenAPI fetch is
    deferred (its schema name is unverified; endpoint evidence comes from the labelled set).
  - `plugins/openrouter_provider/plugin.py`: override strips the gateway prefix (SAME rule as
    `prepare_chat_body`) + validates via `is_valid_upstream_model_id`, then delegates; an invalid
    gateway id fails closed to `None` WITHOUT dialing.
  - Gates: `ruff check`/`format --check`/`pyright`/`check_no_enterprise` green on all touched
    files; full non-live suite **1441 passed, 40 skipped** (+10). Append-only ✓.
- **SCOPING DECISION (surfaced for the P0-checkpoint review — reversible, additive):** the
  detail endpoint in v1 sources observations from the SYNC `chat_parameter_observations`
  ("labelled-local … no network" — `plugin_base.py` contract), NOT a blocking live fetch. The
  async live machinery (6b) is built + unit-tested but its wiring into the request path (an
  app-state httpx client + `ObservationCache` + clock, threaded into the route) is a documented
  follow-up. Rationale (repo signals, not preference): (1) `routes/model_parameters.py` states
  "discovery freshness arrives later" and has no http-client/cache DI seam; (2) the base hook's
  docstring codifies "labelled-local in v1; no network"; (3) Phase 6's task list is
  parsers/distinctness/overlay/hardening with NO "wire live fetch into endpoint" task; (4) every
  P0-checkpoint verification (observed-but-unruled stays visible-but-rejected) is satisfiable
  without a live call; (5) not making a gateway endpoint network-dependent without explicit
  direction is the lower-risk path. Everything built in 6a/6b/6c is shared by the full-live
  design too, so choosing full-live later is purely additive (zero rework).
- **6c — detail-endpoint overlay via labelled-local evidence — DONE 2026-07-23.**
  - `plugins/openrouter_provider/discovery.py`: added `LOCAL_SOURCE="openrouter:static"` (a label
    DISTINCT from the live `openrouter:models`/`openrouter:openapi`, so a reader can tell reviewed-
    static evidence from a network fetch — §5.1 "labelled") + `_REVIEWED_ENDPOINT_PARAMS`
    (temperature, top_p, top_k, max_tokens, frequency_penalty, presence_penalty, seed, stop) →
    `REVIEWED_ENDPOINT_OBSERVATIONS` (native `top_k` mapped through the `provider_params.*` wrapper
    so its observation lines up with its rule).
  - `plugins/openrouter_provider/plugin.py`: override `chat_parameter_observations` to return the
    labelled-local endpoint evidence (NO network); the route's existing composer overlays it with
    the plugin's OWN rules.
  - `tests/unit/openrouter/test_openrouter_parameter_overlay.py` (new, 6 tests): observed-but-unruled
    `top_p` → DISABLED/`projection_not_implemented`/source `openrouter:static`; promoted
    `provider_params.top_k` observed+ruled → ENABLED (bare `top_k` absent); `temperature`
    ruled+observed → ENABLED carrying evidence; `provider` ruled-unobserved → ENABLED/`unknown`/`none`;
    all 8 sampling fields visible with a status; sources ⊆ {`openrouter:static`, `none`}.
  - Gates: targeted `ruff check`/`format --check`/`pyright`/`check_no_enterprise` green; full non-live
    suite **1447 passed, 40 skipped** (+6). Append-only ✓.
- **6d — dispatch-side projection + cache isolation (characterize/preserve) — DONE 2026-07-23.**
  - No production code: the promotion, fail-closed classifier, and cache isolation were already
    correct (Phase 4 + the existing cache key builder); 6d LOCKS that behavior against a future
    overlay regression, and proves Phase 6's overlay additions did not disturb dispatch.
  - `tests/unit/openrouter/test_openrouter_dispatch_projection.py` (new, 6 tests): the route pipeline
    (`strip_provider_dispatch_controls` → `classify_and_project_chat_parameters` → `prepare_chat_body`)
    yields the final serialized body with `provider_params.top_k` promoted to `extra_body.top_k` and
    `temperature` at top level (raw `provider_params`/bare `top_k` fully consumed); the projection
    COMPOSES with the OME-428 hardening (pinned official `api_base`, gateway attribution headers, no
    caller `api_key`); an unruled `top_p` and a smuggled `api_key` are both rejected fail-closed
    (`UnsupportedParametersError`) BEFORE any credential work; and §4.6 isolation holds STRUCTURALLY —
    a body carrying the projected `top_k` returns `CacheBypass(reason="unsupported_fields")` (two
    distinct `top_k` values both bypass → never a shared key), while the same prompt with NO params
    stays cacheable.
  - Gates: FULL `run_gates.py aigateway` **ALL GREEN** (append-only ✓, ruff ✓, format ✓, whole-project
    pyright ✓, enterprise guard ✓, `pytest --cov` ≥80 ✓); full non-live suite **1453 passed, 40
    skipped** (+6).

### Phase 7 — Hugging Face P0 observation overlay (DONE 2026-07-23)

Mirrors Phase 6, adapted to HF's distinct source. Grounded against the LIVE public router
catalog (`https://router.huggingface.co/v1/models`) and the INSTALLED litellm 1.87.0
`HuggingFaceChatConfig` (it subclasses `OpenAIGPTConfig`), so every claim is evidence-backed:

- **Source shape (verified):** the HF catalog carries `data[].architecture.{input,output}_modalities`
  and a `data[].providers[]` array where EACH backend declares `supports_tools` /
  `supports_structured_output` / `context_length` / `status` — but NO `supported_parameters`
  anywhere. This confirms §5.1 "backend-conditional; no complete parameter list assumed". So HF
  splits: catalog → tool/modality/backend evidence (conditional per `:provider` suffix); PARAMETER
  evidence → the labelled-static chat schema (the installed transform's supported OpenAI params).
- **Installed-transform evidence (verified):** `HuggingFaceChatConfig().transform_request(...)`
  passes `temperature`, `max_tokens`, `top_p`, `seed` straight into the outbound JSON body (the last
  boundary before the wire). This is the §6.2-step-4 / §9-"Projection" proof required to ENABLE a
  rule.
- **DESIGN DECISION (separate by proof level; reversible, additive):** the epic ("expose all
  provider params") vs §6.2's caution ("no complete list assumed", "do not assume extra_body
  flattening") is resolved by making each param's gateway status follow its PROOF level. ENABLE only
  the standard OpenAI-direct params proven through the installed transform, seeding the SAME
  conservative pair OpenRouter enables — `temperature`, `max_tokens` (cross-provider consistency);
  OBSERVE the broader sampling set (`top_p`, `frequency_penalty`, `presence_penalty`, `seed`, `stop`)
  as labelled-static → they surface observed-but-DISABLED (`projection_not_implemented`), the P0
  "newly-observed-field-stays-rejected" demo. Enabling more proven scalars later is purely additive
  (zero rework) — surfaced for the P0-checkpoint review.
- **SCOPING (consistent with Phase 6 Reading B):** no live async fetch is wired for HF — its catalog
  carries no per-model params, so a live param-snapshot has no payload; param evidence is
  labelled-static and the catalog parser stays pure/fixture-tested. Backend-conditional tool/modality
  evidence is parsed and proven, integrated into the tool section only as far as the existing
  `chat_parameter_tools` seam allows cheaply.

Decomposed into focused implementation sub-iterations. **Ordering deviation (append-only safety):** rules
(7b) were seeded BEFORE the observation overlay (7c) — the reverse of the bullets originally
drafted — so no cycle ever asserted "temperature DISABLED" that a later cycle would have to
rewrite. This mirrors Phase 6's actual ordering and keeps every prior assertion true across the
phase (plan §9 append-only).

- **7a — pure HF catalog parser + labelled-static observation constants — DONE 2026-07-23.**
  `plugins/huggingface_provider/discovery.py` (new): `parse_hf_backend_capabilities(catalog, *,
  upstream_model_id, backend)` returns per-backend modalities + `supports_tools` +
  `supports_structured_output` (`_bool_or_none`: silence → None, honest absence; absent model OR
  backend → None); `HF_STATIC_PARAM_OBSERVATIONS` (label `huggingface:static`, sorted) for the 7
  standard sampling fields the installed transform accepts (NO `top_k`). Distinct live label
  `huggingface:router`. `tests/unit/huggingface/test_huggingface_discovery_parsers.py` — **8 tests**,
  RED-first (ModuleNotFoundError → GREEN).
- **7b — enabled rules + installed-transform proof — DONE 2026-07-23.**
  `plugins/huggingface_provider/parameters.py` (new): `huggingface_chat_parameter_rules()` = direct
  rules for `temperature` + `max_tokens` (auth `api_key`, revision `huggingface-2026-07`), the SAME
  conservative pair OpenRouter enables. HF plugin overrides `chat_parameter_rules`.
  `test_huggingface_parameter_projection.py` — **4 tests**: each rule PROVEN by running the request
  pipeline THEN the installed `HuggingFaceChatConfig.transform_request` and asserting the field
  reaches the outbound body (§9 last-boundary proof); `top_p` (unruled) and wrapped native `top_k`
  both REJECTED fail-closed.
- **7c — observation overlay + detail-contract composition — DONE 2026-07-23.**
  HF plugin overrides `chat_parameter_observations` → `HF_STATIC_PARAM_OBSERVATIONS` (NO network).
  `test_huggingface_parameter_overlay.py` — **5 tests** composing via `build_model_parameter_document`
  (the same composer the route uses): `temperature`/`max_tokens` ENABLED and carry
  `huggingface:static` provenance; `top_p`/`frequency_penalty`/`presence_penalty`/`seed`/`stop`
  observed-but-DISABLED (`projection_not_implemented`); sources ⊆ {`huggingface:static`, `none`};
  `top_k` absent. Proves §4.4: an observation NEVER enables — only a rule does.
- **7d — dispatch projection + cache isolation (characterize/preserve) — DONE 2026-07-23.**
  `test_huggingface_dispatch_projection.py` — **5 tests** (all GREEN immediately → locks existing
  behavior, no new production code): projected `temperature`/`max_tokens` compose with the pinned
  router `api_base` and request-local token strip; a caller `api_key`-as-param is REJECTED
  fail-closed; the REAL post-prepare HF body is cache-ineligible and two temperatures never share a
  key (§4.6); the core key rule isolates a projected output param (bypass) from a bare prompt
  (eligible). Backend-conditional `supports_tools` divergence across backends is proven in 7a.
- **P0 checkpoint — PASSED 2026-07-23** (see Gates + Deviations): full `run_gates.py aigateway` ALL
  GATES GREEN; full P0 diff reviewed across BOTH providers for overclaiming / control-plane escape /
  cache aliasing / secret exposure / central inventories — all clear; a newly-observed field stays
  visible-but-rejected on BOTH P0 providers (OpenRouter `top_p` via 6c/6d; HF
  `top_p`/`frequency_penalty`/`presence_penalty`/`seed`/`stop` via 7c/7b/7d).

Architecture note (SOLID/hexagonal): HF adds NO Tortoise model/migration/query (no persistence), so
ORM migration checks do not apply this phase. The overlay follows the same ports the core
defines (`chat_parameter_observations`, `chat_parameter_rules`); the plugin implements them; core
never imports the plugin.

### Phase 8 — Anthropic P1 observation overlay (DONE 2026-07-24)

The first P1 provider and the ONLY one so far offering BOTH `api_key` and `oauth`, so Phase 8 is
where the auth-mode-differentiated contract is actually exercised. Anthropic already carries two
rules from an earlier phase (`reasoning_effort`, `temperature`, both auth modes); Phase 8 widens the
proven set and adds the observation overlay + the api-key/OAuth split.

Grounded against the INSTALLED litellm 1.87.0 `AnthropicConfig` (the last boundary before
`litellm.acompletion`) — verified, not assumed:

- **Installed-transform evidence (captured):** `get_supported_openai_params` includes
  `temperature`/`max_tokens`/`top_p`/`stop` (NOT `top_k`, NOT `reasoning_effort`). `map_openai_params`
  renames `stop`→`stop_sequences`. `transform_request` emits `temperature`/`max_tokens`/`top_p`/
  `stop_sequences` top-level; a NATIVE `top_k` reaches `body["top_k"]` when delivered via
  `optional_params`, and `litellm.utils.get_optional_params(custom_llm_provider="anthropic", top_k=…)`
  DOES forward a top-level `top_k` — so the full acompletion path delivers it (§9 last-boundary proof,
  not a bare-kwarg assumption).
- **DESIGN DECISION (resolve "demonstrate an auth-differentiated contract" vs "never fabricate
  an asymmetry" by separating on PROOF-LEVEL):** sampling-param forwarding is auth-agnostic (the OAuth
  attribution block only rewrites `messages`/`system`; the SAME transform then runs), so `max_tokens`
  and `top_p` are enabled under BOTH modes. The genuine asymmetry is `top_k` (Anthropic-native): the
  DIRECT api-key path is transform-verifiable here, while the OAuth Claude-Code SUBSCRIPTION path's
  native-param forwarding is uncaptured in v1 and §6.3 forbids credentialed discovery — so `top_k` is
  enabled for `api_key` ONLY. It surfaces ENABLED in the api-key detail contract but is DROPPED from
  the conservative inline summary (`available={api_key,oauth} ⊄ {api_key}`) — the §6.3 signature.
- **Caller path CONSISTENCY (hexagonal):** `top_k` uses the SAME caller-facing wrapper as OpenRouter
  (`provider_params.top_k`) with a provider-specific target — top-level `top_k` for Anthropic vs
  `extra_body.top_k` for OpenRouter. Each plugin owns its projection target; core is unchanged.
- **SCOPING:** no live discovery (§6.3 — no credentials to the Models API in v1); observations are
  labelled-static `anthropic:static` only. `reasoning_effort` stays rule-only (no raw endpoint field;
  it maps to `thinking`), so its provenance is honestly `unknown`/`none`.

Decomposed (rules BEFORE observations — append-only safety, as in Phase 7):

- **8a** — widen proven rules in `parameters.py`: `max_tokens` + `top_p` (both modes), native
  `provider_params.top_k`→`top_k` (api_key only); each PROVEN by a test running the request pipeline
  THEN the installed `AnthropicConfig` transform; `top_k` REJECTED `wrong_auth_mode` under oauth.
- **8b** — `anthropic_provider/discovery.py` (new): `ANTHROPIC_STATIC_PARAM_OBSERVATIONS`
  (`anthropic:static`, NO live parser — §6.3); plugin overrides `chat_parameter_observations`. Overlay
  test: api-key contract enables temperature/max_tokens/top_p/reasoning_effort/`provider_params.top_k`,
  oauth contract shows `provider_params.top_k`+`stop` observed-but-DISABLED; inline summary =
  {max_tokens, reasoning_effort, temperature, top_p} (top_k OMITTED — step 5).
- **8c** — preserve Claude Code attribution/beta + dispatch composition (characterize/lock, mirrors
  7d): `uses_claude_code_attribution` (sk-ant-oat → True, raw key → False), `prepare_claude_code_body`
  billing-header block intact; projected params compose with the OAuth attribution rewrite.

Architecture note: Anthropic adds NO Tortoise persistence this phase, so ORM migration checks do
not apply. Ports unchanged; plugin implements; core never imports the plugin.

**OUTCOME (DONE 2026-07-24) — actual vs planned:**

- **8a (GREEN):** `parameters.py` widened — `max_tokens`+`top_p` `direct_rule` (both modes), native
  `provider_native_rule("provider_params.top_k"→"top_k")` (api_key only). Tests appended to
  `test_anthropic_parameter_projection.py` (3 Phase-4 → 8): both-mode enablement, api-key-only top_k
  rule shape, standard params + native top_k proven through the INSTALLED `AnthropicConfig` transform
  (`map_openai_params`/`transform_request`) and `get_optional_params`, top_k `wrong_auth_mode` (not
  `unknown`) under oauth. As planned.
- **8b (GREEN):** NEW `anthropic_provider/discovery.py` — `ANTHROPIC_STATIC_PARAM_OBSERVATIONS`
  (`anthropic:static`, NO live parser), set = {temperature, top_p, max_tokens, reasoning_effort, stop,
  `provider_params.top_k`}. **DEVIATION vs plan note (honesty correction, ↑confidence):** the plan
  header guessed `reasoning_effort` NOT in `get_supported_openai_params`; the INSTALLED litellm 1.87.0
  probe shows it IS supported (maps to `thinking`) and `stop` IS supported (→`stop_sequences`), while
  `seed`/`frequency_penalty` RAISE `UnsupportedParamsError` — so the observation set carries honest
  `support="supported"` for reasoning_effort/stop and deliberately OMITS seed/frequency_penalty (no
  fabricated support, unlike the OpenAI-compat providers). Plugin overrides `chat_parameter_observations`.
  NEW `test_anthropic_parameter_overlay.py` (8 tests): standard fields ENABLED w/ `anthropic:static`
  provenance under both modes; `stop` observed-but-DISABLED; `provider_params.top_k` ENABLED under
  api_key / visible-but-DISABLED under oauth; inline summary = {max_tokens, reasoning_effort,
  temperature, top_p} (top_k dropped — step 5); sources ⊆ {anthropic:static, none}.
- **8c (GREEN, characterization — no new production code):** NEW `test_anthropic_dispatch_composition.py`
  (2 tests) via injected `FakeClient` at the litellm wire boundary: OAuth path carries projected
  temperature/max_tokens/top_p AND the billing-header system block AND `anthropic-beta: oauth-*`;
  api-key path carries native `top_k=40` with NO billing header and `x-api-key` (not Authorization).
  Locks SF-244 F02 + §6.3 composition. `test_chat_handler.py` untouched (append-only satisfied).
- **Files:** M `src/aigateway/plugins/anthropic_provider/parameters.py`,
  M `src/aigateway/plugins/anthropic_provider/plugin.py`,
  A `src/aigateway/plugins/anthropic_provider/discovery.py`,
  M `tests/unit/anthropic/test_anthropic_parameter_projection.py`,
  A `tests/unit/anthropic/test_anthropic_parameter_overlay.py`,
  A `tests/unit/anthropic/test_anthropic_dispatch_composition.py`. +15 tests.
- **Gate:** full `run_gates.py aigateway` **ALL GATES GREEN** (append-only ✓, ruff ✓, format ✓,
  pyright ✓, no-enterprise ✓, pytest cov≥80 ✓). Suite **1490 passed, 40 skipped** (was 1475).

### Phase 9 — Gemini P1 (DONE 2026-07-24)

**Intent (plan §Phase 9):** surface Gemini's real parameter contract from ONE provider-local
source across summary/detail/dispatch, with public-API evidence kept separate from OAuth Code
Assist evidence, and prove every enabled rule reaches BOTH wire bodies (direct
`generativelanguage` generateContent AND OAuth `cloudcode-pa` Code Assist envelope).

**Ground truth (validated on-disk + live):**
- `message_adapter.build_generate_content_body(messages, optional_params)` maps
  `temperature→temperature`, `top_p→topP`, `top_k→topK`, `max_tokens→maxOutputTokens` (via
  `config_map`) and `stop`(str|list)`→stopSequences`, into `generationConfig`. This is the last
  AIGateway-owned body builder; both dispatch paths call it (OAuth wraps the same inner body in
  `{model, project, user_prompt_id, request:{...}}`).
- `plugin.chat_completion` harvests `optional_params` from TOP-LEVEL body keys minus
  `{model,messages,api_key,extra_headers,timeout}` → a native `top_k` rule must project to
  **top-level `top_k`** (target `"top_k"`), exactly like Anthropic.
- Gemini `chat_parameter_rules` currently inherits base `()`, and `routes/chat.py` ALWAYS runs
  the fail-closed classifier → today EVERY optional param to a Gemini model is rejected 400.
  That is the gap this phase closes (and the RED-test failure reason).
- Live `$discovery/rest?version=v1beta` (360 KB, 215 schemas): `GenerationConfig` has 25
  properties; `$ref` is a bare schema name; `GenerateContentRequest.generationConfig→GenerationConfig`.

**Decisions where requirements conflict:**
- **Rule the clean bounded scalars** — `temperature`/`top_p`/`max_tokens` (`direct`) + native
  `provider_params.top_k`→`top_k` (`provider_native`), ALL under BOTH auth modes. Both paths share
  `build_generate_content_body`, so there is NO param-level auth asymmetry (contrast Anthropic
  top_k api-key-only): never fabricate asymmetry; `top_k` stays in the summary intersection.
- **`stop` stays observed-but-unruled (visible-but-DISABLED).** `ParameterSchema.type` is a single
  Literal and cannot express `stop`'s `string|array[string]` union; forcing one type would narrow
  the accepted surface dishonestly, and union support in core is out of scope. This mirrors the HF
  precedent (which left `stop`/penalties/`seed` unruled): "represent existing
  mappings" (step 3) is satisfied by representing `stop` as evidence, not as an enabling rule.
- **Separate evidence (step 2) = auth-scoped observations.** `chat_parameter_observations`
  returns public GenerationConfig evidence (`gemini:discovery`) under `api_key` and Code-Assist
  reviewed-static evidence (`gemini:code-assist`) under `oauth`. Gemini is the first provider whose
  observations vary by auth mode — justified by the plan, not gold-plating.
- **Bounded Discovery parser (step 1)** implemented + tested against a fixture (no network in the
  sync path), mirroring HF's live-catalog parser that is tested but not wired to the sync contract.

**Sub-iterations:** 9a rules + projection (`parameters.py`, `test_gemini_parameter_projection.py`);
9b bounded Discovery parser + static evidence (`discovery.py`, `test_gemini_discovery_parsers.py`);
9c auth-scoped observation overlay (plugin wiring, `test_gemini_parameter_overlay.py`); 9d dispatch
capture — direct + OAuth bodies, messages→contents, reject caller-native `contents`
(`test_gemini_dispatch_projection.py`).

**Acceptance:** each enabled rule reaches `generationConfig` in BOTH wire bodies (captured via an
injected client at the httpx boundary); unruled/`contents`/wrong-shape fields fail closed before
dispatch; summary = safe auth intersection; detail overlay shows each field's honest status with
auth-scoped provenance; ALL gates green; append-only preserved.

**OUTCOME (DONE 2026-07-24) — actual vs planned:**
- **Files created (production):** `plugins/gemini_provider/parameters.py` (4 rules: `temperature`,
  `top_p`, `max_tokens` direct + `provider_params.top_k`→`top_k` provider-native, all both auth
  modes, revision `gemini-2026-07`); `plugins/gemini_provider/discovery.py` (bounded
  `parse_generation_config_params` parser + auth-split labelled-static observations
  `GEMINI_DISCOVERY_STATIC_OBSERVATIONS` / `GEMINI_CODE_ASSIST_OBSERVATIONS`).
- **Files modified (production):** `plugins/gemini_provider/plugin.py` — wired
  `chat_parameter_rules` + auth-scoped `chat_parameter_observations` (api_key→discovery,
  oauth→code-assist). No core edits (SOLID/hexagonal: a new param is a provider-local rule only).
- **Tests added (append-only, +30):** `test_gemini_parameter_projection.py` (6, 9a),
  `test_gemini_discovery_parsers.py` (10, 9b), `test_gemini_parameter_overlay.py` (8, 9c),
  `test_gemini_dispatch_projection.py` (6, 9d). No prior test modified.
- **Gates:** full `run_gates.py aigateway` **ALL GREEN** (append-only ✓, ruff ✓, format ✓,
  whole-project pyright ✓, enterprise guard ✓, `pytest --cov` ≥80 ✓). Suite **1520 passed, 40
  skipped** (= 1490 + 6 + 10 + 8 + 6). No `# type: ignore` (the 9d `auth_mode` narrowing was fixed
  by typing the helper params `AuthType`, matching the Phase 8/9c precedent).
- **Behavior change (public contract, intended):** before Phase 9 Gemini inherited base `()` rules,
  so the always-on classifier rejected EVERY optional param 400; now `temperature`/`top_p`/
  `max_tokens`/`top_k` are accepted and dispatched to both wire paths. This is the OME-479 gap the
  phase closes; every enabled rule is backed by a wire-capture characterization test.
- **Deviations:** (1) 9d is characterization — it passed green-on-first-run because 9a's rules +
  the pre-existing `build_generate_content_body` already compose correctly; the RED discipline is
  met by writing+running before declaring proven. (2) The bounded Discovery parser ships tested but
  is NOT wired to a live sync fetch in v1 (the async hook is deferred) — it currently corroborates
  the labelled-static observations, mirroring the reviewed HF precedent. Residual risk: the static
  Gemini evidence set must be revisited if Google's `GenerationConfig` gains public sampling scalars
  before the live-fetch hook lands.

### Phase 10 — Registry conformance + completion review (DONE 2026-07-24)

**Intent (plan §Phase 10):** lock the cross-provider invariants of the whole OME-479 contract as a
PROVIDER-AGNOSTIC conformance suite that discovers the REAL registry (`load_plugins`) and iterates
every registered model — so a future provider cannot silently violate the algebra — then a fresh
review vs the Linear requirement + plan, and the final ledger outcome + residual risks.

**Ground truth (validated against the live registry, exploration script — non-network hooks only):**
- Discovery finds 7 plugins today (anthropic, antigravity, codex, gemini-cli, huggingface, ollama,
  openrouter); the suite remains valid when Ollama contributes zero discovered models, so it must
  never assume a provider HAS models — it needs a non-vacuity floor instead.
- Empirically, right now: every model's canonical prefix routes back to its owning plugin (0
  failures); NO rule's `request_path`/`target` is a `GATEWAY_OWNED_FIELDS` member; NO transport name
  overlaps a rule path; every rule carries a `projection_revision`; and ALL 87 enabled detail
  entries have BOTH a schema AND `provider.support == "supported"` (source ≠ "none"). So "enabling is
  earned" is a live universal invariant, not just a P1 aspiration.

**Invariants asserted (all name-free / no provider inventory — item 5):**
1. **Routing** — every model's canonical prefix resolves via the registry back to its OWNING plugin
   (subsumes "Codex never OpenAI": a codex id whose prefix routed to an `openai` plugin would fail).
2. **Locked summary shape** — every `model_row` carries the locked hybrid keys with literal
   `unsupported_parameter_behavior == "reject"` and a same-origin `parameter_contract_url`.
3. **Gateway-owned lock** — across every auth mode + `None`, no rule's `request_path`/`target` is a
   `GATEWAY_OWNED_FIELDS` member (a locked field is authorized structurally, never by a rule).
4. **Summary = cross-auth-mode intersection** — each row's `supported_parameters` equals the
   INDEPENDENTLY recomputed intersection of enabled rule paths over `available_auth_modes` (not via
   `inline_supported_parameters`, to avoid a tautology) — never overclaims an auth-specific field.
5. **Enabled ⇒ fully evidenced** — per model per real auth mode, each enabled detail entry has a
   schema, a `gateway.projection`, a `gateway.cache_behavior`, `provider.support == "supported"`
   with a real source, AND a backing rule whose `applicable_auth_modes` includes that mode.
6. **Transport not rule-enablable** — `chat_transport_capabilities` names never overlap rule paths.
7. **Non-vacuity** — the registry is non-empty and the suite examined ≥1 enabled param, so broken
   discovery cannot green vacuously.

**Design resolution (item 5 "no inventory" vs item 6 "Codex never OpenAI"):** separate by place. The universal,
name-free routing invariant (1) subsumes "Codex never OpenAI" with zero provider names in the
generic suite; the ONE legitimately-named regression guard (codex GPT-family ids stay under the
`codex` namespace, and `registry.get("openai")` is None) lives in the codex-owned test file, where
naming codex is domain-correct — not inventory in the generic suite.

**Sub-iterations:** 10a generic conformance suite (`tests/unit/core/test_provider_contract_conformance.py`);
10b named codex-never-openai guard — landed as a NEW file `tests/unit/core/test_codex_namespace_guard.py`
(NOT an append to the committed `tests/unit/test_codex_provider.py`; see Deviations — append-only gate);
10c completion review + final ledger outcome.

**Acceptance:** the generic suite passes over the discovered registry with no provider-name literal;
the codex guard passes; full `run_gates.py aigateway` green; append-only preserved; the completion
review confirms summary/detail/dispatch all read ONE provider-local source, core imports no plugin,
and the Linear acceptance ("expose all provider params", fail-closed) is met.

**OUTCOME (DONE 2026-07-24).**
- **10a** — `tests/unit/core/test_provider_contract_conformance.py` (NEW, 6 tests): all 7 invariants
  above assert green over the live-discovered registry (7 plugins / 87 enabled entries) with ZERO
  provider-name literal. Per-file ruff/format/pyright clean; drove no production change (the algebra
  already held — a locked characterization of cross-provider guarantees).
- **10b** — `tests/unit/core/test_codex_namespace_guard.py` (NEW, 1 test): the ONE named guard —
  `registry.get("openai") is None` AND every codex model's canonical id stays `codex/…` resolving to
  the codex plugin. Relocated from an append into a NEW file after the append tripped the append-only
  gate (see Deviations); `test_codex_provider.py` restored byte-for-byte to HEAD.
- **10c completion review — PASSED.** Every Acceptance bullet is proof-backed:
  (1) canonical routing + locked hybrid row shape → 10a routing + locked-shape tests;
  (2) inline == enabled detail, ONE source → three projections → verified in-tree that summary
  (`core/model_capabilities.py:61`), detail (`routes/model_parameters.py:100`) and dispatch
  (`routes/chat.py:120`) all read the SAME `plugin.chat_parameter_rules(...)`, plus 10a's independent
  intersection recompute; (3) unknown/disabled → HTTP 400 pre-credential → Phase-4 fail-closed suite +
  per-provider dispatch-projection tests (caller `contents`/`stop` rejected `unknown`); (4) enabled ⇒
  fully evidenced → 10a `test_every_enabled_param_is_fully_evidenced`; (5) streaming separate transport
  + Codex never OpenAI → 10a transport-lock + 10b; (6) no new dep / Tortoise model / migration / durable
  state / credentialed discovery → verified: `pyproject.toml`+`uv.lock` unchanged on-branch, no
  migration/model file touched, discovery layer imports no ORM/credential/secret and the observation
  cache is a process-lifetime in-memory `OrderedDict` (§5.3); (7) prior tests green → full suite 1527
  passed, append-only preserved.
- **Architecture (SOLID/hexagonal) confirmed:** core (`aigateway.core.*`) imports NO plugin — the only
  `aigateway.plugins` reference in core is the runtime-discovery namespace STRING in `loader.py`
  (`importlib` + `pkgutil`, duck-typed against the `ProviderPluginBase` port). Ports in core, adapters
  in plugins, wiring via registry. No durable state introduced (correct: persisting discovered params
  would add stale-secret/migration cost for no benefit), so stack rule S1 is vacuously satisfied.
- **Scope reconciliation — Linear "P1: …, OpenAI" vs the implemented overlays.** The
  approved plan enumerated overlays as P0 OpenRouter + Hugging Face and P1 Anthropic + Gemini, plus the
  acceptance line "Codex never classified as OpenAI." This gateway integrates NO standalone OpenAI
  direct-platform adapter; OpenAI-family models are surfaced (a) through OpenRouter with FULL param
  exposure (P0) and (b) through the Codex ChatGPT-subscription endpoint (OAuth-only, correctly
  namespaced, no arbitrary-param surface). So there is no separate "OpenAI overlay" to build under this
  plan; a dedicated OpenAI platform-API provider — if later desired — is a distinct provider-integration
  item beyond OME-479's scope. The deliverable meets the approved plan in full; this nuance is flagged,
  not silently claimed.

### Gates (running)

- Per phase: `ruff check`, `ruff format --check`, `pyright` all green on every touched file; full
  non-live suite green after each phase (latest: **1490 passed, 40 skipped** end Phase 8; baseline 1298).
- Comprehensive `run_gates.py aigateway` (adds coverage% + enterprise guard across the whole app) is
  run at the **P0 checkpoint (end Phase 4)** and at **completion**, per the plan's checkpoint scope.
- **P0 checkpoint (end Phase 4) — PASSED 2026-07-23:** append-only ✓, `ruff check` ✓,
  `ruff format --check` ✓, `pyright` ✓, `check_no_enterprise` ✓, `pytest --cov=aigateway
  --cov-fail-under=80` ✓ → **ALL GATES GREEN** (full non-live suite 1398 passed, 40 skipped).
- **End of Phase 6 (2026-07-23) — full `run_gates.py aigateway` ALL GATES GREEN** (append-only ✓,
  ruff ✓, format ✓, whole-project pyright ✓, enterprise guard ✓, `pytest --cov` ≥80 ✓; 1453 passed,
  40 skipped). The whole-project pyright surfaced one latent `reportTypedDictNotRequiredAccess` in a
  6a test (fixed type-safely — see Deviations); no other gate moved.
- **End of Phase 7 / P0 checkpoint (2026-07-23) — full `run_gates.py aigateway` ALL GATES GREEN**
  (append-only ✓, ruff ✓, format ✓, whole-project pyright ✓, enterprise guard ✓, `pytest --cov`
  ≥80 ✓; **1475 passed, 40 skipped** = 1453 + 8 (7a) + 4 (7b) + 5 (7c) + 5 (7d)). No prior test
  weakened; the widely-imported `huggingface_provider/plugin.py` edit caused zero regression.
- **End of Phase 9 (2026-07-24) — full `run_gates.py aigateway` ALL GATES GREEN** (append-only ✓,
  ruff ✓, format ✓, whole-project pyright ✓, enterprise guard ✓, `pytest --cov` ≥80 ✓; **1520
  passed, 40 skipped** = 1490 + 30 Gemini P1). No prior test weakened; enabling Gemini's rule set
  caused zero regression in the always-on classifier's other providers.
- **End of Phase 10 / COMPLETION (2026-07-24) — full `run_gates.py aigateway` ALL GATES GREEN**
  (append-only ✓, ruff ✓, format ✓, whole-project pyright ✓, enterprise guard ✓, `pytest --cov` ≥80 ✓;
  **1527 passed, 40 skipped** = 1520 + 6 (10a conformance) + 1 (10b codex guard)). No prior test
  weakened; the whole OME-479 contract is locked by a provider-agnostic conformance suite.
- Zero regressions: the `chat_credentials.py` refactor is behavior-preserving, proven by the untouched
  OME-428 characterization tests staying green.

### Deviations / notes

- **Canonical ids — the earlier "BREAKING, must be coordinated" flag is WITHDRAWN (2026-07-27).**
  What is true: canonical ids changed the `/v1/models` `id` from bare (`claude-opus-4-8`) to
  provider-prefixed (`anthropic/claude-opus-4-8`), which is a change to that response for any
  consumer that stores or string-matches the published id. What was **wrong** was the conclusion
  that this broke a working chat path and therefore had to be coordinated before release:
  - `routes/chat.py` has rejected every unprefixed id with `400 model must be provider-prefixed`
    since well before this work. Verified at this branch's baseline `c55c56cf`, where both that
    branch in `routes/chat.py` and `test_chat_split_characterization.py::
    test_chat_400_when_model_not_provider_prefixed` (which posts bare `claude-sonnet-4-5`) already
    existed. A bare id was never dispatchable, so no working request stopped working — canonical ids
    made the catalog publish the id chat had always required, closing an inconsistency rather than
    creating one.
  - The named consumer **SF-284** (aigw-claude-backend dropdown) was unaffected twice over: it used
    `anthropic/`-prefixed ids from introduction, `630bd736` moved its suggestions to derive from
    `/v1/models` (prefixing bare rows, preserving prefixed ones, with tests for canonical discovery
    and canonical dispatch), and `9a9cf82d` deleted it outright — and
    `git merge-base --is-ancestor 9a9cf82d c55c56cf` exits 0, so the removal predates this baseline.
  There is no canonical-id release gate. Canonical provider-prefixed ids are the single client
  request identity, per the governing plan, which states no legacy-alias requirement. A compatibility
  shim (OME-644) was briefly built on the withdrawn premise and has been fully removed from the
  branch — see `docs/work/aigw/2026-07-27-OME-644-legacy-anthropic-model-id-aliases.md`.
- **Open/Closed seam, wired-but-empty:** the two new plugin hooks + the detail document's
  observation-derived / `tools` / `transport` sections are structurally present but empty for current
  providers; they are populated by the Phase 5+ provider overlays. This is the extension point, not a gap.
- **Placement:** canonical-id + summary logic lives in a dedicated `core/model_capabilities.py` (pure)
  rather than as a method on the `ModelEntry` transport DTO — keeps the algebra in core and `ModelEntry`
  a plain data carrier (SRP). Behavior matches plan §4.1.
- **Prior-test type-safety fix (append-only preserved):** the first whole-project pyright run (end of
  Phase 6) flagged `snap.model_config["frozen"]` in the 6a test `test_openrouter_discovery_parsers.py`
  — subscripting a non-total `ConfigDict` (`reportTypedDictNotRequiredAccess`). Fixed to the type-safe
  reader `snap.model_config.get("frozen") is True`, which preserves the assertion's meaning exactly (no
  weakening, no skip, no `# type: ignore`). This is a mechanical correctness fix the gate demanded, not
  a change to what the test verifies. Earlier cycles ran pyright per-changed-file; this subscript only
  trips the whole-project run.
- **Append-only gate → 10b relocated to a NEW file (append-only preserved).** The Phase 10 frame planned
  the named codex guard as an append to the committed `tests/unit/test_codex_provider.py`. The
  `run_gates.py` append-only check (`.claude/scripts/run_gates.py`) flags ANY `M/D/R` status on a
  test-glob path (it admits only `A`dded files — "adding tests is always fine"), so even a pure append to
  a committed test file fails it. Resolution: `test_codex_provider.py` was restored byte-for-byte to HEAD
  (`git checkout HEAD -- …`) and the guard now lives in a NEW dedicated file
  `tests/unit/core/test_codex_namespace_guard.py`. This satisfies the gate AND is arguably cleaner — the
  one legitimately-named guard sits in its own codex-dedicated module beside the generic suite, never
  weakening the gate to move on.

### Final Outcome (DONE 2026-07-24 snapshot)

- **Status:** all phases 1-10 + completion review DONE; every Acceptance bullet proof-backed (see the
  Phase 10 OUTCOME). Later consolidation commits are recorded in the closure sections below.
- **Actual files at this snapshot:** 9 modified sources — `core/plugin_base.py`, `main.py`,
  `plugins/{anthropic,gemini,huggingface,openrouter}_provider/plugin.py`, `routes/chat.py`,
  `routes/chat_credentials.py`, `routes/models.py`; 15 new sources — `core/{chat_parameters,
  model_capabilities,model_parameter_contract,parameter_discovery,parameter_discovery_cache,
  parameter_projection,standard_parameters}.py`, `plugins/{anthropic,gemini,huggingface,openrouter}_provider/{discovery,parameters}.py`,
  `routes/model_parameters.py`; ~28 new test files across `tests/unit/{core,anthropic,gemini,huggingface,openrouter}/`
  and top-level. No file exceeds the 450-line ceiling *at this point in the work* — three modules
  crossed it later during the review-remediation campaign; see the closure section below. No
  migration/model/dependency change.
- **Commits at this snapshot:** none; later implementation commits are recorded below.
- **Gates:** full `run_gates.py aigateway` **ALL GATES GREEN** at the P0 checkpoint (end Phase 4/7) and
  at COMPLETION (end Phase 10): 1527 passed, 40 skipped; coverage ≥80; append-only preserved.
- **Deviations:** see notes above (prior-test type-safety fix; 10b relocation for the append-only
  gate). The canonical-id "breaking change for SF-284" that this line previously listed is withdrawn
  — see the first note above.

---

## CLOSURE — 2026-07-27

State at this snapshot: **behaviorally complete, not yet declared plan-complete.** Branch
`OME-479-expose-all-provider-params`, HEAD **`ce49ffe1`**, 25 implementation commits.

The pre-ship review's CHANGES REQUESTED verdict was worked off across 25 commits. This ledger
preserves the durable closure evidence. At this snapshot, 16 findings were closed, F11 was withdrawn as a non-finding,
and F12 was closed for reporting with an enforcement residual deferred to a separate architecture
decision.

**One open owner decision gates "plan-complete":** whether to accept the 450-line module deviation
(three modules over) or require the splits before delivery. See *Residual risks* R1 below.

### Definition-of-done matrix — against the approved OME-479 implementation plan §12

> ⚠️ **SUPERSEDED for bullets 8, 9 and 11 — read the CLOSURE ROUND 2 section below instead.**
> This matrix is preserved as the historical record of the 2026-07-27 assessment at HEAD `ce49ffe1`.
> The subsequent readiness pass overturned three of its verdicts: bullet 8 was **NOT
> MET** (the published `cache_behavior` was violated when a provider preparation hook stripped an
> accepted field), bullet 9 was **NOT MET** (a "qualified for core" verdict is not the required
> proof), and bullet 11 was **NOT MET** (`apps/aigateway/README.md` still claimed OpenAI dispatch —
> the row below checked only the Codex namespace guard, never the prose). All three were closed in
> closure round 2 by commits `747802aa`, `1bc2f075` and `e7993cf5`; the current verdicts live in the
> `CLOSURE ROUND 2 — 2026-07-29` section and in the recreated final readiness review. Rows 1–7, 10,
> 12 and 13 stand, with the round-2 re-verification recorded below.

| # | Plan bullet | Verdict | Evidence |
|---|---|---|---|
| 1 | `/v1/models` returns canonical dispatchable IDs and the exact locked hybrid summary fields | **MET** | `tests/unit/core/test_models_route_contract.py` (3), `test_model_capabilities.py` (9). Canonical prefixing in `core/model_capabilities.py:45-46`; the ID published is the ID `routes/chat.py` requires |
| 2 | Inline arrays deterministic, conservative across auth modes, generated from provider-local rules not raw provider claims | **MET** | `core/chat_parameters.py::inline_supported_parameters` — sorted output; `INVARIANT: with NO auth mode available the summary is EMPTY` (`if not available: return ()`). `test_chat_parameter_contract.py` (35), `test_auth_scoped_discovery.py` (10) |
| 3 | A simple client can decide what it may send without a second request | **MET** | The `/v1/models` summary carries the enabled set per model; `test_models_route_contract.py`, `test_chat_parameter_contract.py` |
| 4 | Selected profile can fetch a private detailed contract: schema, source, freshness, provider support, gateway status/reason, auth applicability, projection, cache behavior | **MET** | `routes/model_parameters.py` + `tests/unit/test_model_parameters_route.py` (15), `test_model_parameter_contract.py`. Private cache headers incl. on error responses (`104b8b74`) |
| 5 | Unknown or disabled client parameters fail with HTTP 400 **before** credential access and dispatch; none silently dropped | **MET** | `test_parameter_projection_hardening.py` (23) — `test_unknown_top_level_optional_param_rejects`, `test_unknown_nested_provider_params_key_rejects_with_dotted_path`, `test_input_body_is_never_mutated`. Ordering is structural in `routes/chat.py`: `classify_and_project_chat_parameters` at :186, credential blob read `_inject_credentials` at :264. Pinned behaviorally by `test_chat_profile_default_validation.py::test_the_refusal_precedes_credential_access` and `anthropic/test_anthropic_thinking_conflict.py::test_the_refusal_precedes_credential_access` |
| 6 | OpenRouter + HF bounded public dynamic observation; Gemini bounded public Discovery; Anthropic labelled runtime/static without credentialed discovery | **MET** | `19a7ef68` (OpenRouter), `1c1eb5b7` (HF), `f37b89af` (Gemini, api-key path only), Anthropic static-labelled. `test_observation_overlay.py` (10), `test_tool_capability_overlay.py`, `test_discovery_runtime.py::test_static_window_reports_never_observed_without_claiming_degradation` |
| 7 | Dynamic-source failure bounded and honest; stale/degraded/unknown evidence never becomes fresh authorization | **MET** | `test_parameter_discovery_cache.py` (16) and `test_discovery_runtime.py` (12): `test_cold_failure_is_degraded_not_fabricated`, `test_refresh_error_beyond_stale_window_is_degraded`, `test_stale_from_other_revision_is_not_served_on_error`, `test_outage_past_the_stale_window_degrades_without_a_timestamp`, `test_a_provider_defect_surfaces_instead_of_masquerading_as_degraded`. Bounds enforced by `5d41561b` (max_bytes + wall-clock timeout), coordination state bounded by `9f1c7995` |
| 8 | Every enabled field has final-boundary projection proof and cache isolation or bypass proof | **MET** | Per-provider `test_*_parameter_projection.py` under `tests/unit/{anthropic,gemini,huggingface,openrouter}/` assert the field's presence/absence on the final payload. Cache: `test_request_cache_keys.py::test_output_affecting_fields_bypass` (parametrized) + `test_different_{model,provider,account,profile}_changes_hash`, `test_result_contains_no_raw_prompt_in_hashes` |
| 9 | One P0 field promotion proves a normal future parameter needs only provider-local rule, projection, and tests — **no shared route/core edit** | **MET for the route; qualified for core** | **Zero** promotion commit touches `routes/chat.py`, `core/chat_parameters.py` dispatch logic, or `core/plugin_base.py`. Each *new field* does add one declarative constant to the shared vocabulary `core/standard_parameters.py` — e.g. `3d11bb47` adds 4 lines (`PENALTY_SCHEMA`) and otherwise edits only provider `parameters.py` + tests. The pure case is `e5b0d3d1` (OpenRouter `top_k=0`): provider rule + tests only, no shared source edit at all. Shared *logic* is untouched; shared *vocabulary* grows by one line per field |
| 10 | Streaming remains a separate transport capability | **MET** | `test_chat_parameter_contract.py::test_stream_transport_capability_reports_an_enabled_gateway` / `…_a_disabled_gateway_with_a_reason` / `test_the_stream_transport_name_is_the_field_callers_actually_send` (`bae47ff2`) |
| 11 | Codex remains distinct from OpenAI; absent first-class OpenAI support stated honestly | **MET** | `test_codex_namespace_guard.py::test_codex_models_stay_under_codex_namespace_never_openai`; `test_codex_provider.py` |
| 12 | No new dependency, migration, durable parameter state, or secret-bearing discovery | **MET** | `git diff c55c56cf..HEAD` over `pyproject.toml`, `uv.lock`, `migrations/`, `models/` is **empty**. Gemini discovery is api-key-path only and public; no credential is written to a discovery cache |
| 13 | Existing tests green, additive coverage present, P0/final gates pass, final review records residual risks before any authorized Git/Linear action | **MET, with a caveat** | Gates: `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → **all green at `ce49ffe1`**. Full suite at HEAD: **1 failed, 1989 passed, 40 skipped in 128.90s**, coverage **92.10%** (floor 80%). The single failure is a pre-existing flake unrelated to this branch — R2 below. Additive coverage: ~28 new test modules; append-only discipline held (no prior test weakened; see the 10b note above). Residual risks recorded here |

**Non-goals confirmed not violated** (approved implementation plan §Non-goals): no central cross-provider
parameter inventory was introduced; streaming was not routed through the ordinary parameter
mechanism; Codex is not treated as OpenAI; URL4/client syntax owned by OME-480/481 is untouched; no
credential, hardening, sanitization, or cache-isolation behavior was weakened.

### Residual risks

- **R1 — plan-compliance: three modules exceed the 450-line ceiling.** Measured at `ce49ffe1`:
  `core/chat_parameters.py` **584**, `core/plugin_base.py` **575**,
  `plugins/openrouter_provider/plugin.py` **477**. (`routes/chat.py` is **391** — within the
  ceiling; it read 405 only while the withdrawn shim was applied.) `chat_parameters.py` is already
  covered by **OME-602** (filed, Triage). The other two had **no issue filed** at this snapshot;
  follow-ups were proposed but deliberately not created. *This is the open
  owner decision: accept the deviation, or require the splits before delivery.* No behavioral
  defect is implied either way.
- **R2 — one pre-existing flaky test makes "all green" probabilistic.**
  `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password` asserts
  `abs(missing - wrong) / wrong < 0.10` over medians of 20 bcrypt-cost-12 logins, so it is sensitive
  to machine load. Five isolated reruns produced **4 passes and 1 failure**.
  `git log c55c56cf..HEAD -- tests/unit/auth/test_login.py` is **empty** — no commit on this branch
  touches it, and it is unrelated to parameter work. Not fixed here (out of scope, and it is a
  security-timing assertion that should not be loosened casually), but CI should be expected to go
  red on it intermittently. Worth its own issue.
- **R3 — F12 enforcement gap.** OpenRouter model-specific support is now *reported* honestly, but
  dispatch can still forward a parameter a given model lacks; OpenRouter ignores it upstream. The
  gateway is honest in what it reports and permissive in what it forwards. Closing this requires an
  architecture decision (promote catalog evidence to rule authority, vs. one atomic capability epoch
  shared by summary/detail/dispatch) — explicitly **not** done inside OME-479. Needs its own issue.
- **R4 — three known parameter gaps deferred, unfiled.** (i) Codex function calling needs a
  Chat-Completions → Responses tool-shape adapter in `chat_handler._build_payload`; (ii) Ollama
  `frequency_penalty` needs a *value* transform (OpenAI `[-2,2]` where `0` = off → Ollama
  `repeat_penalty` where `1.0` = off), not just a rename — it is currently disabled rather than
  wrongly mapped, which is the safe state; (iii) `ProfileDefaults.reasoning_effort` is a bare
  `str | None` with no enum, so a profile default is validated later than a request parameter is.
- **R5 — dynamic evidence is machine- and network-dependent.** Discovery tests exercise bounded
  fakes, not live providers. Live behavior against real provider catalogs is covered only by opt-in
  `AIGW_LIVE=1` diagnostics, which are not merge gates.

---

## CLOSURE ROUND 2 — 2026-07-29 (Bullets 8, 9, 11)

Owner direction for closure round 2: every remaining Definition-of-Done failure or qualification
closes INSIDE OME-479. No deferral, no waiver, no wording amendment. Three focused TDD units;
required final state `13 MET`.

Base for the round: `6b4886f9`.

### Unit 1 — caller-visible cache behaviour is authoritative (Bullet 8)

**Intent.** For every accepted parameter whose rule declares `cache_behavior="bypass"`,
caller-visible presence of that request path must bypass prompt caching even when
`plugin.prepare_chat_body()` removes, renames, flattens or nests the field.

**Defect reproduced (route level, pre-fix).** `reasoning_effort="none"` returned
`X-AIGW-Cache: hit` on the bare request's key and never dispatched, while
`GET /v1/model-parameters` published `gateway.cache_behavior: "bypass"` unconditionally.
Cause: `routes/chat.py` planned the cache from the body *after* `prepare_chat_body`, and the
Anthropic hook drops the value `"none"` (it means what omission means), leaving a body
byte-identical to a bare prompt.

**Design.** Carry explicit cache-policy metadata from classification into cache planning — the
option the closure brief prefers. Cache planning was NOT moved before `prepare_chat_body`
(explicitly discouraged; would change ordering for every provider hook and for model
normalization).

- `core/parameter_projection.py` — new pure primitive `caller_cache_bypass_paths(body, *, rules,
  auth_mode)`: the request paths the caller ADDRESSED whose enabled rule declares `bypass`,
  computed from the caller-visible view. Shares `_addressed_request_paths` semantics with the
  classifier; reads `rule.cache_behavior` rather than assuming it.
- `routes/chat.py` — builds the rule set once, keeps the pre-projection caller view, resolves the
  bypass paths after classification succeeds, passes them into cache planning.
- `routes/chat_dispatch.py` — `_resolve_cache_plan` gains `bypass_paths`. The check runs AFTER
  `build_cache_key`, so it can only ever ADD a bypass: every previously-bypassing request keeps
  its original reason (`disabled` / `not_requested` / `stream` / `unsupported_fields`). Reuses the
  existing `unsupported_fields` reason code — no new caller-facing vocabulary.
- `core/request_cache/keys.py` — exports `PROMPT_KEY_FIELDS` so the conformance sweep can assert
  contract/pipeline agreement without reaching into a private constant.

**Tests (RED first).** `tests/unit/test_chat_cache_contract_composition.py` (new, 7 route-level
tests) — bare miss/store; `reasoning_effort="none"` bypasses, dispatches and does not consume the
bare entry; `"high"` bypasses and dispatches; repeated bare request still hits; the detailed
contract still publishes `bypass`; a preparation hook that strips a DIFFERENT accepted field
(`temperature`) cannot make the request cacheable; a bypassing request does not WRITE the cache
either. `tests/unit/core/test_caller_cache_policy.py` (new, **10** tests — `pytest --collect-only` on the
file; an earlier entry here said 11) — the pure primitive plus an anti-drift lock proving it agrees
with what classification accepted.
`tests/unit/core/test_provider_contract_conformance.py` — APPENDED one registry-wide guard
(`test_every_enabled_rule_declares_a_cache_behavior_the_pipeline_can_honor`): across every
registered provider × model × auth mode, a rule may declare a non-`bypass` cache behaviour only
for a path the key builder actually reads. No existing test was modified, weakened or skipped.

RED evidence: 3 of the 7 new route tests failed with `assert 'hit' == 'bypass'` /
`assert 'miss' == 'bypass'` before the fix; 4 passed (the positive controls the fix must preserve).

**Outcome.** GREEN. Full suite after the unit: **2092 passed, 40 skipped in 89.30s**;
`ruff check`, `ruff format --check`, `pyright` (0 errors) clean. `routes/chat.py` 411 lines
(ceiling 450).

### Unit 2 — a real provider-local P0 field promotion (OpenRouter `top_p`)

**Intent.** Prove the framework enables a genuinely observed-but-unruled field with a
**provider-local edit only** — no shared `core/` or `routes/` source change.

**Selection evidence** (the field was chosen, not assumed). All five gates confirmed before any
edit:

1. *Provider evidence reports it.* `chat_parameter_observations()` for
   `openrouter/anthropic/claude-fable-5` yields 14 observations, including
   `request_path='top_p' support='supported' source='openrouter:static' stale=False`.
2. *No existing rule enables it.* `chat_parameter_rules()` yields 13 paths; `top_p` is absent.
   The observed set minus the ruled set is **exactly `{top_p}`** — it is the only
   observed-but-unruled OpenRouter field, so it is the demonstration, not a contrived one.
3. *The installed final transform preserves schema and representation.* Probed against installed
   **litellm 1.87.0**: `OpenrouterConfig.get_supported_openai_params()` includes `top_p`, and
   `map_openai_params()` → `transform_request()` carries `0.0`, `0.5` and `1.0` onto the wire body
   verbatim as floats. The shared `TOP_P_SCHEMA` (number, 0..1) matches that range exactly, so no
   new or widened schema is needed.
4. *Strict routing applies correctly.* `prepare_chat_body` assigns
   `out["provider"] = dict({"require_parameters": True})` unconditionally — assignment, never a
   merge — so the promoted field rides a strict request.
5. *Cache behaviour is proven through the corrected mechanism.* `direct_rule` declares
   `cache_behavior="bypass"`; Unit 1's `caller_cache_bypass_paths` reads that from the
   caller-visible body, so presence of `top_p` bypasses regardless of preparation.

**Planned changes.** Source: `plugins/openrouter_provider/parameters.py` only — one
`direct_rule("top_p", schema=TOP_P_SCHEMA)` plus its import. Tests: a new
`tests/unit/openrouter/test_openrouter_top_p_promotion.py` carrying the ten-point proof, plus
surgical edits to the two existing tests that pin `top_p` as disabled.

**Approved prior-test changes.** Promoting any observed-but-disabled field
necessarily invalidates the tests asserting it is disabled — that is what closure requirement 4
("the detailed contract moves the field from observed/disabled to enabled") asks for, and the repo
has a documented precedent for it: `test_openrouter_parameter_overlay.py:112-120` records the same
retirement for OME-582 `stop`, OME-585 `seed`, OME-586 the penalties. Three functions change, none
weakened:
- `test_observed_but_unruled_field_is_visible_but_disabled` and
  `test_unruled_parameter_is_rejected_fail_closed` — retargeted to hold the real observation set
  fixed and **withhold the rule**. Every assertion is preserved verbatim; the scenario is now
  constructed rather than borrowed from a gap that no longer exists, which proves the
  observation-is-not-authorization property more directly.
- `test_every_endpoint_observed_sampling_field_is_visible_with_a_status` — the `top_p` disabled
  guard is retired and replaced with an `enabled` assertion, exactly as the three prior promotions
  did in the same function.

**RED evidence** (recorded after the fact — this entry originally asserted TDD order without the
measurement, so it was reproduced at HEAD `e7993cf5` by restoring `parameters.py` to `1bc2f075^`,
tests untouched, and re-running the proof suite):

```
27 failed, 3 passed in 2.09s
```

The 3 passing are deliberate positive controls that must hold both before and after the promotion:
`test_the_observation_alone_still_does_not_authorize` (the §4.4 invariant — had this gone red, the
promotion would have been enabling via the observation rather than the rule),
`test_the_contract_declares_bypass_for_top_p`, and
`test_the_boundary_overwrites_a_provider_that_reaches_it_with_top_p_present`. After restoring the
promoted source, the suite re-ran with **30 passed** and no residual implementation diff. Unit 3 has
no RED phase and none is claimed — it changes README prose only.

**Outcome.** GREEN, and the requirement-10 constraint held: the promotion commit `1bc2f075`
touches four files and **no shared `core/` or `routes/` source** —
`plugins/openrouter_provider/parameters.py` plus the three focused OpenRouter test files
(verified mechanically: no `src/aigateway/core` or `src/aigateway/routes` path changed). The source
change is **12 added lines, 0 removed**: one `direct_rule` line, one `TOP_P_SCHEMA` import, and a
10-line explanatory comment. Functionally the promotion is one line.

Proof suite `tests/unit/openrouter/test_openrouter_top_p_promotion.py` — **30 passed**; full
OpenRouter suite **415 passed**. No test function was removed and no skip/xfail introduced;
assertion counts moved **16 → 18** (dispatch projection) and **36 → 36** (parameter overlay).
The overlay parity was restored deliberately: retiring the disabled-loop lost one assertion, so
the replacement adds `assert "reason" not in params["top_p"]["gateway"]` — a genuine check, since
a stale `projection_not_implemented` beside an `enabled` status would tell a caller the field is
unprojected while it dispatches.

**Correction found while writing the proof, kept rather than papered over.** An end-to-end
`X-AIGW-Cache: bypass` header cannot *attribute* the bypass to `top_p` for this provider: every
OpenRouter dispatch body carries the pinned `api_base` and the gateway-owned `provider` policy
block, neither of which `build_cache_key` recognises, so **every OpenRouter request — including a
bare prompt — is structurally cache-ineligible** (`CacheBypass(reason='unsupported_fields')`).
Probed directly: prepared body keys are `['api_base','extra_headers','messages','model','provider']`.
This is pre-existing, fail-safe (it can only bypass, never mis-serve) and violates no published
promise, since every OpenRouter path publishes `cache_behavior: "bypass"`. Attribution is
therefore proven against Unit 1's `caller_cache_bypass_paths` (`("top_p",)` with the field, `()`
without) and the route test pins the observable header plus dispatch symmetry. Recorded as a
residual risk; any fix is a shared `core/` change, correctly out of scope for a provider-local
unit. An implementation note in the test carries the same explanation.

### Unit 3 — correct the OpenAI support statement (Bullet 11)

**Intent.** `apps/aigateway/README.md` claimed dispatch to "Anthropic, **OpenAI**, Gemini,
Ollama, …". Verified against the real registry: `load_plugins` discovers exactly **seven**
plugins — anthropic, antigravity, codex, gemini-cli, huggingface, ollama, openrouter. There is no
OpenAI Platform provider. Codex, the closest candidate, dispatches to
`https://chatgpt.com/backend-api/codex/responses` (`plugins/codex_provider/chat_handler.py:15`) —
the ChatGPT subscription backend, not the OpenAI Platform API.

**Change.** The rewrite names the seven registered providers, separates the two claims the old
text conflated (the request *shape* is OpenAI-compatible; the provider set is not), states Codex's
distinct backend explicitly, and states the absence of first-class OpenAI Platform support as
current fact without promising future support. Commit `e7993cf5`, one file.

### Closure round 2 — verification (all three units, at HEAD `e7993cf5`)

`uv run .claude/scripts/run_gates.py aigateway` — **ALL GATES GREEN**: append-only ✓,
`ruff check` ✓, `ruff format --check` ✓, `pyright` ✓ (0 errors / 0 warnings),
`check_no_enterprise.py` ✓, `pytest --cov` ✓.

| Metric | Value |
|---|---|
| Passed | **2123** |
| Failed | **0** |
| Skipped | **40** — not executed evidence; **33** `AIGW_LIVE=1` + **7** `AIGW_TEST_PG=1` (see below) |
| Duration | **132.60s** |
| Coverage | **92.22%** (7800 statements, 607 missed; threshold 80%) |

**Skip breakdown, corrected.** This entry originally recorded all 40 skips as opt-in `AIGW_LIVE=1`
provider diagnostics. That is wrong for 7 of them. Measured with `pytest -q -rs`:

| Gate | Count | What is not executed |
|---|---|---|
| `AIGW_LIVE=1` | **33** | `tests/live/` — provider diagnostics (anthropic, gemini, ollama, openrouter, the provider matrix) |
| `AIGW_TEST_PG=1` | **7** | `tests/integration/test_lifecycle_postgres_races.py` (6) and `tests/integration/test_tortoise_migration_smoke.py` (1) |

The 7 Postgres-gated skips are **core persistence tests, not provider diagnostics**, and they sit
inside the gate run. So "existing tests remain green" is scoped to what actually executed: on
SQLite, with Postgres lifecycle-race and migration-smoke coverage unexecuted. Nothing in this round
touches persistence or migrations (Bullet 12, verified), so this is a standing property of the
default gate run rather than a risk introduced here.

**Suite growth, measured against the round base.** Round base `6b4886f9`: 2114 collected / 2074
passed / 40 skipped. Reviewed HEAD `e7993cf5`: 2163 collected / 2123 passed / 40 skipped — **+49
collected, 0 removed**, from 37 new test functions (Unit 1 = 18, Unit 2 = 19, Unit 3 = 0). The
"2092 passed" figure recorded under Unit 1 above is the **post-Unit-1** intermediate, not the round
base; anything comparing 2092 to 2123 measures Unit 2 alone.

`git diff --check c55c56cf..HEAD` — clean, no whitespace errors.

Provider registry / conformance sweep with **every operator gate forced on** — **12 passed**.
Separate census over the same swept registry: **7 providers registered but only 6 reached**
(ollama contributes 0 models, so `_iter_models()` never yields it), **23 models, 236 enabled
parameter entries — 0 missing schema, 0 missing projection, 0 missing auth applicability, 0
`cache_behavior` declarations the pipeline cannot honour.** Per-provider enabled entries:
anthropic 75, huggingface 60, gemini-cli 48, openrouter 42, antigravity 6, codex 5, ollama 0.
Models per provider: anthropic 5, codex 5, huggingface 5, gemini-cli 4, openrouter 3 (behind its
operator gate), antigravity 1, ollama 0. Any statement of the form "passes across all 7 swept
providers" is an overstatement — the registry sweeps iterate models, so the correct number is 6.

**Gate disclosure.** The append-only check tripped before Unit 2 was committed, correctly flagging
the two modified prior test **files** (three prior test functions — enumerated individually under
Unit 2's approved prior-test changes above). It was adjudicated (not silenced) on those grounds, and the unit
proceeded with `--skip-append-only` and full disclosure. Because `append_only_check` diffs against
`HEAD`, it passes trivially once the work is committed — that is a tooling property, not evidence
that nothing changed.

Because that green line is uninformative, the check's comparison was re-run at `e7993cf5` against
the two bases that are informative. Against the round base `6b4886f9` it flags three files
(`test_provider_contract_conformance.py` — a pure addition, flagged only at file granularity — plus
the two OpenRouter files above). Against the branch base `c55c56cf` it flags three more from
earlier phases (`conftest.py`, `test_openrouter_security.py`, `test_chat_x_profile.py`). Comparing
function bodies as ASTs across all six: **no test function was removed anywhere**, and the only
function whose assertion count fell is `test_ordinary_openrouter_fields_pass_through` (7 → 3),
where OME-646 deliberately revoked the four native routing controls it asserted and replaced them
with a parametrized refusal test plus an ordering proof — the file's assertion total rose 26 → 27.

### Residual risks carried out of round 2

1. **Ollama contributes 0 models to the registry conformance sweep** — it builds its catalogue from
   a live daemon that is absent, exactly the limitation the suite's own implementation note documents. No
   settings choice closes it. Its rules are covered instead by
   `tests/unit/ollama/test_ollama_parameter_projection.py`.
2. **All OpenRouter requests are structurally cache-ineligible** (see Unit 2 above). Pre-existing,
   fail-safe, consistent with the published contract, but it means OpenRouter prompt caching never
   engages.
3. **`tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password` is flaky**
   under load — it failed once in a coverage-instrumented run (171s) and passed in the gate run and
   5/5 standalone re-runs. `tests/unit/auth/` is unchanged from the branch base. Pre-existing and
   unrelated.
4. **The final-boundary proofs pin installed litellm 1.87.0.** Deliberate tripwires — an upgrade
   that changes a transform fails these tests rather than silently changing wire behaviour — but an
   upgrade therefore requires re-review.
5. **No sweep enforces that an enabled parameter *has* a final-boundary probe.**
   `test_every_enabled_param_is_fully_evidenced` machine-checks schema, projection, `cache_behavior`
   and mode-specific rule applicability registry-wide; its assertion labelled "final-boundary
   evidence" checks a corroborating *observation* (`provider.support == "supported"` with a real
   source), which is a different boundary from "the installed transform carries this to the wire".
   Every enabled field has such a probe today, hand-written per provider — but a future promotion
   could ship a rule with no probe and every gate would stay green. Pre-existing; closing it needs a
   new registry-wide guard, out of scope for three provider-local units.
6. **OpenRouter reports per-model provider support but authorizes model-independently.**
   `openrouter_chat_parameter_rules()` returns the same `_RULES` for every model
   (`plugins/openrouter_provider/parameters.py:131-136`), while the observation overlay can carry
   per-model catalogue evidence. Nothing downgrades a `gateway.status` on a `provider.support`
   value — correctly, since §4.4 forbids an observation from authorizing and the symmetric rule is
   that it must not de-authorize. A model whose catalogue entry omits a parameter is therefore still
   told the gateway accepts it. Partially mitigated by `provider.require_parameters=true` on every
   OpenRouter dispatch. Carried forward from the round-1 review; untouched by this round —
   `top_p` is subject to it exactly as the 13 pre-existing OpenRouter rules already were.

### Final Outcome — CLOSURE ROUND 2 (DONE 2026-07-29)

All 13 Definition-of-done bullets **MET**. Bullets 8, 9 and 11 moved from `NOT MET` to `MET` via
`747802aa`, `1bc2f075` and `e7993cf5`; all ten previously-met bullets (1–7, 10, 12, 13) are
re-verified and none regressed. The recorded readiness evidence covered the reviewed HEAD, raw gate
results, accepted evidence corrections and residual risks above, and issued **READY TO SHIP**. The
final durable verification after later remediation is recorded below.

**Evidence audit.** A later completeness pass found defects **in the evidence record, not
in the implementation**: the skip characterization corrected above, the suite-growth arithmetic
corrected above, a 10-vs-11 test count, an undercounted call-site figure, "7 swept providers" where
6 is correct, two bullets (3 and 7) graded by deferring to a review that had been deleted, Bullet 13
missing from the regression list, one half of Bullet 8's conjunction left unargued, and Unit 2's RED
phase asserted but unmeasured. All are corrected in this ledger and in the review, each annotated
with what the earlier text claimed. **No source commit changed and no verdict moved**; the reviewed
HEAD is still `e7993cf5`. Two residual risks (5 and 6 above) are new to the record as a result.

**Additional findings at this snapshot:**
- Four tracked-source inaccuracies that the `top_p` promotion made stale, each needing a new commit:
  `plugins/openrouter_provider/observations.py:30` and `plugins/openrouter_provider/plugin.py:231`
  both still name `top_p` as the observed-but-unruled example (no longer true);
  `apps/aigateway/README.md:12-13` describes plugin discovery imprecisely (`core/loader.py:31-46`
  imports `<pkg>.plugin` and requires a `ProviderPluginBase` instance, not merely "a subpackage
  exposing a `PLUGIN` attribute"); and `apps/aigateway/README.md:174` still says "Provider plugins
  land here in follow-up PRs", which is false and now contradicts the corrected line 5-6.
Files changed this round (3 commits on `OME-479-expose-all-provider-params`):

| Commit | Files |
|---|---|
| `747802aa` | `core/parameter_projection.py`, `core/request_cache/keys.py`, `routes/chat.py`, `routes/chat_dispatch.py`, + 2 new test modules, + 1 appended conformance guard |
| `1bc2f075` | `plugins/openrouter_provider/parameters.py`, + 1 new and 2 modified OpenRouter test modules |
| `e7993cf5` | `apps/aigateway/README.md` |

---

## FINAL CLOSURE — 2026-07-30

This section supersedes every earlier current-state, commit, gate and delivery verdict in this
ledger while preserving those sections as dated implementation history.

**Final implementation HEAD:** `478e1c69` on `OME-479-expose-all-provider-params`. The final
remediation sequence after closure round 2 is:

- `0feafa41` — keep the OpenRouter `top_p` proof within the touched-file size limit.
- `65bed501` — harden provider parameter contracts after the complete branch review.
- `0e16d652` — close the remaining parameter-contract and discovery-cache gaps.
- `478e1c69` — harden nested request shapes, profileless Gemini provenance, discovery bounds and
  concurrent cache behavior.

### Final behavior

- Gemini and Antigravity function tools without a non-empty `function.name`, and Ollama
  `response_format.type=json_schema` requests without a nested schema object, fail at chat ingress
  before profile resolution, credential access or provider dispatch. Valid shapes still pass.
- Profileless Gemini derives contract auth mode and evidence from the same
  `GEMINI_API_KEY`/`GOOGLE_API_KEY` selector used by dispatch. Environment-key requests publish
  `api_key` plus public Discovery provenance; stored profile or connection credentials retain
  priority.
- Discovery fresh TTL, stale TTL, failure TTL and timeout reject every non-finite value, including
  environment input. Zero remains valid only for the stale and failure windows.
- Invalid UTF-8 discovery responses fail as sanitized `malformed_json`; replacement decoding can no
  longer erase restrictive evidence and cache the result as fresh.
- Positive and negative discovery records share one total LRU capacity. Per-key single-flight
  hands queued callers the exact revision-matched success or failure outcome even when another key
  evicts the payload while they wait. Evicted stale entries cannot reappear as ghost LRU records,
  and coordination state still disappears when the batch drains.

### Final verification

- Focused request-shape, Gemini provenance, settings, cache and transport suites passed. The final
  cache-focused suite reported **41 passed**.
- `uv run .claude/scripts/run_gates.py aigateway` — **ALL GATES GREEN** after the final change:
  append-only test check, Ruff check, Ruff format, Pyright, no-enterprise guard and full pytest with
  coverage floor.
- Additional concurrency testing reproduced three cache races, drove deterministic regressions for
  each, then re-ran revision/cancellation/capacity probes. Final verdict: **No findings**; all six
  branch-review findings and all three cache races closed.
- The whitespace check was clean. The two final implementation commits contain only their exact
  Python source/test allowlists.

### Residual risk and delivery state

Direct callers of `ObservationCache` that reuse one literal key across revisions in an interleaving
such as `r1, r2, r1` may perform two `r1` attempts because the in-flight handoff retains only the
latest revision result. Production `DiscoveryRuntime` includes source revision in the key, so this
interleaving is unreachable through the application wiring.

Implementation is complete. This ledger and the OME-479 child ledgers provide the durable
documentation provenance for the campaign.
