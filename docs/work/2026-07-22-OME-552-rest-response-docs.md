---
ticket: OME-552
stack: url4-cloud
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-552 — Document REST responses on GET / and DELETE /

## Intent

The two execution routes return a bare `Response`, so FastAPI emits no documented status codes, no
RFC 9457 Problem schema, and no response headers — Scalar renders them contract-less, undercutting
the §12 Scalar-grade goal. Add `responses=` metadata (reusing the existing `url4_cloud.auth.Problem`
model + `PROBLEM_MEDIA_TYPE`) **without changing runtime behaviour** (handlers still return
`Response`).

## Planned changes

- `src/url4_cloud/rest/routes.py` — import `Problem`, `PROBLEM_MEDIA_TYPE`; module-level response
  maps; `responses=` on `start_run` (200; 202 + `Location`/`Link`/`Preference-Applied` headers;
  400/409/428/502/504 → Problem) and `stop_run` (204; 403 → Problem).
- `tests/unit/test_docs_ops.py` — NEW test asserting the documented responses (append-only add).
- `docs/spec/2026-07-21-url4-cloud.md` §5 — note the responses are now documented.

## Test plan

- RED: GET / responses include 200/202/400/409/428/502/504; `Problem` in components referenced by
  409 (`application/problem+json`); 202 documents `Location`/`Link`/`Preference-Applied`; DELETE /
  includes 204 + 403 (Problem). Fails against the current bare-`Response` routes.

## Acceptance

- OpenAPI 3.1 still validates; the documented responses/headers/Problem appear; gates green.

## Outcome

- **Actual files:** `src/url4_cloud/rest/routes.py` (`_problem` helper + `_START_RESPONSES` /
  `_STOP_RESPONSES` maps + `responses=` on both routes; dropped the now-unused `Problem` import,
  kept `PROBLEM_MEDIA_TYPE`); `src/url4_cloud/schemas/openapi.py` (register `Problem` in
  `components.schemas`); `tests/unit/test_docs_ops.py` (+1 test, append); `docs/spec/…§5` note.
  Handlers unchanged — doc-only.
- **Commits:** see the OME-552 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` GREEN (ruff · format · pyright · pytest
  119 passed · cov ≥ 80). External: OpenAPI 3.1 `openapi-spec-validator` ✓; AsyncAPI 3.0
  `@asyncapi/cli` 0 errors. `--skip-append-only` covers a **pure test append** (rule 5: adding
  tests is always fine); nothing existing was modified.
- **Deviations:** FastAPI's `responses={..,"model":Problem}` forces an `application/json` variant
  and leaves a custom media type empty. Switched to a raw `application/problem+json` content with
  the `Problem` `$ref` and registered `Problem` in the OpenAPI customizer — accurate RFC 9457
  media typing, both validators green.
