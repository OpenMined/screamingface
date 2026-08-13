---
ticket: OME-303
stack: aigateway
status: done
started: 2026-08-07
finished: 2026-08-11
---

# OME-303 — AIGateway per-provider-call usage accounting (evidence contract MVP)

## Intent

Give AIGateway an opt-in, provider-extensible **evidence contract** for locally observed
provider send admissions. A caller that sends `X-AIGW-Accounting: v1` gets two sibling
response-only objects under `_aigw`: `usage_accounting` (one record per local provider HTTP
send-pipeline admission, with token/cache/reasoning evidence and provider-authored cost) and
`request_economics` (a current-request summary derived from those observed records). A cache hit
may carry a bounded historical final-response reference, never current spend or avoided-cost proof.

AIGateway returns **facts only**. USD conversion, deterministic attribution, run rollups,
saved-cost persistence and UI stay with URL4/Engine. No database model, migration or accounting
store is added, and no accounting metadata is ever written into
`request_cache_entries.response_json`.

Initial providers: OpenRouter (`litellm_async_http_v1`, direct cost in `openrouter_credits`) and
Anthropic (`litellm_async_http_v1`, token evidence with `direct_cost.status=absent`).

Governing plan (local scratch, untracked):
`.agent-team-AIGW/per-model-call-usage-accounting/implementation_plan.md`, whose MVP decisions are
frozen and binding.

## Planned changes

Core (new package `src/aigateway/core/usage_accounting/`):

- `_types.py` — immutable value/record types: `UsageAccountingStrategy`,
  `ProviderUsageAccountingEvidence`, `TokenUsage`, `CostAmount`, `ProviderCallRecord`,
  `AvoidedCost`, status/outcome enums.
- `_money.py` — canonical fixed-point Decimal amount spelling (`Decimal(str(value))`,
  no exponent notation) and Decimal summation.
- `_collector.py` — request-scoped collector + `ContextVar` bind/reset helpers,
  `dispatch_index` / `send_attempt_index` grouping.
- `_evidence.py` — bounded, sanitized raw-JSON evidence extraction.
- `_classify.py` — core-owned provider-neutral failure classifier
  (`provider_error` / `transport_error` / `conversion_error` / `indeterminate`).
- `_handler.py` — app-lifetime `AccountingAsyncHTTPHandler(AsyncHTTPHandler)` with total,
  non-raising request/response hooks; `create_client()` override so retry replacement clients
  inherit TLS verification and hooks.
- `_render.py` — `_aigw.usage_accounting` + `_aigw.request_economics` renderer for success and
  safe terminal errors.
- `__init__.py` — public surface.

Plugin contract:

- `core/plugin_base/_provider.py` — default-unsupported `usage_accounting_strategy()` and
  `normalize_chat_usage_accounting()` on the **dispatch** surface (not `_contract.py`).

Providers:

- `plugins/openrouter_provider/usage_accounting.py` (+ plugin wiring) — raw-usage mapper,
  `usage.cost` → `direct_cost` in `openrouter_credits`.
- `plugins/anthropic_provider/usage_accounting.py` (+ plugin wiring) — raw-usage mapper,
  `direct_cost=null`, `estimated_cost=null`; explicit gateway-owned dispatch-control injection.

Route / lifecycle:

- `routes/chat_accounting.py` (new) — negotiation, collector lifecycle, negotiated-`stream:true`
  rejection, handler injection for `litellm_async_http_v1`, metadata attachment.
- `routes/chat.py` — wire the seam; attach metadata to a **copy** after `store_global_response()`
  and on cache-hit replay.
- `routes/chat_dispatch.py` — per-dispatch index bump around the overload-retry lambda.
- `main.py` — build the app-lifetime handler at startup; **close it on lifespan shutdown**.

## Test plan

Written RED first, under `tests/unit/usage_accounting/` plus route-level tests beside the existing
chat suites. The 26 required cases from plan §9, grouped:

Negotiation / contract
1. Non-negotiated response shape unchanged.
2. `X-AIGW-Accounting: v1` changes neither provider parameter validation nor cache `key_hash`.
3. Negotiated `stream:true` rejected before dispatch, no handler injection.
21. Negotiated safe errors render `_aigw` beside `detail`; non-negotiated keep existing shape.
26. Negotiated unsupported provider miss → `accounting_not_supported`.

Collector / isolation
22. Supported provider dispatched, zero observed sends → `partial`, `evidence_complete=false`.
25. Concurrent requests share no collector, ID or evidence.
9. Gateway overload retries populate distinct `dispatch_index`.
24. `gateway_call_id` logged for correlation (or documented response-local only).

Transport
8. Hidden `ConnectError` retry → two send-admission records, hooks preserved, grouping populated.
10. Primary **and** replacement clients keep TLS verification and default aiohttp transport.
11. Hooks catch accounting exceptions; cannot fail a completed response or create another send.
12. App-lifetime handler closed on shutdown.
13. Redirect chains inflate neither `provider_calls[]` nor `actual_new_provider_calls`.
23. `latency_ms` null when no response body completed.

Cache boundary
4. Negotiated hit → `provider_calls=[]`, `actual_new_provider_calls=0`, no credential lookup or
   dispatch, no persisted metadata.
5. Hit with cached OpenRouter `usage.cost` → bounded historical direct-cost reference.
6. Hit without safe monetary evidence → historical direct-cost reference unavailable.
7. Miss stores provider JSON first, then returns a copy carrying current-request metadata.

Provider mappers
14. OpenRouter `usage.cost` → canonical string, `openrouter_credits`, never USD.
15. OpenRouter missing/partial usage stays null; LiteLLM zero-filled `Usage` is not evidence.
16. Anthropic input/output/cache/reasoning/tool usage maps; `direct_cost` null.
17. Anthropic dispatch receives gateway-owned retry/client controls.
18. Anthropic `estimated_cost` stays null in the MVP.

Errors
19. Converter/provider error after an admitted response → sanitized metadata, no raw
    prompt/provider-body leakage.
20. `conversion_error` produced by the core-owned provider-neutral classifier.

## Acceptance

- All 26 plan §9 tests pass; every prior test stays green and unmodified.
- Gates green: `uv run .claude/scripts/run_gates.py aigateway`
  (ruff check · ruff format --check · pyright · check_no_enterprise · pytest cov ≥80).
- No `_aigw`, `usage_accounting`, `request_economics`, `direct_cost` or `estimated_cost` in any
  persisted cache row.
- No database model or migration added (S1 not applicable — no schema change).
- Independent adversarial review of the actual diff against plan §11's falsification list,
  resolved or explicitly reported.

## Outcome

- **Actual files** (18 changed/added; all paths relative to `apps/aigateway/`):

  New — core package `src/aigateway/core/usage_accounting/`:
  `__init__.py`, `_types.py`, `_money.py`, `_collector.py`, `_classify.py`, `_handler.py`,
  `_render.py`.

  New — providers + route seam: `src/aigateway/plugins/openrouter_provider/usage_accounting.py`,
  `src/aigateway/plugins/anthropic_provider/usage_accounting.py`,
  `src/aigateway/routes/chat_accounting.py`.

  Modified: `src/aigateway/core/http_status.py`, `src/aigateway/core/plugin_base/_provider.py`,
  `src/aigateway/main.py`, `src/aigateway/routes/chat.py`, `src/aigateway/routes/chat_dispatch.py`,
  `src/aigateway/plugins/anthropic_provider/{plugin,chat_handler}.py`,
  `src/aigateway/plugins/openrouter_provider/plugin.py`.

  Tests (new, 228 cases under `tests/unit/usage_accounting/`): `test_money.py`,
  `test_collector.py`, `test_classify.py`, `test_handler.py`, `test_provider_mappers.py`,
  `test_render.py`, `test_accounting_seam.py`, `test_chat_route_accounting.py`,
  `test_lifespan_and_correlation.py`.

- **Commits:** not yet committed — awaiting explicit owner authorization.

- **Gates:** `uv run .claude/scripts/run_gates.py aigateway` → **ALL GATES GREEN**
  (append-only test check · ruff check · ruff format --check · pyright 0 errors ·
  check_no_enterprise · pytest `--cov=aigateway --cov-fail-under=80`).
  Full suite: **3247 passed, 13 skipped, 33 deselected**; coverage **92%** (gate floor 80).
  No pre-existing test was modified, weakened or deleted.

- **Deviations from the plan** (each deliberate, each with its reason):

  1. **`asyncio.CancelledError` is re-raised by the transport hooks.** The frozen decision says
     hooks catch all exceptions and never raise into LiteLLM/httpx; these hooks catch
     `BaseException` but deliberately re-raise `CancelledError`. Swallowing it would let httpx
     proceed with an upstream send the caller had already abandoned — a send caused by the
     accounting layer, contradicting the ticket's purpose. `CancelledError` is also not a type
     LiteLLM retries, so re-raising cannot trigger a resend. Documented at the catch site.

  2. **`_evidence.py` was not created.** Bounded, sanitized raw-JSON extraction turned out to
     belong at the only place that has the `httpx.Response` — `_handler._read_body` — with the
     size cap (`MAX_RAW_EVIDENCE_BYTES`) living beside the collector that stores it. A separate
     module would have been an indirection with one caller.

  3. **Two additions the plan did not list**, both found while wiring:
     `core/http_status.valid_http_status()` (a *sibling* of `valid_http_error_status`, not a
     widened version of it — widening would silently admit a 200 at ~40 existing call sites), and
     `chat_dispatch.convert_provider_response()` (see 4).

  4. **Conversion failure is raised directly, not through `_safe_dispatch_failure_response`.**
     That helper exists to flip a profile/OAuth connection to ERROR when a status means the stored
     credential is bad. A conversion failure says nothing about the credential — the call
     authenticated and succeeded — so routing through it could disable a working connection
     because of a gateway-side bug.

  5. **`avoided_chat_cost_from_cached_response()` is a THIRD plugin hook** (the plan named two).
     Core cannot parse `usage.cost` itself without encoding OpenRouter's field semantics in core,
     which may not import a plugin.

- **Defects found by the self-review of the diff (all fixed):**
  - `note_conversion_failure()` was **never called** — `conversion_error` was unreachable in
    production despite being unit-tested in isolation. Now wired at the conversion site and
    covered end-to-end through the route.
  - `accounting_error_response()` could raise from an **app-wide** exception handler, which would
    have broken error responses on every route in the gateway. Now contained: it falls back to
    Starlette's untouched handler and logs.
  - `observed_records()` was dead code; removed.
  - `begin_accounting()` constructed a throwaway collector just to mint an id; replaced with
    `new_gateway_call_id()`.

- **Review status:** the self-review above was later SUPERSEDED by an authorized **independent
  multi-agent review** of the implemented plan (7 risk dimensions, each followed by a dedicated
  refuter that re-read the cited code and defaulted to REFUTED under uncertainty). Result: 20
  confirmed / 16 plausible / 12 refuted, written to
  `.agent-team-AIGW/per-model-call-usage-accounting/implementation_review_findings.md` (untracked
  scratch). All four security-dimension leak candidates were refuted. Standing lesson: the gates
  were green throughout, so **gate-green is not defect-free** — every confirmed defect below was
  invisible to lint, types, coverage and 228 passing tests.

  Unifying theme of the confirmed findings: the code repeatedly treated **absence of observation as
  proof of absence**.

- **S1 (migrations):** not applicable — no schema or model change. Nothing is persisted.

## Outcome — post-review fix round (F1, F4, F6)

Authorized scope: F1, F4, F6 only. **F2 deliberately untouched** (its fix narrows the frozen "hooks
never raise" decision and needs an owner ruling). No `_aigw` schema field added — the wire shape is
unchanged, and every fix works by correcting the VALUE of an existing field.
Deferred by instruction: F3, F7, F8/F16.

- **Files changed** (4 source, 5 test; paths relative to `apps/aigateway/`):
  - `src/aigateway/core/usage_accounting/_render.py` — F1
  - `src/aigateway/core/usage_accounting/_collector.py` — F4
  - `src/aigateway/core/usage_accounting/_handler.py` — F4
  - `src/aigateway/plugins/openrouter_provider/usage_accounting.py` — F6
  - `tests/unit/usage_accounting/{test_render,test_collector,test_handler,test_provider_mappers,test_chat_route_accounting}.py`
    — 16 tests ADDED; no prior test modified, weakened or deleted (append-only check green).

- **F1 — an unsupported provider no longer certifies complete cost evidence.** `collector is None`
  meant two opposite things: "nothing was dispatched" (cache hit) and "a provider we cannot observe
  WAS dispatched to". The second rendered `actual_new_provider_calls=0` beside
  `actual_new_cost_evidence_complete=true` — a positive claim that billed work cost nothing.
  `_cost_evidence_complete` now takes `supported`/`cache_status` and returns `false` when
  `supported=false and cache_status != "hit"`. The cache-hit exemption is kept and tested, so the
  fix is honest rather than merely pessimistic. `render_aigw_metadata`'s docstring asserted the
  false premise ("`collector is None` means no provider dispatch was ever attempted") and was
  corrected.

- **F4 — redirect folding can no longer swallow a real send.** Reproduced end-to-end against real
  httpx 0.28.1 + litellm 1.95.0 before fixing: a 307 whose `Location` carries a non-printable ASCII
  byte → `httpx.URL()` raises `InvalidURL` → `Client._redirect_url` converts it to
  `RemoteProtocolError` → `AsyncHTTPHandler.post` resends the ORIGINAL request → **2 real transport
  admissions collapsed into 1 record**, reported as `redirect_hop_count=1`, `status=complete`,
  `evidence_complete=true`. After the fix: 2 records, `send_attempt_index` 1 and 2,
  `redirect_hop_count=0` on both, `status=partial` — and still `partial` when evidence is
  force-applied to every record, because `mark_incomplete()` latches.

  Two-part fix. The collector now records the redirect's intended target and folds only when the
  next admission matches it (`_continues_redirect`); a mismatch disarms the fold, marks the
  collector incomplete, and opens a new record. The handler resolves that target by mirroring
  httpx's own `_redirect_url` steps, and when the target CANNOT be resolved it does not arm the fold
  at all — no hop is coming, because httpx will raise instead of following it.

  Design notes worth keeping: (a) a "same-URL means resend" heuristic was rejected because a
  legitimate self-redirect would then split into two records — the very §12 inflation the fold
  exists to prevent; (b) `target=None` in the collector keeps its single meaning ("no URL
  information — fold, as before"), which is what preserves the existing opaque-marker tests, and the
  unfollowable-Location case is expressed by NOT calling `on_redirect_observed` — so the fix cures
  F1's disease rather than reintroducing it one layer down; (c) the residual limit is documented at
  the code: a provider that self-redirects is genuinely indistinguishable from a resend of the same
  URL at this seam, and folds.

  Verified reachability rather than assumed it: `httpx.InvalidURL` derives from `Exception`, NOT
  `ValueError`, while `idna`'s `IDNAError`/`InvalidCodepoint` (e.g. `Location: http://xn--/`) ARE
  `ValueError` subclasses that escape httpx's own `except InvalidURL` guard. Both arms are caught;
  neither subsumes the other.

- **F6 — OpenRouter cache-write tokens read the documented raw key.** The mapper read
  `prompt_tokens_details.cache_creation_tokens`, which appears nowhere in OpenRouter's API; the raw
  body uses `cache_write_tokens`. Every OpenRouter prompt-cache write was silently reported as
  `null`. Now resolved through `_cache_write_tokens`, preferring `cache_write_tokens` and falling
  back to `cache_creation_tokens` for LiteLLM's converted shape (installed litellm 1.95.0
  `types/utils.py` mirrors the two names as the same quantity). Keys are matched by PRESENCE, not
  truthiness, so a present-but-malformed value stays `null` instead of falling through to the alias.
  The old comment claimed OpenRouter reports writes under `cache_creation_tokens` and was replaced.

- **Every added test was proven to fail without its specific fix** (each guard was temporarily
  disabled and the test re-run), so none of the 16 is a tautology:
  F1 unit → `assert True is False`; F1 route → same defect through the real route;
  F4 collector → 3 of 5 fail on `_continues_redirect`; F4 handler → `assert 1 == 2` with
  `redirect_hop_count=1`; F6 → 2 of 4 failed at RED. The valid-redirect-chain test
  (`test_redirect_chain_does_not_inflate_provider_calls`) stayed green throughout, confirming no
  over-correction, and the two F1/F6 tests asserting unchanged correct behaviour pass either way as
  blast-radius guards.

- **Tests:** `uv run pytest tests/unit/usage_accounting -q` → **244 passed** (228 pre-existing + 16
  added).

- **Gates:** `uv run .claude/scripts/run_gates.py aigateway` → append-only test check ✓ ·
  ruff check ✓ · ruff format --check ✓ · pyright ✓ (0 errors) · check_no_enterprise ✓ ·
  coverage **92.10%** ✓ (floor 80). Full suite **3262 passed, 46 skipped, 1 failed** on both runs —
  but a DIFFERENT test each run, and both are wall-clock timing tests unrelated to this work:
  `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password` (compares
  medians of 20 timing samples) and
  `tests/unit/test_api_key_validation_http.py::test_validation_session_shares_one_absolute_deadline`
  (a 30 ms total budget against a 20 ms sleep). Confirmed pre-existing, not merely assumed: the
  login timing test **also fails in the OME-303 worktree, which contains none of these edits**, and
  neither test has any import path to `usage_accounting`.

  AIDEV-NOTE for whoever runs these gates next: this suite contains statistical wall-clock tests
  that flake under coverage instrumentation, so "all gates green" is a probabilistic claim here. Do
  not chase either failure as a regression without first reproducing it in a tree without the change
  under test.

- **Deviation:** the 2 route-level F1 tests were appended to `test_chat_route_accounting.py`, which
  was already 698 lines — past the card's ≤450 guidance — taking it to 764. Chosen over a new file
  because all the arrangement helpers and the `chat_client` fixture are module-local, and importing
  a fixture across test modules would have needed a `noqa`. The deviation is pre-existing and
  repo-wide (`src/aigateway/routes/auth.py` is 1424 lines); splitting this file is its own unit of
  work, not a side effect of this fix round.

- **Not committed.** Nothing staged; index verified empty. Awaiting explicit owner authorization.

## Outcome — post-review fix round (F2/F5)

Owner ruling captured in-session: accounting is an observer. Hooks must never raise
accounting-originated errors, but they also must not hide or transform provider/transport errors
that would have occurred without accounting.

Actual changes:

- `src/aigateway/core/usage_accounting/_handler.py`: `_on_response` now separates three failure
  sources. Cancellation still propagates; accounting-originated hook failures still get swallowed
  and mark the collector incomplete; provider/transport failures raised while reading the response
  body mark the collector incomplete and are re-raised unchanged.
- `tests/unit/usage_accounting/test_handler.py`: added
  `test_body_read_failure_preserves_the_transport_timeout`, which drives a real httpx response body
  stream that raises `httpx.ReadTimeout`. On the unfixed code it failed with `httpx.StreamConsumed`;
  after the fix LiteLLM classifies the original timeout path as `litellm.exceptions.Timeout`, with
  one send record left `partial`/`indeterminate`.
- `.agent-team-AIGW/per-model-call-usage-accounting/implementation_review_findings.md`: updated
  top-level fix status to mark F2/F5 fixed and to remove F2 from the open-owner-ruling list.

Checks run:

- RED: `uv run pytest tests/unit/usage_accounting/test_handler.py::TestHooksAreTotal::test_body_read_failure_preserves_the_transport_timeout -q`
  failed on the pre-fix code with `httpx.StreamConsumed`, proving the regression guard was live.
- GREEN focused: same test → `1 passed, 1 warning`.
- GREEN focused suite: `uv run pytest tests/unit/usage_accounting -q` → `245 passed, 1 warning`.
- `uv run ruff check .` → passed.
- `uv run ruff format --check .` → passed.
- `uv run pyright` → `0 errors`.
- `uv run python scripts/check_no_enterprise.py` → passed.

## Outcome — post-review fix round (F3, F7, F8/F16)

Authorized scope: remaining non-owner post-review findings after F2/F5. No `_aigw` schema field was
added; fixes preserve the wire shape and correct existing evidence values, fallback normalization, and
test/comment coverage.

Actual changes:

- `src/aigateway/routes/chat.py`: extracted `_dispatch_and_finalize_accounting()` so provider evidence
  is finalized before dispatch and conversion errors escape. Negotiated error responses now preserve
  raw evidence already captured by the collector instead of rendering `usage`, `direct_cost`, and model
  fields as `null`.
- `tests/unit/usage_accounting/test_chat_route_accounting.py`: added a route-level regression proving a
  conversion failure still exposes captured raw Anthropic usage evidence and remains incomplete.
- `src/aigateway/plugins/anthropic_provider/usage_accounting.py`: final-response fallback now reads
  LiteLLM's production OpenAI-compatible `prompt_tokens` / `completion_tokens` / `total_tokens` shape.
  Zero cache/detail counters in final-response fallback are treated as unknown because LiteLLM may have
  filled them, while non-zero detail evidence is still preserved.
- `src/aigateway/plugins/openrouter_provider/usage_accounting.py`: final-response cache/detail fallback
  now applies the same zero-as-unknown rule; raw OpenRouter evidence still preserves explicit zeroes.
- `tests/unit/usage_accounting/test_provider_mappers.py`: added production-shaped LiteLLM
  `ModelResponse.model_dump()` cases for Anthropic and OpenRouter fallback behavior.
- `src/aigateway/core/usage_accounting/_handler.py`: moved the `CancelledError` justification comment
  from the near-dead request-hook branch to the reachable response-hook body-read branch.
- `tests/unit/usage_accounting/test_handler.py`: corrected the cancellation regression to use the
  production hook set and cancel during response body read; the test now proves the send is admitted but
  left unresolved/partial when cancellation propagates.
- `.agent-team-AIGW/per-model-call-usage-accounting/implementation_review_findings.md`: updated fix
  status and verification for F3, F7, F8/F16.

Checks run:

- RED F3: `uv run pytest tests/unit/usage_accounting/test_chat_route_accounting.py::TestConversionFailure::test_captured_usage_survives_a_conversion_failure -q`
  failed on pre-fix code with `TypeError: 'NoneType' object is not subscriptable`, proving `usage` was
  still `null` on the negotiated conversion-error response.
- GREEN F3 focused class: `uv run pytest tests/unit/usage_accounting/test_chat_route_accounting.py::TestConversionFailure -q`
  → `6 passed, 1 warning`.
- RED F7: `uv run pytest tests/unit/usage_accounting/test_provider_mappers.py::TestAnthropic::test_litellm_final_response_shape_maps_core_tokens tests/unit/usage_accounting/test_provider_mappers.py::TestAnthropic::test_litellm_zero_cache_details_are_unknown_in_final_response_fallback tests/unit/usage_accounting/test_provider_mappers.py::TestOpenRouterPromptCacheTokens::test_litellm_zero_cache_details_are_unknown_in_final_response_fallback -q`
  → 3 failures: Anthropic core tokens were `None`, and final-response zero cache counters rendered as
  `0`.
- GREEN F7 mapper suite: `uv run pytest tests/unit/usage_accounting/test_provider_mappers.py -q`
  → `31 passed, 1 warning`.
- GREEN F8/F16 focused: `uv run pytest tests/unit/usage_accounting/test_handler.py::TestHooksAreTotal::test_cancellation_still_propagates tests/unit/usage_accounting/test_handler.py::TestHooksAreTotal::test_body_read_failure_preserves_the_transport_timeout -q`
  → `2 passed, 1 warning`.
- GREEN usage-accounting suite: `uv run pytest tests/unit/usage_accounting -q` → `249 passed, 1 warning`.
- `uv run ruff check .` → passed.
- `uv run ruff format --check .` → passed.
- `uv run pyright` → `0 errors, 0 warnings, 0 informations`.
- `uv run python scripts/check_no_enterprise.py` → passed.
- `uv run .claude/scripts/run_gates.py aigateway` → first run reached pytest/coverage but failed the
  unrelated wall-clock auth timing test
  `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password`; focused rerun of
  that test then passed (`1 passed, 1 warning`). Gate rerun → `ALL GATES GREEN`.

Dependency evidence used for F7:

- Installed `litellm` package version: `1.95.0`.
- Official LiteLLM docs show `ModelResponse` usage is OpenAI-compatible (`prompt_tokens`,
  `completion_tokens`, `total_tokens`, `prompt_tokens_details.cached_tokens`) and document
  `cache_write_tokens` mapping into `PromptTokensDetailsWrapper`.
- Local installed probe of `ModelResponse(..., usage=Usage(...)).model_dump()` confirmed the exact
  runtime shape used by this checkout, including mirrored `cache_write_tokens` / `cache_creation_tokens`.

Remaining triage:

- Confirmed low findings F9-F15 were not changed in this batch. They need case-by-case owner/developer
  triage because they involve dead-code policy, early-error public behavior, cache-status semantics,
  possible wire-schema deletion, provider cost-detail scope, a decorative test assertion, and mapper
  refactoring rather than the already-approved localized non-owner fixes.

- **Not committed.** Nothing staged. Awaiting explicit owner authorization.

## Planned — handoff-ready unpublished v1 correction round

Owner clarification (2026-08-11): this delivery owns the AIGateway producer contract only.
Engine integration, attribution, pricing and rollups belong to another owner. The current delivery
supports OpenRouter and Anthropic, but v1 must let later providers such as Hugging Face map existing
canonical concepts without core or Engine provider branches. Because v1 is neither published nor
pushed, correct it in place rather than carrying compatibility for the superseded draft.

TRIZ contradiction resolution:

- A giant universal provider union is closed and convenient but forces core/Engine churn.
- Provider-native subdocuments are extensible but force provider parsing and leakage controls into
  Engine.
- The selected separation-by-function design uses a structured canonical accounting core for every
  Engine-required fact and bounded, allowlisted, audit-only provider extensions for facts Engine may
  ignore. Any new Engine-required semantic still requires a future core schema version; the plan no
  longer promises impossible unlimited no-churn extensibility.

Planned files:

- `.agent-team-AIGW/per-model-call-usage-accounting/{initial_task_description,implementation_plan,implementation_review_findings,plan_review_findings}.md`
- `.agent-team-AIGW/per-model-call-usage-accounting/usage_accounting_v1_contract.md`
- `apps/aigateway/src/aigateway/core/usage_accounting/{_types,_collector,_render,_money}.py`
- `apps/aigateway/src/aigateway/routes/chat_accounting.py`
- `apps/aigateway/src/aigateway/plugins/{anthropic_provider,openrouter_provider}/usage_accounting.py`
- focused and golden tests under `apps/aigateway/tests/unit/usage_accounting/`

Acceptance:

- Wire terminology states observed attempts/send admissions, never proven billing or provider receipt.
- Canonical input/output totals have explicit subset semantics; unknown never becomes zero and no
  total can be double-counted with cache/reasoning breakdowns.
- OpenRouter and Anthropic map every v1 pricing-required fact without Engine provider parsing.
- Provider response IDs are bounded and reach the wire.
- Provider extensions accept only bounded allowlisted numeric/boolean/closed-enum evidence; no raw
  strings, nested provider objects, prompts, output, headers, credentials or errors.
- Cache hits produce no current attempts or spend; historical evidence is labelled as a cached final
  response with limited coverage, never as a proved counterfactual saving.
- Capture/cardinality, usage evidence and direct-cost evidence have independent statuses.
- Request economics is derived centrally and exactly from rendered attempts; incomplete/truncated
  attempts cannot produce a complete subtotal.
- A provider that maps existing canonical concepts can be added without changing the core schema or
  Engine decoder; a genuinely new Engine-required concept requires a future schema version.
- Exact wire goldens and compatibility rules are published for success, retries, partial failures,
  cache replay, explicit zero, unknown, unsupported providers and future-provider conformance.
- Focused accounting tests and `uv run .claude/scripts/run_gates.py aigateway` pass.

## Outcome — handoff-ready unpublished v1 correction

Implemented the normative contract in
`.agent-team-AIGW/per-model-call-usage-accounting/usage_accounting_v1_contract.md` for Anthropic and
OpenRouter. Engine implementation remains explicitly out of scope.

Delivered:

- observed-attempt terminology and stable attempt/cardinality identity;
- structured inclusive input/output usage with non-additive cache/reasoning subsets;
- Anthropic cache-write TTL and service-tier pricing context;
- OpenRouter credit cost plus bounded, non-aggregable unitless cost-detail audit evidence;
- independent capture, usage and provider-authored direct-cost statuses;
- bounded cache references with final-success-only coverage and no `avoided_cost` counterfactual;
- bounded allowlisted provider extensions, response IDs and deterministic 64 KiB degradation;
- exact decimal parsing and scaled-integer subtotal arithmetic without float/context rounding;
- transport retry/failure and HTTP-200 provider-body-error classification;
- strict JSON Schema shipped inside the built wheel;
- explicit unknown-version and negotiated-streaming rejection before dispatch.

Independent review:

- Stage 1 found 9 concrete defects; all were reproduced and fixed.
- Stage 2 found 4 additional defects; all were reproduced and fixed.
- Final monetary falsification found 2 precision defects; both were reproduced and fixed.
- Final reviewer verdict: **GO WITH NAMED RESIDUAL RISKS**. The only named low residual is
  future-plugin discipline for namespace-specific enum membership/provenance. Current Anthropic and
  OpenRouter mappers use explicit allowlists and emit no enum facts.

Verification:

- RED: new handoff test initially failed during collection because v1 types did not exist.
- Focused final: `uv run pytest tests/unit/usage_accounting -q` → `301 passed, 1 warning`.
- Full gate: `uv run .claude/scripts/run_gates.py aigateway --base 9f1d5256` →
  `ALL GATES GREEN` (append-only, ruff, format, pyright, Enterprise guard, pytest coverage).
- Wheel: `uv build --wheel` succeeded and contained
  `aigateway/core/usage_accounting/usage_accounting_v1.schema.json`.
- No live provider calls were run; provider contracts were verified against official docs, pinned
  LiteLLM 1.95.0/runtime fixtures and transport-level tests.
- Final amended commit: `400685a5` (`feat(aigateway): add usage accounting`, `Refs: OME-303`).
- Final post-commit review verdict: **GO**, with no findings.

## Planned — additional-review correction round

The deeper additional review superseded the prior no-findings conclusion. The original report is
preserved in
`.agent-team-AIGW/per-model-call-usage-accounting/additional_implementation_review_findings.md`; the
source-based adjudication and corrected fix scope are in
`.agent-team-AIGW/per-model-call-usage-accounting/additional_implementation_review_response.md`.

Intent:

- correct confirmed Anthropic, renderer-totality, outcome, direct-cost-status and schema defects;
- preserve the distinction between explicit conversion failures, provider-body errors and unknown
  post-response local failures;
- leave the OpenRouter money precision bound unchanged pending an explicit owner decision.

Planned source/contract changes:

- `core/usage_accounting/{_collector,_types,_render}.py` and the packaged JSON Schema;
- `routes/chat_accounting.py`;
- Anthropic and OpenRouter usage-accounting mappers;
- the normative v1 contract and incorrect redirect-fold comments;
- focused append-only regression tests, except existing golden fixtures whose provider field spelling
  is itself the confirmed defect and must be corrected from `reasoning_tokens` to `thinking_tokens`.

Test plan:

- RED regressions for lone-surrogate and malformed-type identifier degradation;
- RED Anthropic raw-thinking and converted-estimate tests;
- RED explicit conversion/provider-error/unknown post-200 outcome tests;
- RED malformed service tier, OpenRouter null cost, zero-record economics, printable ASCII and
  failure-code schema tests;
- provider-level cardinality canaries for Anthropic and OpenRouter shared LiteLLM transport;
- focused accounting suite followed by the configured AIGateway gates.

Acceptance:

- negotiated metadata rendering is total over bounded mapper evidence;
- Anthropic reasoning is provider-reported raw evidence only;
- no unknown local failure is falsely called conversion or success;
- zero observed records and direct-cost status follow the normative observed-attempt terminology;
- Python value objects and JSON Schema accept the same public scalar domains;
- all focused tests and AIGateway gates pass, with no live credential use.

## Outcome — additional-review correction round

The reviewer returned
`.agent-team-AIGW/per-model-call-usage-accounting/additional_implementation_review_findings.md`
with the original finding text retained, in-place corrections in §0, and its own response round in
§11. The companion implementation disposition is in
`.agent-team-AIGW/per-model-call-usage-accounting/additional_implementation_review_response.md`.
Together they form the final adjudication trail; neither should be read without the other.

Delivered:

- total bounded identifier/model rendering for non-strings, invalid UTF-8 and hostile `str`
  subclasses;
- exact runtime validation of canonical enums, nested value objects, extension containers,
  strategy/evidence/cache-reference return types and `unit_unknown` direct cost;
- Anthropic raw `thinking_tokens` mapping without publishing LiteLLM's converted local estimate;
- terminal-send-only outcome correction, preserving explicit conversion and provider-body errors;
- robust malformed strategy, service-tier and OpenRouter null-cost degradation;
- observed-record request economics, closed failure-code schema and printable-ASCII parity;
- installed-LiteLLM transport canaries for Anthropic and OpenRouter using the injected accounting
  handler and an in-process mock transport, with no live provider request;
- source comments and this handoff corrected to observed local send-admission terminology rather
  than provider receipt, execution or billing.
- the normative `direct_cost_status` ordering amendment and the unpublished narrowing of
  `failure_code` to the producer's closed seven-value vocabulary explicitly disclosed; four
  superseded assertions were corrected under the authorized correction scope.

TDD evidence:

- First additional-review RED set: `8 failed, 86 passed, 1 error`; failures covered nested runtime
  values, strategy containment, hostile strings, terminal-send targeting and the initial provider
  canary setup.
- The provider canary setup was corrected to disable LiteLLM fallbacks and its process-global
  background logger while retaining the real installed transport path.
- Independent Stage 1 review then raised six boundary/terminology claims. A separate Stage 2
  refuter narrowed the strategy severity, refuted the proposed cache-source restriction, and
  confirmed exact-type containment, hostile canonical scalars, `unit_unknown`, handoff and
  terminology defects. Each confirmed portion received a failing regression before its fix.

Final verification:

- `uv run pytest tests/unit/usage_accounting -q` -> **327 passed, 1 warning**.
- `uv run .claude/scripts/run_gates.py aigateway --base 9f1d5256` -> **ALL GATES GREEN**
  (append-only test check, Ruff, format, Pyright, Enterprise guard and full pytest coverage gate).
- Independent refuter assessment after the prescribed corrections: no blocking defect established.
- Residual testing limitation: renderer totality has adversarial field coverage but not exhaustive
  property generation over every possible future malformed object state.
- OpenRouter F-5 precision remains an explicit owner decision; contract, Python and JSON Schema stay
  mutually consistent and were not widened.
- No live provider calls or credentials were used. Nothing was staged or committed in this round.

## Planned — final closure iteration: F10 early negotiated errors

Intent:

- ensure negotiated safe 400 responses for an unprefixed model or an unknown provider carry the
  same bounded `_aigw` metadata envelope as later safe errors;
- preserve the exact existing response shape for non-negotiated callers;
- avoid logging or rendering the caller-authored unknown provider name as accounting metadata.

Planned files:

- `apps/aigateway/src/aigateway/routes/chat.py`;
- `apps/aigateway/src/aigateway/routes/chat_accounting.py`;
- `apps/aigateway/tests/unit/usage_accounting/test_chat_route_accounting.py`.

Test plan:

- RED route tests for negotiated unprefixed-model and unknown-provider errors asserting bounded
  `accounting_not_supported` metadata with zero attempts and `direct_cost_status=not_applicable`;
- parity tests proving the same non-negotiated errors remain bare `detail` responses;
- focused usage-accounting suite followed by the configured AIGateway gates.

Acceptance:

- F10 from `implementation_review_findings.md` is closed at the real route boundary;
- no provider lookup, credential resolution, cache access or dispatch is introduced for either
  early error;
- unknown accounting versions retain their existing fail-before-dispatch behavior;
- no FastAPI/LiteLLM public contract or `_aigw` wire field changes.

Outcome:

- Added route-level regressions for negotiated and non-negotiated unprefixed/unknown-provider 400s.
- `begin_accounting()` now accepts `plugin=None` only for unresolved early errors and publishes an
  unsupported session using the gateway-authored provider label `unresolved`; caller-controlled
  provider text is not written into accounting logs or metadata.
- Both early error branches publish that session before raising. No cache lookup, credential
  resolution or dispatch occurs.
- RED: negotiated cases failed with `KeyError: '_aigw'`; non-negotiated parity cases passed.
- GREEN focused: `TestEarlySafeErrors` -> `4 passed, 1 warning`.
- Accounting suite: `331 passed, 1 warning`.
- `uv run .claude/scripts/run_gates.py aigateway` -> `ALL GATES GREEN`.
- No schema, migration, dependency or provider contract change.

## Outcome — production type-ignore removal

- Removed both production `# type: ignore[arg-type]` escapes from
  `ProviderExtensionFact.__post_init__()` by making integer and decimal value-type narrowing
  explicit before calling the canonical validators.
- Added append-only boundary coverage for string/bool values under integer and decimal fact kinds.
- RED typecheck after removing the suppressions: Pyright reported two argument-type errors at the
  validator calls.
- GREEN focused: `test_v1_value_bounds.py` -> `39 passed, 1 warning`; Pyright -> `0 errors`.
- Accounting suite after F10 plus this iteration: `335 passed, 1 warning`.
- First gate run stopped only because the new test was inserted between prior tests; moving the same
  new test to the append-only end of the file resolved the process violation.
- Final `uv run .claude/scripts/run_gates.py aigateway` -> `ALL GATES GREEN`.

## Planned — immutable v1 exact release fixtures

Intent:

- provide an append-only, schema-valid, authoritative fixture matrix for every case required by
  `usage_accounting_v1_contract.md` §Golden acceptance fixtures;
- use production-shaped 32-hex attempt/call IDs and validate every rendered `_aigw` fixture against
  the packaged Draft 2020-12 schema;
- prove Hugging Face pinned/unpinned backend values fit the canonical contract while the actual
  plugin remains unsupported by default.

Planned files:

- new `apps/aigateway/tests/unit/usage_accounting/test_v1_release_fixtures.py` only.

Test plan and acceptance:

- exact OpenRouter success/zero/missing/retry/failure-with-usage fixtures;
- exact Anthropic cache/TTL, missing-cache, tier/tool and cache-reference fixtures;
- hidden resend versus overload grouping, response-less transport and conversion failures;
- unsupported miss, cache hit, bounds/overflow/leakage degradation;
- Hugging Face pinned/unpinned canonical backend plus default-unsupported declaration;
- non-negotiated parity and unknown-version rejection remain covered at the route and are indexed in
  the fixture manifest;
- all generated metadata validates against the packaged schema and the contract matrix has no
  missing case.

Outcome:

- Added `test_v1_release_fixtures.py` as the authoritative deterministic release matrix. It keeps
  the prior handoff examples untouched and uses fixed schema-valid `call_<32 hex>` /
  `attempt_<32 hex>` identities throughout.
- Covered every metadata-producing contract category and indexed the two route-only acceptance
  cases (non-negotiated parity and unknown-version rejection) that already have route regressions.
- Every positive fixture validates against the packaged Draft 2020-12 schema; a negative nested/raw
  provider-object fixture is rejected.
- Bounds fixture renders 64 of 65 observed attempts, reports one omission, marks capture partial and
  suppresses unverifiable subtotals.
- Hugging Face pinned/unpinned fixtures prove canonical `pricing_context.backend` fit while the real
  plugin remains default-unsupported.
- Focused release matrix: `5 passed, 1 warning`; accounting suite: `340 passed, 1 warning`; Pyright:
  `0 errors`.
- First full gate run had one unrelated statistical auth timing failure at 10.06% versus a 10%
  threshold; focused rerun passed. Gate rerun -> `ALL GATES GREEN`.

## Planned — implementation-review cleanup F9/F14/F15

Intent:

- remove the dead collector mutation surface that production never calls;
- make the concurrency isolation assertion observe per-response evidence rather than a value copied
  from the owning collector;
- centralize provider-neutral mapper policy before a third provider copies it.

Planned files:

- new `apps/aigateway/src/aigateway/core/usage_accounting/_mapper.py`;
- both shipped provider `usage_accounting.py` modules;
- `_collector.py`;
- append-only core helper tests plus targeted updates to the three tests that called the removed dead
  method and the one decorative concurrency assertion, explicitly authorized in this closure round.

Acceptance:

- no production or test caller of `on_send_failed` remains;
- raw usage wins over converted fallback consistently for both providers;
- converted zero-detail suppression and cache-write alias presence semantics remain unchanged;
- concurrency isolation fails if response evidence crosses collectors;
- no wire/schema/provider behavior changes.

Outcome:

- Added provider-neutral `_mapper.py` for bounded counts, mapping coercion, converted-detail zero
  suppression, cache-write aliases, raw-before-converted usage selection and response identifiers.
- Removed the dead `RequestAccountingCollector.on_send_failed()` surface and migrated the three
  tests that had been its only callers to the production `finalize_last_open_failure()` path.
- Replaced the decorative concurrency assertion with one over each collector's captured raw
  response owner. Cross-collector response evidence now fails the test even when requested models
  were initialized correctly.
- RED: the new mapper-policy module failed collection with `ModuleNotFoundError` before
  `_mapper.py` existed.
- GREEN focused mapper/collector/seam/concurrency suite: `123 passed, 1 warning`.

## Outcome — final publication hardening (F-5, L-2, L-9 and release confidence)

- Owner selected a v1 bound of 18 integer and **33 fractional digits**. `_money.py`, `_types.py`,
  provider-extension decimal validation, all three JSON Schema amount surfaces, tests and the
  normative contract now agree. Values with 19 and 33 fractional digits survive exactly; 34 are
  rejected. Subtotals remain integer-rescaled and independent of the ambient Decimal context.
- RED F-5: six focused failures covered canonical rendering, subtotals, `DirectCost`, decimal
  extensions and JSON Schema. GREEN focused bound suite: `129 passed, 1 warning`.
- L-2: persisted cache JSON now parses finite fractional numbers as `Decimal`, preserving the stored
  lexical OpenRouter cost until accounting metadata is attached. The existing binary-float overflow
  refusal remains. Full cache-store suite: `29 passed, 1 warning`.
- L-9: Anthropic converted/cache fallback now preserves LiteLLM 1.95.0
  `prompt_tokens_details.text_tokens`, cached/cache-creation tokens and 5m/1h
  `cache_creation_token_details`. The route-level installed-LiteLLM regression reaches the rendered
  wire with the complete breakdown.
- Added a dependency-free generative renderer regression over 90 boundary combinations; every
  output is bounded and validates against the packaged Draft 2020-12 schema.
- Renamed the unpublished internal `ProviderCallRecord` model to `ProviderAttemptRecord` and made
  the older handoff fixture IDs schema-valid, completing the provider-attempt terminology cleanup.
- Official evidence rechecked before edits: OpenRouter documents automatic response usage and cost
  in credits; its current OpenAPI models numeric fields as doubles. Installed LiteLLM is 1.95.0 and
  its Anthropic transformation explicitly sets inclusive `prompt_tokens`, uncached `text_tokens`,
  cache read/write and TTL detail fields. Installed FastAPI is 0.141.1; its documented
  response serialization contract and a production `-> Any` route probe confirmed that bare cached
  `Decimal` values do not preserve number shape on this route, so `_restore_cached_json_numbers()`
  converts them before FastAPI serializes the response.
- GREEN accounting suite before Stage 1 review: `355 passed, 1 warning`.
- Full configured gate: append-only policy stopped on owner-authorized old-test updates required by
  dead-API removal, the unpublished record rename and the selected amount-bound correction. Rerun
  with the gate's explicit `--skip-append-only` Confidence-Gate mechanism passed Ruff, format,
  Pyright, Enterprise guard and full pytest+coverage: `ALL GATES GREEN`.
- Stage 1 found two Medium defects: cache-wide Decimal replay could change a non-negotiated JSON
  number's external type, and two Anthropic release fixtures bypassed production mapper semantics.
  Both received RED regressions and were corrected: accounting reads exact cached Decimals before a
  non-mutating float restoration for the client response, and Anthropic goldens now originate from
  the shipped mapper with exact semantic assertions. Stage 2 review remains pending.
- Stage 2 confirmed one remaining Medium in the release oracle and one Low in early-error coverage.
  OpenRouter and Anthropic release cases now originate from their shipped mappers/cache-reference
  functions, and the canonical sorted JSON of all 18 metadata fixtures is pinned by independent
  SHA-256 goldens so any wire drift fails even when schema-valid. Negotiation now happens before
  body parsing with an unresolved body-independent session: negotiated malformed/body-shape errors
  carry bounded unsupported metadata, while an unknown version wins explicitly before malformed
  JSON and non-negotiated shapes remain unchanged.
- The Stage 2 verification pass found that response-less retry goldens still carried impossible
  response IDs and that preliminary validation minted an orphan correlation ID on valid requests.
  Response-less records now pass through the OpenRouter normalizer with no response and pin null
  identities; header version validation is side-effect-free, while only actual early errors publish
  the unresolved session. A valid negotiated request now allocates and logs exactly one call ID.
- Final focused accounting suite after all review corrections: `362 passed, 1 warning`; cache-store
  suite: `29 passed, 1 warning`.
- Final refuter rerun: **no findings**. Residual evidence gap is limited to live-provider calls and
  exhaustive malformed future-plugin state generation.
- Final configured gate required three coverage runs because the unrelated statistical
  `test_unknown_user_timing_close_to_wrong_password` failed twice under coverage after passing its
  focused rerun. The third `run_gates.py aigateway --skip-append-only` run passed Ruff, format,
  Pyright, Enterprise guard and full pytest+coverage: `ALL GATES GREEN`.

## Outcome — final adversarial follow-ups F-C/F-D/F-E/F-F

- F-C now exercises a private sentinel through the shipped OpenRouter normalizer from both request
  and raw provider input, proves it is absent from schema-valid rendered metadata and pins the
  canonical adversarial fixture hash without changing the original release matrix.
- F-D preserves one economic record for redirect chains but marks capture `partial` whenever an
  expected hop revisits any URL already admitted in that folded chain. That is the point where a
  legitimate redirect cycle and LiteLLM replacement-client resend are indistinguishable.
- F-E removed the remaining OpenRouter arithmetic `type: ignore` through explicit `None` narrowing,
  with no behavior change.
- F-F corrected the cache Decimal rationale: exact Decimal carriers are consumed by accounting, then
  `_restore_cached_json_numbers()` restores the prior numeric wire shape before FastAPI serializes
  the production `-> Any` response.
- RED evidence: direct self-redirect initially returned `complete`; the added redirect-cycle
  regression also returned `complete` before admitted-URL tracking.
- Focused verification: mapper/fixture/collector/cache/route set `160 passed`; final collector and
  release suites `41 passed`.
- First full gate reached `3384 passed, 46 skipped`, coverage `92.18%`, and failed only the known
  unrelated statistical auth timing test; its focused rerun passed. Two subsequent configured gates
  passed append-only, Ruff, format, Pyright, Enterprise guard and full pytest+coverage:
  `ALL GATES GREEN`.
- Independent two-stage review found and then closed redirect-cycle and Decimal-rationale gaps; the
  final refuter returned `GO` after probing 1,092 redirect chains and the settled F-C/F-D/F-E/F-F
  corrections. Nothing was staged, committed or pushed.

## Outcome — PR review taxonomy and documentation corrections

- Removed version markers from the evolving pre-beta accounting taxonomy: schema identifiers,
  transport capabilities, provider-extension namespaces, packaged schema filename and contract-test
  filenames now use descriptive unversioned names.
- Replaced the temporary `X-AIGW-Accounting: v1` negotiation with
  `X-AIGW-Accounting: enabled`. This header remains a non-streaming opt-in only until the separately
  designed default-on streaming unit removes it.
- Added the tracked implementation plan at
  `docs/tasks/aigw/2026-08-12-OME-303-per-provider-attempt-usage-accounting.md` and the current runtime
  contract at `apps/aigateway/docs/usage-accounting.md`.
- Documented that compatibility is not guaranteed until beta without publishing an `alpha` marker
  in the wire. Earlier numbered-contract references in this historical ledger are superseded by the
  tracked plan and runtime contract above.
- Replaced the hardcoded provider-name failure-taxonomy test with a guard derived from the actual
  provider plugin registry. The test fails explicitly if discovery returns no providers.
- RED evidence: the new schema taxonomy test failed on the existing `.v1` schema identifiers and
  `_v1` transport values. After the migration, the accounting suite passed: `367 passed, 1 warning`.

## Outcome — default-on non-streaming accounting

- Removed `X-AIGW-Accounting` activation and validation. Every non-streaming chat call now opens an
  accounting session by default; legacy header values are ignored and never reach providers or the
  cache key.
- Preserved the existing `stream: true` SSE path without accounting. Streaming requests, including
  recognized early errors, create no accounting session, inject no accounting client, bind no
  collector and return no `_aigw` metadata.
- Defined `_aigw` as a gateway-reserved response namespace. A provider-supplied value is replaced
  only in the returned copy; provider JSON stored in the request cache remains unchanged.
- Non-object provider results now fail as sanitized local conversion errors with bounded accounting
  instead of returning a successful bare JSON array that cannot carry `_aigw`; malformed results are
  never cached or reflected in the response.
- Specialized profile-index mutation conflicts now use the same accounting error renderer when a
  session exists, while non-chat and streaming conflicts retain the prior detail-only `503` shape.
- RED evidence: three activation tests initially failed for missing default accounting, legacy-header
  rejection and streaming rejection. Independent review additionally reproduced streaming early
  error metadata, a successful non-object response without accounting and an accounted mutation
  conflict without `_aigw`; each counterexample received a focused regression test before its fix.
- Verification: usage-accounting suite `377 passed`; affected provider/cache/security suite
  `119 passed`; final configured AIGateway gate passed Ruff, format, Pyright, Enterprise guard and
  full pytest+coverage: `ALL GATES GREEN`. One unrelated statistical auth timing failure passed its
  focused rerun before the successful full-gate repeat. Two-stage independent review returned
  **GO** with no findings.

## Iteration — extract taxonomy plugin

Status: in progress

### Intent

Keep AIGateway core limited to provider-neutral accounting signals, hook contracts and request-local
observation. Move taxonomy value objects, normalization policy, rendering, schema and provider mapper
policy into `aigateway.plugins.taxonomy`, while preserving the existing `_aigw` wire contract and
provider behavior.

### Planned changes

- Add an append-only architecture test that rejects taxonomy policy under `core/usage_accounting`
  and private module filenames in the new plugin.
- Introduce `src/aigateway/plugins/taxonomy/` with public module filenames and a curated package API.
- Repoint routes and provider plugins to the taxonomy plugin without broadening core dependencies.
- Leave Tortoise models, querysets, transactions and migrations unchanged; `main.py` lifespan remains
  responsible only for owning the app-lifetime observer resource.
- Preserve the existing schema IDs, response fields, error behavior, cache behavior and tests.

### Test plan

- Prove the architecture test is RED before moving production modules.
- Run the complete usage-accounting suite plus affected cache/provider/lifespan tests.
- Run `uv run .claude/scripts/run_gates.py aigateway --base c41c3b58 --skip-append-only` from the
  repository root after the refactor.
- Obtain a two-stage independent architecture review because the move touches a public plugin/core
  boundary and monetary evidence policy.

### Acceptance

- `core/usage_accounting` contains only observer signals/hooks and their lifecycle state.
- `plugins/taxonomy` owns taxonomy types, money normalization, mappers, rendering and packaged schema.
- No new private Python module filename is introduced, and moved private filenames are removed.
- No behavior or wire-format regression; all configured AIGateway gates pass.

### Outcome

Status: done

- `core/usage_accounting` now contains only the public `signals.py` and `hooks.py` modules plus
  its curated package API. Signals contain only a structural observer protocol and request-local
  `ContextVar` binding; hooks contain the app-lifetime LiteLLM/HTTPX observer.
- Taxonomy collection, types, failure classification, mapper policy, money normalization,
  rendering, request session orchestration and JSON schema moved to `plugins/taxonomy` with public
  module filenames. `routes/chat_accounting.py` is now a thin import facade.
- Taxonomy contributions were removed from `ProviderPluginBase`; Anthropic and OpenRouter retain
  optional plugin-owned contributions, while unsupported or invalid contributions fail safe in the
  taxonomy session.
- Provider discovery now silently ignores non-provider packages without `plugin.py`, while broken
  provider package/plugin imports remain warning-and-skip failures. Regression tests cover both
  missing-dependency paths.
- No Tortoise model, queryset, transaction, configuration or migration changed. The Tortoise
  no-private-module and no-business-logic-in-signals architecture rules are satisfied.
- RED evidence: the new architecture suite initially failed because taxonomy policy/schema lived
  in core and `plugins/taxonomy` did not exist. Final focused verification: `388 passed`, Ruff clean,
  Pyright `0 errors`. Final configured AIGateway gate passed Ruff, format, Pyright, Enterprise guard
  and full pytest+coverage: `ALL GATES GREEN`.
- Two-stage independent review found and drove fixes for loader diagnostics/exception containment,
  whole-core relative-import enforcement, invalid-strategy observability and the duplicated raw
  evidence bound. Final reviewer verdict: **GO**, no remaining findings.
- This iteration is included in the follow-up OME-303 taxonomy feature-plugin commit; no push was
  performed.

## Iteration — default-enabled taxonomy feature plugin

Status: in progress

### Intent

Make `plugins/taxonomy` an explicitly managed, default-enabled non-provider feature plugin with an
operator opt-out, while preserving the package hierarchy `plugins/<feature>[/extensions]` and keeping
provider discovery, provider registry and core accounting signals/hooks independent of taxonomy.

### Hook and signal analysis

- Existing `core/usage_accounting/signals.py` already exposes the complete request-local transport
  observer contract taxonomy needs; no new signal is required.
- Existing `core/usage_accounting/hooks.py` already owns app-lifetime HTTP observation and shutdown;
  no new hook is required.
- Enablement is taxonomy lifecycle/configuration, so it belongs in `plugins/taxonomy/plugin.py` and
  `settings.py`, not in core and not in `ProviderPluginBase`.
- Future isolated extensions follow `plugins/taxonomy_<subfeature>` and contribute through an explicit
  taxonomy-owned port only when existing contributions cannot express the new behavior.

### Planned changes

- Add public `plugins/taxonomy/plugin.py` and `settings.py` modules.
- Default `AIGW_TAXONOMY_ENABLED` to true and support an explicit false opt-out.
- Let the taxonomy plugin own handler creation/closure and request activation decisions.
- Store the active taxonomy plugin in FastAPI app state as composition-root wiring; do not add a
  generic feature-plugin base/registry until a second non-provider feature proves the abstraction.
- Add append-only tests for default enablement, environment opt-out, lifecycle, disabled response
  behavior and the absence of additional core hooks/signals.

### Acceptance

- Taxonomy is enabled by default and current non-streaming `_aigw` behavior is unchanged.
- `AIGW_TAXONOMY_ENABLED=false` disables handler creation, collection and `_aigw` attachment.
- Taxonomy remains outside `ProviderRegistry` and exports no provider `PLUGIN` contract.
- Core accounting remains exactly `signals.py` plus `hooks.py`; no new core extension point is added.
- No Tortoise model, queryset, transaction, configuration or migration changes; all gates pass.

### Outcome

Status: done

- Added public `plugins/taxonomy/plugin.py` and `settings.py`. `TaxonomyPluginSettings` reads
  `AIGW_TAXONOMY_ENABLED`, defaults to true and is frozen; `TaxonomyPlugin` snapshots the startup
  decision and owns the app-lifetime observer creation and close.
- `main.py` remains the explicit composition root. No speculative `FeaturePluginBase` or generic
  feature registry was introduced; taxonomy remains outside `ProviderRegistry` and exports no fake
  provider singleton.
- Provider discovery now scans only `*_provider` packages. This reserves `plugins/<name>` for a
  large feature and `plugins/<name>_<subfeature>[_<detail>]` for isolated extensions without making
  them appear as providers.
- Hook/signal recalculation found no missing extension point. Existing request-local signals and
  transport hooks carry every event taxonomy needs, so core accounting remains exactly
  `signals.py`, `hooks.py` and its package API.
- Disabled-at-startup taxonomy creates no handler or accounting session and emits no `_aigw` for
  successful or early-error responses. The taxonomy-owned response sanitizer removes forged or
  historical provider/cache `_aigw` before cache write/replay attachment without mutating source
  objects or executing provider dict-subclass overrides.
- No Tortoise model, queryset, transaction, configuration or migration changed. Public module names,
  lifespan ownership and signal purity comply with the `tortoise-dev` architecture rules.
- RED evidence: the new plugin tests initially failed import because `plugin.py` and `settings.py`
  did not exist. Final focused verification: `398 passed`; Ruff and format clean; Pyright `0 errors`.
  The final configured AIGateway gate passed Ruff, format, Pyright, Enterprise guard and full
  pytest+coverage: `ALL GATES GREEN`.
- Two-stage independent review found and drove fixes for startup-only enablement, forged provider and
  cache metadata, mutable settings replacement, and hostile dict-subclass containment. Final verdict:
  **GO**, no remaining findings.
- No commit or push was performed in this iteration.
