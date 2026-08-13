---
title: Consume normalized benchmark Case outcomes in the Python Client
ticket: OME-803
status: approved
date: 2026-08-13
---

# Consume normalized benchmark Case outcomes in the Python Client

## Outcome

The Python Client consumes the strict `screamingface.candidate-result.v1` contract produced by
OME-802 without re-deriving Benchmark semantics. Every selected Case keeps its stable identity,
explicit outcome, exact provider refusal, partial grading evidence, and typed failure diagnostics
through decoding, lookup, report export, and notebook presentation.

The Engine remains the source of truth for Benchmark outcomes. The Client validates an untrusted
wire and presents it; it does not decide whether an answer passed a Benchmark.

## Wire boundary

Every decoded Case requires exactly these nine fields:

- `case_id`
- `input`
- `output`
- `finish_reason`
- `grade`
- `failures`
- `metadata`
- `status`
- `refusal`

Unknown or missing fields fail with `ExecutionError`. `case_id` accepts a non-blank string or a
non-boolean integer because it is Benchmark identity, not a sequence offset. `status` is one of
`scored`, `refused`, or `failed`.

Nested Failure values consume the OME-802 wire exactly: `stage`, `code`, `message`, `retryable`,
`case_id`, and `metadata`. Candidate-level failures cannot claim a Case identity. No legacy wire
shape, alias, or inference fallback is accepted.

Nested Case Grade, Check, Evidence, and Evidence Producer values also mirror the producer's closed
fields, numeric bounds, outcome vocabularies, and open non-empty producer type. Exact wire text is
preserved; validation never trims identifiers, explanations, refusal text, or failure messages.

## Public Case values

`sf.CaseResult` exposes `status` and `refusal`, preserves string and integer Case identifiers, and
serializes the complete outcome losslessly. Direct Python construction may omit `status`; the
constructor derives it only to keep ordinary value authoring concise. This convenience is not a
wire compatibility path: the result decoder always requires the explicit Engine field.

The Client mirrors the current OME-802 structural invariants:

- `scored` has an output and numeric grade, with no refusal or failures.
- `refused` has exact refusal text, no output or grade, and exactly one Candidate-stage
  `provider_refusal` Failure.
- `failed` has one or more Failures, no refusal or numeric grade, and may retain a grade whose
  score is null as partial grading evidence.

The OME-807 scoring-policy change is deliberately separate. When that producer contract lands,
the consumer and its tests change together rather than anticipating two accepted wire meanings.

## Case collection and export

`CandidateResult.cases` remains an ordered immutable sequence. Position and identity are distinct:
callers use `.by_id(case_id)` for explicit identifier lookup, avoiding ambiguity when integer Case
identifiers overlap sequence indexes.

`CaseResult.to_dict()`, Candidate Result serialization, `Report.to_dict()`, and file export retain
the same outcome fields and nested Failure evidence. An evaluate transport returns the exact URL4
expression it was given; the Report preserves that expression unchanged for replay and audit.

## Presentation

The report widget trusts the explicit Case status:

- scored Cases render as correct or incorrect using their already-normalized grade/checks;
- refused Cases render a warning state and the exact provider refusal;
- failed Cases render a warning state and their typed failure chain;
- failed Cases carrying partial grading evidence render as `unscored`, never `incorrect`.

Failure summaries name affected Case identifiers and group identical diagnoses while a disclosure
retains each exact Failure payload. Candidate scores withheld by the current fail-closed producer
say why instead of showing unexplained dashes. All Engine/provider text remains HTML-escaped.

## Exclusions

- Changing Engine aggregation or the OME-807 failure taxonomy.
- Per-operation outputs, attempt traces, request parameters, or correlation IDs (OME-784).
- Rich per-turn conversation expansion (OME-794).
- Benchmark-specific scoring or refusal inference in the Client.
- Compatibility readers for pre-release result shapes.
