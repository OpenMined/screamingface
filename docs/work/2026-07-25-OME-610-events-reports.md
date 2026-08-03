---
ticket: OME-610
stack: screamingface
status: blocked
started: 2026-07-25
finished:
---

# OME-610 — Implement typed Events and Reports

## Intent

Expose one immutable Event model and one Report shape for one or many independently executed
Candidates.

## Implemented

- Strict Event, Failure, Usage, MemberResult, CandidateResult, and Report values.
- Public `BenchmarkInfo` reused by Plans and Reports, with explicit selected `case_count`.
- Ordered/name Candidate lookup, `.only`, partial-Failure evidence, and portable JSON.
- Canonical Candidate-result URL4 and stable Operation-reference validation.

## External gate

Terminal decoding awaits the versioned Candidate-result schema and stable Operation/Event
attribution contract. The Client never calculates Engine-owned scores, aggregation, missing
usage, or shared-cost allocation. Candidate-inclusive totals may overlap; the Report requires an
Engine-provided de-duplicated Evaluation total and otherwise leaves total usage unavailable.

## Verification

Covered by Event, Report, value-validation, and Engine-contract tests plus the OME-605 package
gate. Implemented in `8451da41 feat(screamingface): establish v1 plan and run client contract`.
