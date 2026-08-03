# Benchmark researcher discovery — spec (OME-722)

Status: DRAFT — awaiting owner approval
Tickets: OME-722 (epic) · OME-723 (url4-cloud) · OME-724 (py-screamingface)

## Goal

A researcher in a notebook learns what a benchmark is — title, description, size, and the
actual prompts — through `sf.*` calls only, before spending money evaluating. The Engine
contract is plain paginated REST so the future web frontend reuses it unchanged.

## Non-goals

- No answer keys, instruction specs, or grading kwargs ever leave the Engine.
- No changes to `sf.evaluate(...)`, the url4 execution path, or notebooks 00/05/06.
- No search/filter server-side; pagination only (client-side filtering is the card
  widget's job at these sizes).

## Contract 1 — Engine REST (OME-723)

`GET /v1/benchmarks/{benchmark_id}/cases?limit=&offset=`

- `benchmark_id`: catalog id or `default` (same alias rule as the sibling route).
- `limit`: 1..200, default 50. `offset`: ≥0, default 0. Out-of-range offset → empty
  `data`, not an error.
- 200 body:

```json
{
  "object": "list",
  "benchmark": "ifeval",
  "revision": "047f1de449639c61…",
  "total": 541,
  "limit": 50,
  "offset": 0,
  "data": [{"id": 1, "input": "Write a 300+ word summary…"}]
}
```

- Source: the family's prepared `cases.json` under the assets root — the same file the
  runtime serves; fields passed through are exactly `id` + `input`.
- ETag + `Cache-Control: public, max-age=300, must-revalidate` + 304 handling identical
  to the sibling catalog routes (ETag over the serialized page).
- 404 problem+json for unknown id (existing `_problem` helper). Missing assets → 503
  problem+json `benchmark_unavailable` (mirrors the node-route error code).
- Generic: resolved via the `BENCHMARKS` registry + `assets_root(env)`; zero
  family-specific code.

## Contract 2 — SDK (OME-724)

```python
import screamingface as sf

sf.benchmarks.list()          # BenchmarkCatalog — interactive cards: title, id,
                              #   description, case count. Sequence[Benchmark].
b = sf.benchmarks.get("ifeval")   # Benchmark (also catalog[i] / iteration)
b                              # card: title, description, revision, case_count
b.cases(limit=5)               # CaseCatalog — cards: case id + prompt text
b.cases(limit=5, offset=100)   # paging
```

- `Benchmark` is a frozen value: `id`, `title`, `description`, `revision`,
  `case_count` — decoded from the existing `/v1/benchmarks` + `/v1/benchmarks/{id}`
  payloads (title/description are already served and currently dropped by the SDK).
- `.cases()` is lazy — hits OME-723's endpoint on call; raises the SDK's existing
  `EngineUnavailableError` / `PlanningError` taxonomy on failure (defend at the
  boundary, no raw httpx errors).
- Rendering reuses `_Catalog` / card infrastructure (`_ui/catalog.py`, `_ui/cards.py`);
  plain-text `repr` stays informative outside notebooks (frontend-agnostic values,
  presentation only in `_ui`).
- **Breaking change (accepted):** `sf.benchmarks.list()` items become `Benchmark`
  values, not `str`. Pre-v1 SDK, only internal consumers; tests updated to production
  shape, no compat shim.

## Notebook (OME-724)

`07_ifeval_e2e.ipynb` (authored in `build_notebooks.py`, gated by
`check_notebooks.py`) gains a "Meet the benchmark" section before evaluation:

1. `sf.benchmarks.list()` — discover
2. `ifeval = sf.benchmarks.get("ifeval")` — pick, show the card
3. `ifeval.cases(limit=3)` — read real prompts (markdown cell explains the
   machine-checkable-constraints idea using the shown prompts)
4. existing evaluate cells unchanged

## Testing (invariants)

- Engine: pagination math (limit/offset/total), ETag/304, 404 unknown, 503 missing
  assets, response never contains keys beyond `id`/`input` (answer-key discipline),
  works for both `draco` and `ifeval` fixtures.
- SDK: catalog decodes title/description, `.cases()` decodes + paginates, error
  taxonomy on unreachable engine, card render smoke (`_repr_html_` non-empty), notebook
  builder/checker green.

## Sequencing

OME-723 first (contract), OME-724 blocked on it. Both on this worktree's branch lane,
conventional commits `Refs: OME-N`.
