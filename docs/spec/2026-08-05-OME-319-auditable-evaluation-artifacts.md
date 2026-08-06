# OME-319 — auditable Case Results

## Problem

`screamingface.candidate-result.v1` currently returns aggregate score and metrics. DRACO passes
the Candidate output and every Judge reply through Grading, then discards the output, raw reply,
and explanation. The SDK consequently cannot answer: what was asked, what did the Candidate
produce, what was checked, and why did it receive this grade?

The observed acceptance example is the 2026-08-05 `draco/smoke` Evaluation: Case 1 produced one
valid `UNMET` verdict and score `0.0`, but neither GPT-5.5's output nor the Judge explanation
survived completion.

## Ownership

- A Benchmark owns how its Cases are graded and constructs the Case Results.
- The Engine preserves those Case Results in the Candidate Result returned by ordinary URL4.
- The SDK strictly decodes immutable structural values and renders or serializes them.
- Widgets understand Case Result, Case Grade, Check, and Evidence; they do not understand DRACO or
  IFEval protocols.
- Execution remains URL4 plus Benchmark routes. These result values are not executable and users
  do not author them.

## Wire contract

`screamingface.candidate-result.v1` gains a required `cases` array. Only the top-level Candidate
Result carries a schema tag. `benchmark_id` and `benchmark_revision` version the nested meanings.

```json
{
  "case_id": 1,
  "input": "the exact Candidate input",
  "output": "the exact Candidate output",
  "grade": {
    "method": "rubric",
    "score": 1.0,
    "metrics": {},
    "checks": []
  },
  "failures": [],
  "metadata": {}
}
```

`input` and `output` are JSON values so future Benchmarks may retain native structured inputs or
outputs. A Case that failed before producing an output uses `null`; it is not dropped. `grade` is
`null` only when no valid Case Grade exists. `metadata` contains non-secret Case facts selected by
the Benchmark and must not reveal unused private grading material or answer keys.

### Case Grade

A Case Grade contains:

- `method`: a short Benchmark-defined grading method such as `rubric` or `deterministic`;
- `score`: the Case's primary numeric score;
- `metrics`: all additional JSON-compatible Case metrics used for audit or display;
- `checks`: ordered grading Checks.

### Check

Every Check contains `type`, `id`, `label`, ordered `evidence`, and `metadata`. A Benchmark may add
a normalized `outcome` or numeric `score` when one meaningful Check-level summary exists. It must
not invent one when the protocol scores repeated observations independently.

DRACO emits one `criterion` Check per rubric criterion. Its metadata contains criterion type,
weight, and scoring axis. IFEval emits one `instruction` Check per instruction constraint.

### Evidence

Every Evidence item contains:

- `sequence`: its one-based order within the Check;
- `producer`: `{ "type": "model" | "deterministic", "id": "..." }`;
- `valid`: whether it was accepted by the Benchmark parser or verifier;
- `outcome`: the normalized outcome when valid;
- `explanation`: normalized explanatory text when available;
- `raw_output`: the exact observed output, without reparsing or reconstruction;
- `metadata`: Benchmark-specific provenance such as a bounded rejection reason.

Invalid replies remain Evidence with `valid=false`, exact `raw_output`, and a bounded rejection
reason. They are never silently erased.

## DRACO mapping

Each Case Result stores the question and Candidate output once. Every rubric criterion becomes a
Check. Each independent Judge pass becomes Evidence whose producer is the Engine-known pinned
Judge model. The Evidence stores the exact raw reply, normalized `MET`/`UNMET`, explanation, and
validity. Scoring continues to mean the independent-pass DRACO calculation; the Check does not
fabricate a majority verdict.

## IFEval mapping

Canonical IFEval stores its one Candidate output, one Check per instruction constraint, and its
strict and loose deterministic verifier observations as Evidence. Corrective IFEval additionally
retains every Candidate attempt and sanitized feedback in ordered metadata/evidence while clearly
identifying the selected output. Verifier implementation details that would expose private grading
material to the Candidate remain private.

## Provenance rule

Keep every fact the Engine observes and can attribute correctly. Never fabricate missing facts.
Per-call finish reason, refusal, usage, cost, or duration may be added when semantic attribution is
available; until then the field is absent. Candidate-wide URL4, operations, usage, timestamps, and
model identity remain on `CandidateResult` and are not copied onto every Case.

## SDK interface

`CandidateResult.cases` is an immutable ordered collection of `CaseResult`. `CaseResult.grade` is
an immutable `CaseGrade`; its Checks and Evidence are likewise immutable. Benchmark metadata is
preserved as immutable JSON-compatible values. No new Benchmark requires an SDK release merely to
transport different metadata.

`Report.to_dict()` and `Report.to_json()` serialize the complete structure losslessly. Future
JSONL/CSV export consumes these values and never reconstructs evidence from URL4 or progress
events.

## Invariants

- One Case Result maps to one selected Engine Case id; duplicate or missing ids fail loudly.
- Case ordering matches selected Benchmark Case ordering.
- Exact Candidate output is stored once per Case, not once per Check.
- Exact raw output and normalized Evidence are both retained.
- Evidence producer and sequence come from the Engine, never from model output.
- Accepted, invalid, and missing Evidence counts reconcile with Case metrics.
- `case_count == len(cases)` at Engine and SDK seams, including failed Cases.
- A failed Case remains inspectable with `grade=null`; it cannot become a plausible score zero.
- Strict decoding rejects malformed structures rather than dropping evidence.
- No provider-, model-, or Benchmark-specific SDK branches.

## Compatibility

Nothing implementing this contract has merged to `main`; this review stack changes atomically.
There is no legacy fallback.

## Out of scope

- Inventing per-Case cost or timing before semantic attribution exists.
- External artifact storage.
- CSV flattening policy.
- Public Scoreboard redaction policy; local retention and publication are distinct decisions.

## Acceptance

- A real DRACO smoke expression returns the exact question, Candidate output, criterion, raw Judge
  reply, normalized status, explanation, Judge identity, and pass order.
- Invalid Judge replies and Case failures remain inspectable.
- SDK values and Report JSON round-trip those facts exactly.
- IFEval emits its per-Case output and deterministic checks through the same structure.
