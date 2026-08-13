---
title: Consume partial benchmark results and graded refusals
ticket: OME-694
status: approved
date: 2026-08-13
---

# Consume partial benchmark results and graded refusals

## Outcome

The Python Client strictly consumes the OME-807 `screamingface.candidate-result.v1` producer
contract. One immutable `CandidateResult` exposes the Engine-declared score and factual coverage,
while every selected Case remains available as scored, refused, or failed.

The Client validates and presents untrusted wire data. It does not calculate coverage, rescore
Cases, classify failure tiers, sanitize Engine errors, or impose a publication threshold.

## Candidate Result interface

`sf.CandidateResult` gains required `coverage: float`, a finite number in `[0, 1]`. It is preserved
as a top-level field by `to_dict()`, `Report.to_dict()`, `Report.to_json()`, and `Report.export()`.

The strict decoder requires the Engine's exact top-level fields, including `coverage`. Missing,
unknown, non-numeric, non-finite, or out-of-range values fail with `ExecutionError`. The Client
does not verify coverage by counting grades; the Engine remains authoritative for that derived
fact.

Generic `metrics.coverage` is unsupported. Benchmark metrics remain an open immutable JSON
mapping, including optional values such as `pass_rate` and `verdict_coverage`. A numeric score may
coexist with typed Candidate- or Case-level Failures because the Engine may score the gradeable
subset. An unscored Candidate still requires empty metrics.

## Case outcomes

The Client mirrors the revised producer invariants:

- `scored`: output, numeric grade, no refusal, no Failures;
- `refused` and graded: exact refusal, `output=None`, normal numeric Benchmark grade, no Failures;
- `refused` and ungraded: exact refusal, `output=None`, `grade.score=None`, one or more safe
  grading Failures;
- `failed`: one or more Failures, no refusal, and no numeric grade.

Direct Python construction derives `refused` whenever refusal text is present, even when the Case
has a numeric grade. The wire decoder always requires explicit status. Provider refusal is no
longer represented as a synthetic Candidate-stage `provider_refusal` Failure.

## Presentation

The Report card reads coverage from `candidate.coverage`, never from metrics. A score with
coverage below 100% is shown as a partial evaluation and clearly states that the score represents
only the Engine-graded portion. A zero-coverage unscored result explains that no selected Case was
gradeable. Refused Cases retain their warning identity, exact refusal, normal grade/checks, and
any later grading Failure.

The obsolete Client `CoverageWarning` and `metrics.coverage`/`coverage_target` interpretation are
removed. Coverage is factual result data, not a Client-enforced Benchmark publication policy.

## Compatibility and exclusions

This is an in-place migration of the unreleased V1 interface. Do not add optional defaults,
legacy aliases, dual readers, fallbacks, inferred coverage, or a second result type.

Excluded:

- Engine aggregation, checking, scoring, or sanitization;
- leaderboard admission policy or partial-score submission changes;
- runtime usage/attribution work owned by OME-699;
- CorrectiveLoop/SelfCorrective and benchmark capability work owned by OME-796;
- unrelated notebook rewrites.
