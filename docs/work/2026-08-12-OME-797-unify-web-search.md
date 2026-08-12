---
ticket: OME-797
stack: url4-cloud
status: in_progress
started: 2026-08-12
finished:
---

# OME-797 — Unify url4-cloud web search onto one route flag

## Intent

`apps/url4-cloud/url4.toml` declares two per-route capability flags — `web_tools` (the
Tavily tool loop url4-cloud runs itself) and `native_web_search` (provider-side search
delegated to aigateway). An operator has to know which mechanism each model supports and
hand-maintain the right flag per route; both default to `false`, so a route searches only if
someone remembers to declare it; and the file's header documents `web_tools` while never
defining `native_web_search`.

Collapse both into one `web_search` flag that defaults to **true**, and make the
native-vs-Tavily choice programmatic: a route whose provider is in
`WEB_SEARCH_NATIVE_PROVIDERS` delegates natively, every other route takes Tavily.

## Design

`ModelSpec` keeps ONE declared field and derives the mechanism:

- `web_search: bool = True` — declared per route; the only knob an operator sets.
- `provider_of(model_id)` — the segment before the first `/`; an unprefixed id is anthropic.
- `uses_native_web_search` — `web_search and provider_of(id) in WEB_SEARCH_NATIVE_PROVIDERS`.
- `uses_web_tools` — `web_search and not uses_native_web_search`.

`WEB_SEARCH_NATIVE_PROVIDERS = frozenset({"openrouter"})`.

WHY only openrouter: `web_search` is declared by exactly one aigateway plugin
(`plugins/openrouter_provider/parameters.py:279-286`). Every other plugin is a bespoke
`custom_llm_provider` (codex OAuth, gemini-cli / Code Assist, antigravity) rather than
litellm's stock vendor route, so litellm's `web_search_options` is not reachable through
them and `web_search_options` appears nowhere in aigateway. Adding a provider here is
per-provider aigateway work — declare the parameter, build the envelope from one pure
function, key it into the global cache, bump the adapter revision (OME-777 invariant I1).

WHY prefix-segment matching and not substring: `openrouter/anthropic/claude-opus-4.8` is an
OpenRouter route. A raw substring test would capture it the day `anthropic` joins the set and
send it down the wrong envelope.

WHY default true: an operator supplying a Tavily key wants search; the previous default made
every route silently non-searching until individually declared. Routes whose tool round-trip
is not yet verified end-to-end (anthropic, codex, gemini-cli, antigravity) are covered by a
later PR per owner decision — not gated here. Note a deployment with no `TAVILY_API_KEY`
still serves plain completions on those routes (`web_tools.build_runtime` returns `None`).

## Planned changes

- `src/url4_cloud/world_config.py` — `ModelSpec.web_search`, `provider_of`,
  `WEB_SEARCH_NATIVE_PROVIDERS`, the two derived properties, `_MODEL_KEYS`. The retired
  `web_tools` / `native_web_search` keys are deleted outright — no shim, no migration
  branch, no dedicated error (owner decision, 2026-08-12).
- `src/url4_cloud/runner/request_parameters.py` — `wants_web_search` reads `spec.web_search`.
- `src/url4_cloud/runner/connector.py` — `_retrieval_request` branches on
  `uses_native_web_search`.
- `src/url4_cloud/runner/web_tools.py` — `build_runtime` returns `None` for native routes.
- `url4.toml` — drop both keys from every route; rewrite the header block to document
  `web_search` and the routing rule.
- `src/url4_cloud/benchmarks/draco/aggregate.py` — comment referencing the old flag.
- Tests: the 13 files asserting the two-flag contract, plus new coverage.

## Test plan (RED first)

New — `tests/unit/test_web_search_routing.py`:
- `provider_of`: prefixed, unprefixed⇒anthropic, nested (`openrouter/anthropic/…`⇒openrouter).
- routing: openrouter route ⇒ native; codex/gemini-cli/antigravity/huggingface/ollama and
  unprefixed anthropic ⇒ Tavily; `web_search = false` ⇒ neither.
- INVARIANT: `uses_native_web_search` and `uses_web_tools` are mutually exclusive, and their
  disjunction equals `web_search`.
- config: default is `true` when omitted; explicit `false` parses; non-boolean raises.

Preserved behaviour that must stay green (contract, not implementation):
- `web_search=true` on a route declaring none ⇒ `web_retrieval_unavailable`.
- Benchmark-required search on such a route ⇒ `benchmark_retrieval_unavailable` (fails closed).
- `web_search=false` disables retrieval everywhere.
- Explicit request + no Tavily key ⇒ raises; implicit + no key ⇒ plain completions.
- Native branch emits `web_search: True` (+ `web_search_excluded_domains`) and NO `tools`.
- Tavily branch emits `tools`/`tool_choice` and never `web_search`.

## Acceptance

- One flag in `url4.toml`; no route declares a mechanism.
- `run_gates.py url4-cloud` green (ruff · format · pyright · layering · pytest ≥80%).
- The config KEYS `web_tools` and `native_web_search` appear nowhere in `apps/url4-cloud` —
  not in `url4.toml`, the parser, tests, or prose. (The token itself survives legitimately in
  the module `runner/web_tools.py` and the derived property `uses_web_tools`, which name the
  mechanism rather than a declaration.)

## Outcome

- **Actual files:** as planned, plus prose repairs the plan did not enumerate —
  `runner/web_tools.py`, `runner/connector.py` (three docstrings), `world_config.routes_for`,
  and `benchmarks/draco/aggregate.py`. Tests: the 13 planned files, plus the new
  `tests/unit/test_web_search_routing.py`.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` — ALL GREEN (ruff · ruff format ·
  pyright · check_layering · pytest cov ≥80%). Suite: **1168 passed, 5 skipped**.
- **Deviations:**
  1. **Scope grew to a second app.** The design could not work as specified: aigateway
     hardcoded `engine: "native"`, which OpenRouter honours even for models without built-in
     search (it errors), so "this provider searches natively" was a per-MODEL fact. That is
     exactly why the config carried two flags. Raised with the owner, who chose to drop the
     hardcoded engine — split into epic OME-799 with sibling OME-800 (aigateway), both landing
     in one PR because separating them ships a state where five OpenRouter routes force an
     engine their models do not carry.
  2. **`--skip-append-only` used, with the owner's explicit approval** of the specific edits.
     13 prior test files changed here. Three tests in `tests/unit/test_native_web_search.py`
     were REMOVED as unrepresentable under one flag; a comment block in that file records
     which test in `test_web_search_routing.py` now carries each guarantee.
  3. **No migration path for the retired keys** — owner decision, twice reinforced. An earlier
     draft added a `_RETIRED_MODEL_KEYS` branch and a test pinning its message; both were
     removed. `url4.toml` ships inside the image, so a stale config cannot meet new code, and
     the parser's existing unknown-key check already fails closed.
  4. **DRACO's judge changes retrieval backend.** `openrouter/google/gemini-3.1-pro-preview`
     declared `web_tools` and now resolves to native (OpenRouter → Exa, as the model has no
     built-in search). The owner confirmed this is expected. `REVISION` does not hash the
     mechanism, so the benchmark revision is unchanged by design; `benchmarks/draco/aggregate.py`
     records the change in its protocol caveats.
  5. **Provider matching is by prefix segment, not the substring the request described.**
     Behaviour is identical while the native set holds only `openrouter`; it diverges the day
     `anthropic` is added, when a substring test would capture
     `openrouter/anthropic/claude-opus-4.8`. Flagged to the owner and not objected to.
