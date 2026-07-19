---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Implement the Phase 2C compiler and Run stage

## Intent

Implement the separately approved Phase 2C contract without introducing grading, aggregation,
authentication, tools, persistence, retries, runtime mocks, or direct AI Gateway access.

## Delivered

- Canonical parameterized and concrete URL4 compilation through the public URL4 builder/AST
  facade and renderer.
- One complete expression and one `GET /v1?q=...` request per selected case.
- Registry-backed preflight and strict plaintext Fusion-result validation.
- Fixed four-way case concurrency, stable canonical ordering, and no automatic retries.
- Atomic typed case failures and immutable JSON-compatible run records.
- A real persistent-node integration test for SDK-generated expressions.
- A no-runtime-mock Docker smoke spanning public SDK -> persistent URL4 node -> AI Gateway.
- A clean-run CI dependency fix that installs the declared `datasets` extra before Pyright checks
  the nested engine application.

## Validation

- `uv run ruff check src tests apps/screamingface-engine/src apps/screamingface-engine/tests`
- `uv run ruff format --check src tests apps/screamingface-engine/src apps/screamingface-engine/tests`
- `uv run pyright src tests apps/screamingface-engine/src apps/screamingface-engine/tests`
- `146 passed` across the SDK and engine test suites.
- SDK coverage: `96.45%`; engine coverage: `98.09%`.
- Isolated Docker smoke passed at engine port `14404` and Gateway port `19105`; no provider
  credentials were present, so the expected Gateway failure was preserved as one atomic URL4 run
  failure with no partial member answers.

## Boundary

The implementation never calls AI Gateway directly from the SDK and contains no runtime response
mock. The controlled Gateway transport used by the persistent-node integration test verifies the
successful result contract deterministically; the Docker smoke verifies the real service topology
without claiming an authorized provider response.

## Outcome

- **Commits:** none; the user owns commit and push.
- **Deviations:** no public-contract deviations. Provider-authorized Docker success was not
  claimed because credentials were deliberately unavailable; both the success contract and the
  real credential-free topology are covered honestly.
