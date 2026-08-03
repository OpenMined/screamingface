---
ticket: OME-724
stack: repo
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-724 — Rich benchmark catalog and case browsing in the SDK + researcher notebook flow

## Intent

A researcher learns what a benchmark IS — title, description, size, real prompts —
through `sf.*` calls before spending money. `sf.benchmarks.list()` becomes a catalog of
rich frozen `Benchmark` values (breaking change, accepted in the spec: items were bare
strings), `sf.benchmarks.get(id)` picks one, `benchmark.cases(limit=, offset=)` pages
real prompts from OME-723's endpoint. Notebook 07 opens with the "Meet the benchmark"
flow. Spec: `docs/spec/2026-08-03-OME-722-benchmark-researcher-discovery.md` Contract 2;
parent epic `OME-722`; blocked-by `OME-723` (done, this branch).

## Planned changes

- `src/screamingface/discovery.py` — new frozen values `Benchmark` (id, title,
  description, revision, case_count + `.cases()` via a bound non-comparing fetcher
  field + `_repr_html_` card) and `CaseInfo` (id, input).
- `src/screamingface/_engine/catalog.py` — decode title/description (currently
  dropped); per-benchmark summary fetch `/v1/benchmarks/{id}?limit=1` for
  revision/total case_count; case-page fetch + decode
  `/v1/benchmarks/{id}/cases?limit=&offset=`; `Benchmarks.get` + `Benchmarks.cases`;
  async mirrors (`AsyncBenchmarks.get/.cases`); async-built values direct `.cases()`
  callers to `await client.benchmarks.cases(...)` via a typed PlanningError.
- `src/screamingface/_ui/catalog.py` — `_BenchmarkCatalog` over rich values;
  new `_CaseCatalog` carrying total/limit/offset.
- `src/screamingface/_ui/cards.py` — rich benchmark rows, case rows, single
  `benchmark_card_html`.
- `src/screamingface/benchmarks.py` — module-level `get()` beside `list()`.
- `src/screamingface/__init__.py` — export `Benchmark`, `CaseInfo`.
- `scripts/build_notebooks.py` + regenerated `examples/07_ifeval_e2e.ipynb` — "Meet
  the benchmark" section (list → get → cases(limit=3)) before the evaluate cells.
- Tests: new `tests/test_benchmark_browsing.py`; UPDATE (spec-approved breaking
  change, no compat shims): `tests/test_catalog_discovery.py`,
  `tests/test_rich_display.py`, `tests/test_public_interface.py` to the production
  shape.

## Test plan

RED first in `tests/test_benchmark_browsing.py` (httpx.MockTransport):

- `list()` returns rich `Benchmark` values decoded from catalog + per-id summary
- `get(id)` happy path; unknown id → `PlanningError` `unknown_benchmark`
- `.cases(limit, offset)` decodes rows, forwards paging params on the wire, exposes
  total/limit/offset; rows are `CaseInfo(id, input)` only
- error taxonomy: unreachable engine → `EngineUnavailableError`; 503 page →
  `PlanningError` non-permanent; malformed page JSON/shape → `PlanningError` permanent
  (no raw httpx errors leak — boundary defense invariant)
- async: `await client.benchmarks.list()/get()/cases()` mirror; async-built value
  `.cases()` raises the typed redirect error
- cards: catalog/`Benchmark`/case-catalog `_repr_html_` non-empty + HTML-escapes
  hostile input text
- `sf.benchmarks.get` delegates to the lazy default client
- updated prior tests keep the same invariants (decode rejection table, auth/error
  taxonomy) against the rich shape

## Acceptance

- New + full screamingface suite green; notebook builder + checker green
- SDK gates green (ruff, format, pyright, pytest; coverage ≥ pre-existing 94.78%
  baseline — the 95-bar shortfall predates this unit and is flagged to Keelan)
- Notebooks 00/05/06 unchanged; `sf.evaluate` untouched
- NO COMMIT — standing owner instruction (2026-08-03) to leave the tree dirty for
  manual review

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (discovery.py, _engine/catalog.py, _ui/catalog.py,
  _ui/cards.py, benchmarks.py, __init__.py, build_notebooks.py + regenerated
  examples/07, new tests/test_benchmark_browsing.py, updated
  test_catalog_discovery.py / test_rich_display.py / test_public_interface.py).
- **Commits:** NONE — standing owner instruction (2026-08-03) to leave the tree
  dirty for manual review alongside OME-719/720/723.
- **Gates:** SDK ruff + format + pyright green; pytest 377 passed;
  **coverage 95.00% — the 95 bar now PASSES** (pre-existing 94.78% shortfall
  flagged by OME-720 is cleared by this unit's fully-covered additions);
  `check_notebooks.py` green; url4-cloud suite re-run green (688 passed).
- **Deviations:**
  1. Prior-test updates (4 files) — pre-approved by the spec's accepted breaking
     change ("tests updated to production shape, no compat shims"); the decode
     rejection table and error-taxonomy invariants were preserved, fixtures gained
     title/description + summary routes.
  2. `test_public_interface.py`'s legacy-alias blocklist dropped "Benchmark" — the
     spec deliberately reintroduces the name as the rich discovery value; WHY
     comment left in the test.
  3. Summary fetch uses `?limit=1` per catalog entry (revision + total_case_count)
     instead of the unbounded resource — avoids the Engine rendering the full url4
     expression per catalog row. list() therefore costs 1 + N requests (N=2 today).
  4. Async-born `Benchmark.cases()` raises a typed redirect
     (`sync_cases_on_async_client`) pointing to `await client.benchmarks.cases(...)`
     — the spec specified only the sync surface; house async mirrors added on the
     adapter instead of an untyped sync-over-async bridge.
