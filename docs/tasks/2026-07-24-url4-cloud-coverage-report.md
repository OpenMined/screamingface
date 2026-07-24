---
id: OME-568
linear_url: https://linear.app/openmined/issue/OME-568/url4-cloud-ci-publish-coverage-report-test-report-checks-parity-with
status: done
type: task
priority: P3
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-24
closed: 2026-07-24
---

# OME-568 — url4-cloud CI: coverage report + test-report parity

Bring `.github/workflows/url4-cloud-tests.yml` to reporting parity with `aigateway`/`scoreboard`:
coverage `xml`/`term-missing`, an `orgoro/coverage@v3.2` PR coverage comment, a
`dorny/test-reporter@v2` JUnit check, a `cost:` CI cost-diff job, plus `permissions` +
`workflow_dispatch`. The `--cov-fail-under=80` gate is preserved. Lands in the existing PR #419.
Sub-issue of the url4-cloud app epic (`OME-513`). Ledger:
`docs/work/2026-07-24-OME-568-url4-cloud-coverage-report.md`.
