---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Implement Phase 3B grading values and ExactChoice

## Intent

Implement the reviewed deterministic foundation for grading without exposing a half-supported
`Run.grade()` method. Add the final immutable grading records, port the proven ExactChoice parser,
and make execution preflight share the exact same reference validator. Do not introduce Rubric
judge traffic, aggregation, `Fusion.evaluate()`, or engine-profile behavior.

## Changes

- Added immutable `Grades`, `CaseGrades`, `Grade`, `CriterionVerdict`, and `GradeFailure` public
  values with defensive mappings, stable ordering, strict valid/invalid-state invariants, and
  JSON-compatible serialization.
- Preserved both detailed criterion failures and target-summary failures without converting
  missing evidence into zero scores.
- Ported only the focused ExactChoice answer parser from the benchmark harness: A–J choices,
  explicit final-answer markers, decorated choices, guarded prose choices, numeric strings, and
  normalized full-text equality.
- Required canonical ExactChoice references to be non-empty strings. Literal integer references
  are rejected so the SDK never guesses zero-based versus one-based index semantics.
- Reused that validator in Phase 2C run preflight so execution and later grading cannot disagree
  about whether a reference is valid.
- Exported the grading values at the top-level `screamingface` namespace.

## Boundaries

- `Run.grade()` remains absent until Phase 3C can support both ExactChoice and Rubric.
- ExactChoice makes no engine request.
- No screamingface-engine, URL4, AI Gateway, Docker, notebook, reducer, compiler, aggregation,
  authentication, persistence, or public execution-policy behavior changed.

## Verification

- 91 focused Phase 3B tests pass; `_exact_choice.py` has 100% focused coverage and `grades.py`
  has 97% focused coverage.
- 188 SDK tests pass with 96.77% total coverage against the required 95% threshold.
- 49 isolated screamingface-engine tests pass with 98.09% coverage; no engine file changed.
- Full owned-path Ruff lint/format and package Pyright pass.
- Phase 0 fixture construction, deterministic Phase 1 notebook regeneration, public-import smoke,
  and wheel/sdist builds pass.

## Outcome

- **Runtime:** Phase 3B complete.
- **Public execution:** unchanged at `Fusion.run()`; no partial grading method exposed.
- **Next review:** Phase 3C Rubric protocol and complete `Run.grade()` dispatch.
