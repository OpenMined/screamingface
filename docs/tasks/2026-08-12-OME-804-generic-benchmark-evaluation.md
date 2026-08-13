---
title: Extract generic benchmark evaluation capabilities in URL4 Cloud
ticket: OME-804
status: Done
date: 2026-08-12
closed: 2026-08-13
parent: OME-801
blocked-by: OME-802
---

# OME-804 — Extract generic benchmark evaluation capabilities in URL4 Cloud

## Goal

Deepen the URL4 Cloud Benchmark module so DRACO, IFEval, and HealthBench compose the same
Case-selection, Candidate-invocation, error-collection, Case-evaluation, and Aggregation
capabilities while retaining their irreducible data, evaluator, prompt, and scoring semantics.

## Delivery

Development occurs on `OME-804-benchmark-execution`, rebased onto `origin/main` after prerequisite
OME-802 PR #572 merged. The branch contains one OME-804 commit above that merged prerequisite and
is delivered as one ordinary, unstacked PR.

## Acceptance

- The complete installed Benchmark URL4 remains the Evaluation and test seam.
- Successful protocol behavior remains pinned by independent DRACO, IFEval, and HealthBench
  fixtures.
- Shared mechanics live outside Benchmark-specific directories.
- Benchmark-owned checker, Judge, prompts, grading, and score mathematics remain local.
- No manifest DSL, second runner, arbitrary Python, compatibility fallback, or schema version is
  introduced.
