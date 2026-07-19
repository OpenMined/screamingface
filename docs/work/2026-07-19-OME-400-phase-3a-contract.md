---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Approve Phase 3A grading and aggregation contract

## Intent

Review and lock the complete public grading, aggregation, failure, and convenience-facade
behavior before any Phase 3 runtime implementation. Preserve the architecture in which the SDK
orchestrates work through the configured URL4 engine, only the engine contacts AI Gateway, and
deterministic exact grading and mean aggregation remain local.

## Approved decisions

- `run.grade()` grades the captured Fusion and every captured member by default. It does not rerun
  workers, and a failed run case receives no grading work.
- Grading produces nested immutable `Grades`, `CaseGrades`, `Grade`, `CriterionVerdict`, and
  `GradeFailure` values with stable ordering and JSON-compatible snapshots.
- `ExactChoice` ports the established A–J/numeric-string/explicit-marker/full-text normalization
  contract.
  Invalid benchmark references raise before spend; a non-blank unparseable model answer is valid
  incorrect work and scores `0.0`.
- `Rubric` validates every selected reference before judge spend and uses one ordinary advertised
  model-route request for each target, criterion, and pass. URL4 context is the judge user message
  and intent is the pinned judge system prompt.
- Official DRACO passes are byte-identical independent requests. The SDK adds no salt or pass
  marker, and the engine must leave AI Gateway response caching disabled for judge calls.
- A judge response is the model's plaintext JSON with `explanation` and a `MET`/`UNMET` status.
  The SDK may extract the first fenced/prefaced object, validates its exact schema, and retries
  only invalid structured output up to two times with an identical request.
- Rubric grades require complete criterion/pass coverage. Missing evidence remains missing,
  produces `score=None`, and is never inferred as `UNMET` or converted into a partial score.
- Rubric scores use DRACO's positive/negative weighted formula; `pass_rate` and weighted section
  scores are meanable grade metrics. Raw evidence, counts, coverage, and failures are not metrics.
- `aggregators.Mean` uses one strict common paired case set for the Fusion and every member.
  `Report` and `MemberReport` expose scores, baseline, gain, coverage, metrics, failures, and
  completeness on the `0..1` scale.
- `Fusion.evaluate(benchmark, first=...)` is exactly
  `self.run(benchmark, first=first).grade().aggregate()`. It has no independent policy knobs.
- `benchmarks.load(id)` remains an eager registry/manifest/case-resource load. Passing the loaded
  object skips only loading; all panel, reducer, and rubric-judge model work still uses the
  configured URL4 engine.

## Failure and execution policy

- An operation that cannot safely begin raises: malformed rubric/reference data, unsupported
  strategies, unavailable judge models, incompatible parameters, or failed engine preflight.
- Once valid grading begins, a target/criterion failure is recorded and unrelated work continues.
- There is no SDK transport retry. Invalid judge-output schema alone permits two validation
  retries, for three total byte-identical attempts.
- Phase 3A originally selected a 32-request judge bound. Phase 3C operational review supersedes
  that value with 16 because the current engine rejects requests above its 16-request admission
  limit. Returned cases, targets, criteria, passes, and failures retain stable semantic order.
- `Grades.complete` and `Report.complete` describe all selected work, so a valid partial paired
  report can still be incomplete.

## Implementation slices

- **Phase 3B:** public grading values and failures, `ExactChoice`, and focused tests.
- **Phase 3C:** rubric preflight, URL4 judge calls, parsing/retries, scoring, and evidence.
- **Phase 3D:** paired Mean reports and exact `Fusion.evaluate()` facade parity.

Every slice requires owner review before runtime work begins.

## Outcome

- **Actual files:** updated the normative benchmark contract, architecture plan, task ledger, and
  syntax-only walkthrough fixture; added this review record.
- **Runtime changes:** none.
- **Engine-profile changes:** none.
- **Tests:** documentation/fixture validation only.
- **Next review:** Phase 3B implementation boundary and contract tests.
