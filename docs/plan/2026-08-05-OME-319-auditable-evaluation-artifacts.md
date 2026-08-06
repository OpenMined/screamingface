# OME-319 — auditable Case Results implementation plan

## Confirmed seams

1. Engine: `screamingface.candidate-result.v1` returned by ordinary URL4 execution.
2. SDK: immutable `CandidateResult.cases` and lossless Report serialization.
3. Presentation: generic Case/Grade/Check/Evidence widgets, with no Benchmark branches.

Benchmark helpers remain implementation details. The contract is output data, not execution DSL.

## Vertical slices

### 1. DRACO

- Execute the smoke expression against controlled Candidate and Judge routes.
- Require one Case Result containing exact input/output, a rubric Case Grade, one criterion Check,
  and one complete Judge Evidence item.
- Name the Candidate output once per Case before criterion fan-out.
- Retain valid and invalid Judge replies in Engine-bound records and score from the same normalized
  values.
- Preserve failed Cases with `grade=null` and attached failures.

### 2. SDK

- Decode the literal Engine result from the DRACO slice into immutable public values.
- Round-trip it exactly through `Report.to_dict()` and `Report.to_json()`.
- Reject malformed structures, duplicate ids, count mismatches, and invalid JSON values.

### 3. IFEval

- Map instruction constraints to Checks and strict/loose deterministic verification to Evidence.
- Retain canonical output and corrective attempts/feedback without SDK protocol branches.

### 4. Documentation and gates

- Show Case inspection and JSON export in SDK documentation/notebooks.
- Run URL4 Cloud and ScreamingFace gates, including notebook/distribution checks.
- Prepare OME-319/OME-316 scope and status proposals without mutating Linear.

## Rejected implementation

- No opaque `artifacts` or Benchmark-specific `grades` bag.
- No nested schema tag on every Case, Check, or Evidence item.
- No DRACO fields on public SDK classes.
- No recovery by parsing URL4 or progress events after completion.
- No duplicated Candidate output per criterion.
- No normalized-only verdicts; raw evidence is required.
- No fabricated telemetry whose attribution is unavailable.
