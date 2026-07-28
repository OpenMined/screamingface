---
ticket: OME-568
stack: url4-cloud
status: done
started: 2026-07-24
finished: 2026-07-24
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

- **Actual files:** `.github/workflows/url4-cloud-tests.yml` (added `permissions` +
  `workflow_dispatch`; expanded the pytest step with `--tb=short --junitxml`
  `--cov-report=xml --cov-report=term-missing`; added `dorny/test-reporter@v2`,
  `orgoro/coverage@v3.2`, and the `cost:` job) — matches planned. Plus this ledger + the
  `docs/tasks/` mirror.
- **Commits:** `2567658` — `ci(url4-cloud): publish coverage report + test-report checks`
  (pushed to `OME-513-url4-cloud`, PR #419).
- **Gates:** YAML valid (`yaml.safe_load` OK; `actionlint` not installed locally). Workflow
  ran **GREEN** on PR #419 — pull_request run `30090713374`: `test (3.12)` 30s, `test (3.13)`
  37s, `CI cost diff` pass. The **coverage comment posted** (`github-actions[bot]` → "☂️
  Python Coverage", 2026-07-24T11:46:53Z); the `dorny/test-reporter` JUnit check published;
  the `--cov-fail-under=80` gate is preserved. No app/python source changed → `run_gates`
  categories unaffected; the app suite stays green.
- **Deviations:**
  - **No TDD RED/GREEN** — CI workflow YAML, not Python; the gate is YAML validity + the
    workflow running green on the PR. Ledger + task-management process still applied.
  - **`cost:` job logs a benign 403** posting its PR comment ("Resource not accessible by
    integration"). This is **identical to aigateway** (whose `CI cost diff` job also concludes
    `success`): the org's restricted default `GITHUB_TOKEN` prevents the `HupBaHa/cost-diff`
    action from writing the comment; a job-level `permissions` block can only narrow, not
    elevate. The job still passes. Pre-existing, repo-wide, not introduced here — out of scope
    for OME-568. Possible future repo item: raise default workflow token permissions or drop
    the cost-diff comment step.
  - **Node.js 20 deprecation** annotation is repo-wide (every action), non-blocking.
