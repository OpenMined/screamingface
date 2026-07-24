---
ticket: OME-568
stack: url4-cloud
status: in_progress
started: 2026-07-24
finished:
---

# OME-568 — url4-cloud CI coverage report + test-report parity

## Intent

`url4-cloud-tests.yml` **enforces** coverage (`--cov-fail-under=80`) but does not **report**
it — a gap vs the `aigateway`/`scoreboard` lanes. On PR #419 the checks go green but no
coverage/test annotation is posted. Bring the lane to reporting parity so this PR (and every
future url4-cloud PR) gets a coverage comment + a JUnit test-report check. Lands in the
existing PR #419.

## Planned changes

- `.github/workflows/url4-cloud-tests.yml`:
  - add `permissions: { contents: read, checks: write, pull-requests: write }` +
    `workflow_dispatch:` trigger.
  - pytest step: add `--tb=short`, `--junitxml=results.xml`, `--cov-report=xml:coverage.xml`,
    `--cov-report=term-missing` (keep the 4 `--cov=` targets + `--cov-fail-under=80`; `-v`).
  - add `dorny/test-reporter@v2` (JUnit check, `if: always()`).
  - add `orgoro/coverage@v3.2` (PR coverage comment, `thresholdAll: 0.80`,
    `if: always() && github.event_name == 'pull_request'`).
  - add the `cost:` CI cost-diff job mirroring aigateway.

## Test plan

- YAML parses (`yaml.safe_load`); `actionlint` clean if available.
- No app/python source changed → `run_gates` categories (ruff/pyright/pytest) unaffected; the
  app suite stays green (unchanged).
- Runtime verification: the workflow runs on PR #419 (self-triggers via its own path filter)
  and produces a coverage comment + a test-report check; the 80% gate is still enforced.

## Acceptance

`url4-cloud-tests.yml` valid YAML mirroring aigateway's reporting (coverage `xml`/`term-missing`,
coverage PR comment, JUnit test-report check, cost-diff job); 80% gate preserved; pushed to
PR #419; CI green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:** **No TDD RED/GREEN** — this is a CI workflow (GitHub Actions YAML), not
  Python code, so there is no unit test to drive it; the gate is YAML validity + the workflow
  running green on the PR. Ledger + task-management process still apply.
