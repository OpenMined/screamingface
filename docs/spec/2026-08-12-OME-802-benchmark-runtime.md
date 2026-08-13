---
title: Generic benchmark outcome and scoring runtime
ticket: OME-802
status: approved
date: 2026-08-12
---

# Generic benchmark outcome and scoring runtime

## Outcome

URL4 Cloud exposes one deep Benchmark result module shared by DRACO, IFEval, and HealthBench.
Candidate construction remains independent: the Client compiles any compatible complete Recipe
into `$candidate`; the Engine-owned Benchmark URL4 invokes it, evaluates the answer, and produces
one strict Candidate Result.

```text
Client Recipe → complete $candidate
                         │
Cases → Candidate Invocation → evaluator adapter → Case Grade → generic finalization
                                                                │
                                                                ▼
                                                       Candidate Result
```

URL4 remains the only executable graph representation. This work adds neither a YAML orchestration
DSL nor another runner.

## Module seam

The public producer seam consists of:

- `EvidenceProducer`, `Evidence`, `Check`, `CaseGrade`, `Failure`, `CaseResult`, and
  `CandidateResult` strict Pydantic values in `benchmarks.contract`.
- `finalize_candidate_result(...)` in `benchmarks.aggregation`, which owns ordered coverage and
  fail-closed Candidate finalization.
- A Benchmark scorer callable that receives the complete ordered scored Cases and returns the
  Benchmark's primary score plus canonical and Benchmark-specific metrics.

The scorer varies because the published mathematics genuinely vary. IFEval maps deterministic
instruction checks into strict/loose accuracy; DRACO combines multi-pass rubric scores; HealthBench
uses an unclipped penalty-bearing rubric mean. The finalizer does not pretend these are one formula.

Registered runtime routes remain URL4 adapters. A route parses one request into a typed value and
returns a typed value; Benchmark directories own only their data, evaluator semantics, and scorer.
Do not add a route solely to wrap one Python helper that URL4 does not need to address.

## Candidate invocation

`/benchmarks/candidate` remains the one structural Candidate seam. Its result preserves:

- `output: str`
- provider `finish_reason: str | null`
- exact provider `refusal: str | null`

`finish_reason` is open non-blank provider text, not an SDK-owned enum. A new provider reason must
survive the wire unchanged rather than requiring an Engine release.

A Benchmark adapter must never turn a refusal into an incorrect answer or discard its exact text.
The adapter converts it into a refused Case Result and skips grading for that Case. It does not
silently inject the Benchmark evaluator into Candidate construction.

## Strict Case outcomes

Every selected Case has exactly one `CaseResult` with stable `case_id`, public input, Candidate
output, finish reason, refusal, optional grade, failures, and public metadata.

`status` is closed:

- `scored` — `grade.score` is present; `refusal` is null; `failures` is empty. A score of zero is
  still a successfully graded, potentially incorrect answer.
- `refused` — exact `refusal` is present; `grade` is null; output is null; one Candidate-stage
  `provider_refusal` Failure explains the missing answer.
- `failed` — one or more typed Failures explain why the Case did not produce a score. Partial
  grading evidence may remain in `grade`, but `grade.score` is null and `refusal` is null.

There is no unexplained generic `unscored` state. A selected Case without a score must say whether
it was refused or failed. Refusal is never inferred from output text.

`case_id` is stable identity, not tuple position. The producer permits a non-blank string or a
non-boolean integer so future Benchmarks do not have to renumber official identifiers.

## Evidence and grading

- A `Check` is one named requirement with ordered Evidence, optional normalized outcome/score, and
  public metadata.
- `Evidence` identifies its model or deterministic producer, preserves exact raw output, and says
  whether that output was accepted. Accepted Evidence may carry outcome and explanation; rejected
  Evidence retains its rejection metadata.
- A `CaseGrade` names the method, carries an optional score, open metrics, and ordered Checks.
- Metadata and Benchmark-specific metrics stay open JSON mappings; structural envelope keys are
  closed and unknown fields fail producer construction. “JSON” is enforced at producer
  construction: sets, custom objects, non-finite floats, and other non-wire values fail there.

Public Benchmark criteria, scoring weights, Judge evidence, and bounded operational diagnostics
remain available so a Client can explain every outcome. Credentials, genuinely non-public answer
keys, hidden reasoning, stack traces, and internal filesystem paths never enter the public result
merely because the producer models can represent open metadata. Failures retain safe codes and
messages; sensitive implementation detail is sanitized rather than all diagnostics being removed.

## Fail-closed finalization

`finalize_candidate_result(...)` receives the immutable Benchmark identity, ordered selected Case
Results, optional Candidate-level Failures, and one scorer adapter.

- It preserves every Case in supplied order and rejects duplicate Case identity.
- It calls the scorer only when every Case has `status="scored"` and there are no Candidate-level
  failures.
- Otherwise it returns `score: null` and `metrics: {}` without invoking the scorer.
- A scored result must publish numeric `score` plus `pass_rate` and `coverage` in `[0, 1]`.
- Benchmark-specific metrics remain alongside the canonical metrics.
- Operational failure and refusal never become benchmark zeroes.

Canonical Benchmarks therefore fail closed on any missing required Case. If a future official
Benchmark explicitly permits partial scoring, that is a different immutable Benchmark protocol
and requires an explicit finalization policy rather than weakening the default.

“Complete” here means that every selected Case has a numeric score accepted by that Benchmark's
own protocol; it does not impose universal 100% evaluator-evidence coverage. DRACO, for example,
accepts a scored Case at its reference 95% Judge-coverage floor and exposes the missing Evidence in
its metrics. IFEval and HealthBench require complete checks for a scored Case. There is no generic
`partially_scored` status: rejected partial grading remains auditable with `grade.score: null`.

## Benchmark adapters

- IFEval retains its official deterministic instruction verifier and strict/loose score mapping.
- DRACO retains rubric selection, multi-pass Judge evidence validation, and reference aggregation.
- HealthBench retains its rubric Judge, point/penalty rules, and unclipped challenge metric.

Common structure—Case outcome validation, refusal/failure preservation, exact coverage, and final
Candidate construction—must not be recopied into those adapters.

## Preflight and replay

Benchmark installation continues validating immutable assets and statically resolvable URL4 routes
without spending. The complete Engine-owned benchmark URL4 continues to be published and becomes
self-contained after the Client binds `$candidate`; direct URL4 execution and `sf.evaluate(...)`
therefore use the same runtime.

Every score-affecting Benchmark data, evaluator, scorer, or protocol change changes the Benchmark
revision. The result wire itself remains the unreleased `screamingface.candidate-result.v1`.

## Pre-release compatibility

There has been no public Client/Engine release for this contract. Evolve v1 directly into this
final strict shape. Do not add a v2 schema, legacy models, deprecated keys, aliases, migrations,
dual writers/readers, or shape inference fallbacks.

## Exclusions

- Client Report decoding and presentation (OME-803).
- CorrectiveLoop and Candidate control strategies (OME-796).
- Dynamic operation occurrence, timing, usage, cost, and cache attribution.
- Arbitrary user Python and manifest-defined execution graphs.
- One universal scoring formula that changes published Benchmark semantics.
