---
ticket: OME-795
stack: url4-cloud
status: done
started: 2026-08-12
finished: 2026-08-12
---

# OME-795 — Make url4-cloud local mode reach a successful run out of the box

## Intent

`url4-cloud serve --local` against a loopback aigateway (auth disabled) cannot complete a run on a
clean checkout. Three independent defects stack, each producing an error that names the wrong
cause. This unit removes all three so that "clone → run two commands → evaluate an expression"
works without bespoke factory modules or hand-patched config, which is the premise local mode
exists to serve.

Full reproduction evidence, including the frame traces, is in `OME-795`.

## Planned changes

- `src/url4_cloud/local.py` — apply the `local_aigateway_base_url` fallback BEFORE the catalog is
  built, so discovery and connections resolve the same address. Decide the local benchmark default
  (see Design forks).
- `url4.toml` — prefix the five Anthropic model ids with `anthropic/` and update `default_route`.
- `tests/unit/test_declared_models_match_aigateway.py` — derive the expected id from aigateway's
  real `canonical_model_id` rule instead of a hardcoded per-provider prefix table.
- New/extended tests under `tests/unit/` for each defect (see Test plan).

## Design forks — resolved with the owner before coding

1. **Local benchmark default** → **(a)**: `create_local_app(benchmarks=None)` resolves to the
   builtins only when `URL4_BENCHMARK_ASSETS` is present in the run env, else `EMPTY_BENCHMARKS`.
   Naming an asset root is the operator asserting the assets exist, so a wrong path still fails
   loudly rather than silently serving a Benchmark-less Engine.
2. **How the pinning test learns the real prefix rule** → **(a)**: the per-provider prefix table
   is replaced by the provider NAME plus one mirrored rule (`_canonical`). aigateway is a separate
   uv project and cannot be imported, so this mirrors one rule rather than four assumptions.
3. **Prior test that had to change** (asked separately) → update
   `test_local_app_automatically_wires_the_loopback_aigateway`'s `assert app.state.catalog is None`
   to `is not None`. That assertion pinned the defect itself.

## Test plan (RED first, append-only)

- Local composition builds a catalog when only the local default address applies — currently fails
  (catalog is `None`), pins defect 1.
- A local App with no benchmark assets present can still build an executor and run a
  non-benchmark expression — pins defect 2.
- Every id declared in `url4.toml` satisfies aigateway's canonical prefix rule, and the declared
  `default_route` names a declared model — pins defect 3 and would have caught the drift.
- Boundary/error: an explicit `URL4_CLOUD_AIGATEWAY_BASE_URL` still wins over the local default;
  a declared world whose ids do not match still degrades (503) rather than raising at composition.

## Acceptance

- On a clean checkout with a loopback aigateway (auth disabled) and no extra env:
  `GET /v1/models` returns the full declared catalog (not 503), and a single-model expression
  reaches `terminated: succeeded` without a custom factory or a patched `url4.toml`.
- The declared-models test fails if either side's prefix rule changes.
- All card gates green for the `url4-cloud` stack; no prior test weakened, skipped or deleted
  (two were modified under explicit owner approval — see Design forks 2–3 and Deviations 1).

## Outcome

- **Actual files** (as planned, plus one not foreseen):
  - `src/url4_cloud/local.py` — added `_local_benchmarks()` and `_with_local_gateway()`; the local
    address is now substituted ONCE, above the catalog, and feeds both consumers.
  - `url4.toml` — five Anthropic ids prefixed, `default_route` updated, and the header INVARIANT
    comment corrected (it asserted the opposite rule and is what the declarations followed).
  - `tests/unit/test_declared_models_match_aigateway.py` — prefix table → provider name +
    `_canonical`; added `test_the_canonical_rule_prefixes_once_and_only_once` and
    `test_the_declared_default_route_is_a_declared_model`.
  - `tests/unit/test_local_benchmarks.py` — NEW, three cases for the benchmark decision.
  - `tests/unit/test_local_aigateway_connection.py` — flipped the one authorized assertion; added
    `test_an_explicit_url_points_the_catalog_at_the_same_gateway_as_connections`.
- **Gates:** `ALL GATES GREEN` — ruff check · ruff format --check · pyright · check_layering.py ·
  pytest with coverage (`1152 passed, 5 skipped`; coverage gate ≥80 met).
- **Acceptance verified against live services**, not just tests: with the fixed code, a plain
  `uv run url4-cloud serve --local` and **no env vars at all** returned `/v1/models` = 200 with 23
  models (previously 503), and `/openrouter/openai/gpt-5.5('What is 7+5?')` reached
  `terminated: succeeded` with body `12`. `/anthropic/claude-haiku-4-5` now fails with
  `profile_not_found` (no credential connected) instead of `aigateway_http_400`
  ("model must be provider-prefixed") — the id resolves; only the credential is absent.

### Deviations

1. **`run_gates.py --skip-append-only` was used.** The append-only check flags ANY `M` on a path
   matching `test_globs`, and this unit necessarily modified two prior test files. Both changes
   were put to the owner as Confidence-Gate decisions and approved BEFORE coding: the derived
   prefix rule (which cannot be done without editing `_SLUG_SOURCES` and its guard assertion) and
   the single `catalog is None` assertion that pinned defect 1. No prior test was weakened,
   skipped, or deleted — the suite grew from 1147 to 1152 passing.
2. **`url4.toml`'s header comment was corrected**, which the plan did not list. It stated the
   inverse rule ("Anthropic's ids are UNPREFIXED") and is the reason the declarations were wrong;
   fixing the ids while leaving the comment would have re-created the drift at the next edit.
3. **The `/v1/benchmarks` honesty problem is NOT fixed here.** Discovery still lists DRACO on a
   box where no assets are installed, so it advertises what execution would refuse. The chosen
   fork makes local mode install nothing by default, which removes the run failure but leaves
   discovery over-promising. Worth its own item.
4. **`create_local_app`'s `benchmarks` default changed** from `BUILTIN_BENCHMARKS` to `None`
   (resolved from the env). No in-repo caller passes the parameter, so this is source-compatible;
   an external caller relying on the implicit builtins would now need `URL4_BENCHMARK_ASSETS`.
