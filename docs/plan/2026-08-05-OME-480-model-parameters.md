---
title: OME-480 URL4 Cloud model-details proxy — implementation plan
status: approved
created: 2026-08-05
ticket: OME-480
spec: docs/spec/2026-08-05-OME-480-model-parameters.md
ledger: docs/work/2026-08-05-OME-480-model-parameters.md
---

# OME-480 implementation plan

Branch `OME-480-model-parameters`, stack `url4-cloud`, based directly on `origin/main`.

## Slice 1 — upstream adapter

- Add a model-parameter source port without widening the catalog source contract.
- Fetch the canonical model query using the existing verified identity/profile headers.
- Preserve valid v1 documents and caller-correctable `4xx`; reject unsafe upstream failures and
  malformed/mismatched success documents.
- RED first through an `httpx.MockTransport` public adapter seam.

## Slice 2 — Engine route

- Delegate uncached detail reads through the existing production service/client lifecycle.
- Add an injectable model-parameter dependency and public route.
- Apply private/no-store and identity/profile `Vary` to every result.
- RED first through the ASGI endpoint seam, including OpenAPI and unconfigured/failure paths.

## Verification

- Focused new test module while iterating; existing test files remain unchanged.
- `python3 .claude/scripts/run_gates.py url4-cloud` from the repository root.
- Final `origin/main...HEAD` scope and secret-leak review.

No SDK, AI Gateway, URL4, Benchmark, cache-setting, or provider-policy change belongs here.
