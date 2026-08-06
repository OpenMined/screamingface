---
ticket: OME-319
stack: repo
status: in_progress
started: 2026-08-05
finished:
---

# OME-319 — auditable Case Results

## Intent

Make every completed Evaluation auditable after its live stream ends by retaining the exact Case
input/output, output finish reason, Case Grade, Checks, raw and normalized Evidence, failures, and
attributable provenance through the Engine and SDK Report.

Linear remains unchanged during implementation per owner instruction. OME-319 is the lead existing
work item; OME-316 is the related per-Case inspection consumer. Their final scopes/statuses will be
proposed in the end-of-stack ticket audit.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/**` — produce complete Case Results.
- `apps/url4-cloud/src/url4_cloud/runner/**` — retain the existing model-response finish signal at
  the Candidate Invocation boundary without reconstructing results from the live event stream.
- `apps/url4-cloud/tests/unit/test_draco_case_artifacts.py` — public Engine tracer bullet.
- `packages/screamingface/src/screamingface/report.py` and result decoding — immutable SDK
  Case/Grade/Check/Evidence values.
- `packages/screamingface/tests/test_case_artifacts.py` — public SDK tracer bullet and boundaries.
- IFEval implementation/tests — same universal envelope.
- README and generated notebook documentation where the artifact interface is shown.

## Test plan

- Red first: complete DRACO smoke Case evidence survives ordinary Engine execution.
- Red first: a content-bearing Candidate response ending with `finish_reason="length"` remains
  gradeable and exposes `CaseResult.finish_reason == "length"`.
- Red first: the same literal survives SDK decoding and Report JSON.
- Boundaries: invalid Evidence, Case failures, duplicate ids, count/shape mismatch, immutable JSON.
- IFEval canonical and corrective Case evidence.

## Acceptance

- A completed local DRACO smoke Report can answer what was asked, what the Candidate produced, what
  was checked, what the Judge returned, how the selected output ended, and why it received its
  status.
- No Benchmark semantics in SDK compilation or decoding.
- Both layer gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** pending
- **Commits:** not committed
- **Gates:** pending
- **Deviations:** pending
