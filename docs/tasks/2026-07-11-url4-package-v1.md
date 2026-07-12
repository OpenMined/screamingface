---
id: OME-397
linear_url: https://linear.app/openmined/issue/OME-397/package-and-commit-url4-sdk-v1-under-sdlc
status: done
type: task
priority: P2
labels: [pkg/url4-python-sdk, Python SDK, autonomous, agentic, Feature]
created: 2026-07-11
closed: 2026-07-11
---

Package and commit the **url4 SDK v1** into the monorepo at `packages/url4` as one fresh,
SDLC-tracked unit. url4 is a standalone, framework-free core library for the url4 expression
protocol — `(sources)!intent` compiled into an executable DAG of typed nodes with I/O
inverted behind an `IOLayer` port. The code already exists; this unit packages the current
working state (base + in-flight modifications + new `src/url4/_annotations.py`, `tests/spec/`,
`tests/test_scan.py`) onto a fresh branch off up-to-date `main` without altering main history.
No re-development. Relationship: lands the package that the earlier deferred extraction item
`OME-367` anticipated.
