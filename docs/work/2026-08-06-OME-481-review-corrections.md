---
ticket: OME-481
stack: screamingface
status: complete
started: 2026-08-06
finished: 2026-08-06
---

# OME-481 — review corrections for model parameters

## Intent

Ensure local Candidate/Benchmark compilation fails before any model-catalog request.

Linear state is intentionally unchanged until the final review packet, per owner direction.

## Changes

- Reorder synchronous and asynchronous Evaluation planning so local compilation precedes model
  catalogue loading.
- Add focused synchronous and asynchronous regression tests proving an unavailable catalogue
  cannot mask a local Candidate-shape error.

The proposed general string-parameter encoding work was dropped. The `stop="END,STOP"` example
was reviewer-generated rather than an OME-481 acceptance requirement, and structural parameter
values already fail early at Candidate construction instead of leaking a URL4 `RenderError`.

## Test plan

- A locally invalid Candidate fails without calling the model catalogue, synchronously and
  asynchronously.
- Run focused tests and the ScreamingFace package gate.

## Acceptance

- Local planning errors cannot be masked by model-catalog availability.
- No paid transport begins after any planning or preflight failure.

## Outcome

The synchronous and asynchronous launch paths now compile and link the Candidate locally after
fetching the selected Benchmark and before loading the model catalogue. Both regression tests pass;
the complete ScreamingFace suite passes with 555 tests and 14 skips.
