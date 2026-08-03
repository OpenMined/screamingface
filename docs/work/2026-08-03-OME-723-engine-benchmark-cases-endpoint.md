---
ticket: OME-723
stack: url4-cloud
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-723 — Serve paginated benchmark cases on the Engine control plane

## Intent

A researcher (SDK today, web frontend later) can read a benchmark's actual prompts
before spending money evaluating. One stable REST URL —
`GET /v1/benchmarks/{benchmark_id}/cases?limit=&offset=` — paginated, ETag-cached,
resolved generically through the `BENCHMARKS` registry + `assets_root(env)`. Spec:
`docs/spec/2026-08-03-OME-722-benchmark-researcher-discovery.md` Contract 1. Parent
epic `OME-722`; `OME-724` (SDK) is blocked on this contract.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/rest/benchmarks.py` — add the cases route beside the
  two catalog routes: limit 1..200 default 50, offset ≥0 default 0, out-of-range
  offset → empty `data`; body `{object, benchmark, revision, total, limit, offset,
  data:[{id, input}]}`; ETag/Cache-Control/304 via the existing `_response` helper;
  404 problem+json unknown id; 503 problem+json code `benchmark_unavailable` on
  missing/unreadable assets; pass through ONLY `id` + `input` (drop e.g. draco's
  `domain` column).
- `apps/url4-cloud/tests/unit/test_benchmark_cases_endpoint.py` — new test module
  (append-only: no existing test file touched).

## Test plan

RED first, in `test_benchmark_cases_endpoint.py` against the FastAPI app with a tmp
assets root (draco + ifeval fixture dirs, prepared-shape `cases.json`):

- happy path: defaults (limit 50, offset 0), body shape + total + data fields
- pagination math: limit slices, offset walks, out-of-range offset → empty data (200)
- limit/offset validation: limit 0, 201, negative offset → 422
- `default` alias resolves to the default benchmark (sibling-route parity)
- 404 unknown id (problem+json)
- 503 missing assets (problem+json, code `benchmark_unavailable`)
- ETag + If-None-Match → 304; different pages → different ETags
- INVARIANT (answer-key discipline): response objects contain exactly `id` + `input`,
  even when cases.json carries extra columns (`domain`)
- INVARIANT (asset/code drift): `total` equals the file's row count; a cases file
  whose count disagrees with `case_count` when fully installed is surfaced (assert
  `total` from file, not from the definition)

## Acceptance

- All new tests green; all prior url4-cloud tests green and unmodified
- `run_gates.py url4-cloud` green (ruff, format, pyright, layering, pytest+cov)
- Response never contains keys beyond `id`/`input`
- NO COMMIT — standing owner instruction (2026-08-03) to leave the tree dirty for
  manual review; commits happen after owner review alongside OME-719/720

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `rest/benchmarks.py` (route + `_case_rows` +
  `_problem` optional `code` extension member) and new
  `tests/unit/test_benchmark_cases_endpoint.py` (15 tests).
- **Commits:** NONE — standing owner instruction (2026-08-03, "don't commit anything
  yet, I want to manually review"); dirty tree for review alongside OME-719/720.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` ALL GREEN (ruff, format,
  pyright, layering, pytest 703 passed / cov ≥ 80). Append-only skipped because the
  flagged modifications are OME-719's uncommitted, pre-declared prior-test changes —
  this unit added one new test module and touched no prior test.
- **Deviations:** `_problem` gained an optional `code=` keyword (additive; 404 callers
  unchanged) to carry `benchmark_unavailable` as a problem+json extension member —
  spec asked for "503 problem+json `benchmark_unavailable`" without fixing the field.
