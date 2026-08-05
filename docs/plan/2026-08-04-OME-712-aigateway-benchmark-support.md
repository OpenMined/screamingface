# OME-712 AI Gateway benchmark support — certification plan

**Ticket:** OME-712
**Spec:** `docs/spec/2026-08-04-OME-712-aigateway-benchmark-support.md`

## Goal

Certify the independently reviewable AI Gateway layer between the URL4 runtime foundation and
URL4 Cloud benchmark runtime, correcting only evidence-backed defects.

## Review seams

1. Standard parameter declaration and validation.
2. OpenRouter request projection and canonical model settings.
3. Provider discovery HTTP route.
4. Migration CLI and local launcher process boundary.

## Phase 1 — Baseline and traceability

- [x] Reuse the existing OME-712 task mirror without changing Linear.
- [x] Record the Gateway-owned contract and create this ledger before new implementation work.
- [x] Attempt the canonical AI Gateway gate and record the environment blocker.

## Phase 2 — Review the original landing

- [x] Verify the benchmark model ids against the Engine definitions and live catalog.
- [x] Verify standard-parameter validation and OpenRouter projection, including negative cases.
- [x] Verify provider discovery authentication and response ownership.
- [x] Verify migration/launcher behavior without duplicating canonical settings.
- [x] Identify legacy fallbacks, duplicated policy, dead code, private cross-app tests, and stale
      docs.

## Phase 3 — Evidence-backed corrections

- [x] Add a failing behavior-level test before each required production correction.
- [x] Put new provider-discovery coverage in a new test module and avoid benchmark policy in the
      Gateway.
- [x] Obtain owner approval for the Confidence-Gate exception covering the inherited exact
      seed-list pin; no test is deleted, skipped, or weakened.
- [x] Re-run focused tests after every correction.

## Phase 4 — Certification

- [ ] Obtain an authoritative full gate on Linux after this branch is published. The local fresh
      environment cannot build the current LiteLLM 1.95 lock on macOS with Rust 1.92.
- [x] Complete the in-progress work ledger with files, counts, risks, and exact local evidence.
- [ ] Prepare the Gateway reviewer packet and proposed Linear/PR notes without publishing them.

## Explicit process deviations

- OME-712 remains one cross-cutting issue by owner direction; no cleanup issue is created.
- The final landing is stacked by explicit owner decision even though the repository guide
  normally prefers each PR to branch from `main`.
- The implementation predates this whole-layer spec; this pass certifies it before the upper
  URL4 Cloud layer is reviewed.
- The canonical macOS gate is environment-blocked: LiteLLM 1.95 has no compatible wheel on this
  machine and its source dependency requires Rust 1.94.1. Main's Linux AI Gateway workflow is
  green on Python 3.12 and 3.13; the unpublished branch still needs its own Linux run.
