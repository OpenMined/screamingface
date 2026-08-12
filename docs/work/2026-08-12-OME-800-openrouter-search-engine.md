---
ticket: OME-800
stack: aigateway
status: in_progress
started: 2026-08-12
finished:
---

# OME-800 — Stop forcing the OpenRouter web-search engine

Epic: OME-799 · Sibling: OME-797 (url4-cloud)

## Intent

`plugins/openrouter_provider/web_search.py` assigns `{"id": "web", "engine": "native"}`.
OpenRouter documents that a forced `engine: "native"` always attempts the model's built-in
search **even when the model has none**, which errors; the automatic native-or-Exa fallback
happens only when `engine` is left unspecified.

So "OpenRouter searches natively" is a fact about each MODEL, not about the provider — and
every consumer has to keep a per-model list. `apps/url4-cloud/url4.toml` kept exactly that,
hand-splitting eight OpenRouter routes across two mechanisms. Dropping the key makes the
provider-level statement true and deletes that knowledge from the consumer (OME-797).

## Planned changes

- `src/aigateway/plugins/openrouter_provider/web_search.py` — `_WEB_SEARCH_POLICY` loses
  `engine`; the docstring records why the absence is load-bearing.
- `src/aigateway/plugins/openrouter_provider/global_cache.py` —
  `GLOBAL_CACHE_ADAPTER_REVISION` `openrouter-global-cache-2026-08c` → `-08d`.
- Tests: 4 assertions pinning `engine: "native"` in `tests/unit/openrouter/` change to the
  engine-free envelope; one new test states the absence as a requirement.

## Test plan (RED first)

- NEW: the envelope carries no `engine` key, so OpenRouter selects native-or-Exa itself.
- CHANGED (Confidence Gate — the owner approved the envelope change): 4 assertions that
  pinned `engine: "native"`.

No test asserts the revision string. Nothing pinned the old literal either, so a new one
would only restate the constant it is meant to guard.

Preserved, must stay green:
- `apply_web_search` is a pure function of `body` alone (OME-781 / D2).
- `web_search` and `web_search_excluded_domains` stay keyed; `exclude_domains` still rides
  the plugin object.
- The projection equals the dispatch envelope, because both use this one builder.
- No envelope at all when `web_search` is absent or not `True`.

## Acceptance

- `engine` appears nowhere in the emitted envelope.
- `run_gates.py aigateway` green (ruff · format · pyright · no-enterprise · pytest ≥80%).

## Outcome

- **Actual files:** as planned — `plugins/openrouter_provider/web_search.py`,
  `plugins/openrouter_provider/global_cache.py`, and two test files under
  `tests/unit/openrouter/`.
- **Gates:** `run_gates.py aigateway --skip-append-only` — ALL GREEN (ruff · ruff format ·
  pyright · check_no_enterprise · pytest cov ≥80%). Suite: **3035 passed, 46 skipped**.
- **Deviations:**
  1. **`--skip-append-only` used, with the owner's explicit approval.** Two prior test files
     changed: four assertions that pinned `engine: "native"` now expect the engine-free
     envelope. No test was removed, skipped, or weakened; one was added
     (`test_the_engine_is_left_to_openrouter`).
  2. **No test pins the adapter revision string.** The plan proposed one; nothing pinned the
     old literal either, so it would only have restated the constant it was meant to guard.
     The revision bump is covered by the existing projection tests, which read the constant.
  3. The historical `engine: "native"` quotation inside the SUPERSEDED docstring in
     `test_openrouter_web_search_cache.py` is left verbatim — it records what a deleted test
     once asserted, and rewriting history there would make the record false.
