---
title: Originals-faithful benchmark failure handling
ticket: OME-807
status: approved
date: 2026-08-13
---

# Originals-faithful benchmark failure handling

## Outcome

URL4 Cloud publishes every trustworthy selected Case while distinguishing model behavior from
infrastructure failure and protocol corruption. A paid run keeps its valid Benchmark score over
the Cases that the Benchmark successfully graded and declares exactly how much of the selection
that score represents.

```text
Candidate/model response ──→ normal Benchmark checker ──→ numeric Case grade
Infrastructure failure   ──→ typed missing Case grade  ──→ excluded from score
Protocol corruption      ──→ loud error                ──→ no Candidate Result

numeric Case grades ──→ Benchmark scorer ──→ score
numeric / selected   ───────────────────────→ top-level coverage
```

This spec supersedes only the **Fail-closed finalization** policy in OME-802. Its strict typed
wire, exact Case identity, public-error privacy, and Benchmark-owned checking/scoring seams remain
in force.

## Deep module seam

`benchmarks.aggregation.finalize_candidate_result(...)` is the one failure-policy interface used
by DRACO, IFEval, and HealthBench. It:

1. validates the selected and produced Case identities;
2. retains every selected Case in selection order;
3. materializes a typed failed Case for one trustworthy missing identity;
4. partitions Cases by numeric grade versus missing grade;
5. calls the supplied Benchmark scorer with only the gradeable typed Cases;
6. publishes the Benchmark score and factual top-level coverage, or the explicit zero-coverage
   unscored shape.

The finalizer does not inspect Failure codes, retry operations, decide whether Benchmark evidence
is sufficient, impose a coverage floor, or reproduce Benchmark mathematics. Those behaviors stay
behind the Benchmark scorer/evaluator adapter.

## Failure policy

### Candidate/model behavior

An explicit refusal, empty output, garbage answer, or text that fails a deterministic checker is
model-authored behavior. The Benchmark's normal checker receives the exact text and determines the
normal Case grade. Any numeric grade participates in the score and coverage.

A provider-declared refusal retains distinct public truth:

```text
status="refused"
refusal=<exact provider text>
output=None
grade=<normal Benchmark grade>
failures=[]
```

If later grading infrastructure fails, the same refused Case retains its refusal but has
`grade.score=None` and one or more safe grading Failures. Refusal is never inferred from answer
text and is never assigned a universal zero.

The generic Candidate Invocation decoder therefore returns both an evaluator-facing answer and
the original refusal metadata. Benchmark routes use the evaluator-facing text exactly as they use
a normal Candidate answer; the final public Case still distinguishes output from refusal.

### Harness/infrastructure failure

A provider or transport failure after explicit retries, Judge failure, or one trustworthy missing
Case row produces a typed Case with `grade.score=None` and a safe Failure. It is excluded from the
Benchmark scorer and lowers coverage. It never becomes a plausible numeric zero.

Retries remain explicit on replayable URL4 Candidate/evaluator operations. Aggregation sees only
terminal outcomes.

### Protocol corruption

Duplicate or surplus Case rows, forged or mismatched identities, malformed internal envelopes,
and identity-less positional ambiguity raise loudly and produce no Candidate Result. A missing
row is recoverable only when the selection still identifies the missing Case unambiguously.

## Candidate Result V1

The unreleased `screamingface.candidate-result.v1` contract evolves in place:

- `coverage` is a required top-level finite number in `[0, 1]`.
- `coverage = round(number of Cases with numeric grade / selected Cases, 4)`.
- A numeric grade counts even when the Case status is `refused`.
- With at least one gradeable Case, `score` is the Benchmark scorer's result over only gradeable
  Cases and Benchmark metrics are preserved.
- With no gradeable Cases, `score=None`, `coverage=0.0`, and `metrics={}`.
- A scored Candidate may retain failed Cases and safe Candidate-level Failures excluded from its
  score.
- NaN is not a missing-value representation internally or on the wire.
- Failure tiers are not public fields; numeric grade, typed missing grade plus Failure, or a raised
  protocol error already encode the distinction.

The canonical vocabulary is:

- `score`: the Benchmark's headline result;
- top-level `coverage`: selected Cases represented in that score;
- optional `metrics.pass_rate`: a Benchmark-specific fraction of evaluated checks that passed;
- optional `metrics.verdict_coverage`: completeness of expected Judge/rubric verdicts.

Generic `metrics.coverage` is removed because it previously represented different quantities in
different Benchmarks. The Engine reports factual coverage and applies no publication threshold;
leaderboard eligibility is a separate downstream policy.

## Benchmark invariants

- IFEval keeps its official deterministic instruction checks and strict/loose scoring.
- DRACO keeps its selected criteria, multi-pass Judge Evidence, and reference score computation;
  its Engine-side 95% Candidate publication floor is removed.
- HealthBench keeps its penalty-bearing rubric grades and unclipped mean.
- Fully successful runs remain numerically identical to their pre-OME-807 results.
- Only the Benchmark decides when its Case has enough valid Evidence to carry a numeric grade.

## Public-error privacy

URL4 Cloud is the sole public-wire privacy seam. It preserves Candidate-authored output and exact
refusal evidence, but bounds and sanitizes infrastructure Failure code, message, retryability, and
explicit metadata. Raw exceptions, stack traces, credentials, filesystem paths, and arbitrary
provider dictionaries never reach JSON. Coverage includes regression tests for Unix and Windows
paths and common `key=value` secret forms.

The Python Client performs no duplicate scoring, policy classification, or sanitization. OME-694
strictly decodes and presents this producer contract after OME-807 lands.

## Compatibility and exclusions

This is an in-place unreleased V1 migration. Do not add a V2 schema, legacy aliases, dual
writers/readers, migrations, fallbacks, or shape inference.

Excluded:

- Benchmark-card or advertised-check-capability redesign;
- Benchmark Variant removal and CorrectiveLoop/SelfCorrective Recipes;
- configurable failure policies, retry orchestration, or coverage thresholds;
- leaderboard admission policy;
- unrelated Benchmark cleanup.
