# OME-400 — Full benchmark-run URL4 migration

**Status:** implemented and verified
**Date:** 2026-07-21
**Contract:** [`../spec/2026-07-21-OME-400-full-run-url4-contract.md`](../spec/2026-07-21-OME-400-full-run-url4-contract.md)

## Objective

Move benchmark slicing, Recipe execution, grading, and aggregation behind one reproducible URL4
request while keeping the ScreamingFace SDK responsible for typed authoring, validation, report
decoding, and notebook UX.

## Verified before implementation

- Refreshed the protected local `packages/url4` overlay from `OME-466-url4-serve` at
  `220fb5f01e49ba52367ea589eb6bc6deeaa8e2b8`.
- Confirmed current URL4 mandatory-intent behavior and identified the old compiler as incompatible.
- Executed a network-free GPQA-shaped full expression through `Url4Node`.
- Confirmed NDJSON collection decoding, half-open slicing, named bindings, model context/intent,
  reducer intent payloads, grader context/intent payloads, and reduce-over-iteration aggregation.
- Confirmed from Hugging Face's primary documentation that `HF_TOKEN` is the supported environment
  credential and overrides a machine-stored token.

## Implementation sequence

1. Migrate Recipe rendering and reducer adapters to mandatory-intent URL4.
2. Advertise and register versioned GPQA cases, exact-choice grader, and mean aggregator routes.
3. Load benchmark manifests from the configured engine.
4. Compile `Benchmark.evaluate(candidate, first=...)` into one full URL4 expression and decode one
   `screamingface.report.v1` plaintext response.
5. Remove the client-side execution fallback and update tests, Docker credentials, notebooks, and
   public documentation.
6. Record the production 7-solo/9-Fusion DRACO target and the unresolved generic named multi-root
   settlement requirement in a deterministic notebook for URL4 design review.

## Acceptance

- `first=1` evaluates only the first canonical GPQA row inside URL4.
- The SDK sends exactly one `/v1` request for the complete benchmark run.
- The response is a validated report and preserves the exact full expression as `Report.url4`.
- Missing or invalid engine dataset credentials fail safely without exposing the token.
- URL4's protected overlay remains absent from the commit diff.

## Verification

- SDK: 370 tests passed; 95.34% coverage; the one-request benchmark executor is at 100%.
- Engine: 238 tests passed; 95.51% coverage; benchmark cases, grader, and aggregator contracts are
  exercised independently and through one complete URL4 request.
- Generated notebooks are deterministic.
- Ruff and Pyright pass for both SDK and engine.

The design handoff is `packages/screamingface/examples/07_full_draco_url4.ipynb`. Its
`settle({...})` spelling is explicitly illustrative; it records the required generic semantics
without claiming that current URL4 accepts that grammar.

If at least one selected case succeeds, the engine returns a complete or partial paired report. If
every selected case fails, `/aggregators/mean/1` raises `benchmark_evaluation_failed`; the SDK does
not fabricate an all-`None` report.
