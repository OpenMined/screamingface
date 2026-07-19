---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Implement Phase 3D paired aggregation and reports

## Intent

Complete the public benchmark loop without hiding its stages. Preserve stable Fusion and member
identities from execution through reporting, aggregate only honest paired comparisons, and expose
`Fusion.evaluate()` as an exact convenience facade over the already public stages.

## Public contract

- `Run`, `Grades`, and `Report` preserve `fusion_name` and the ordered immutable
  `member_n -> model ID` mapping.
- Successful case results must contain exactly those member slots, in order, with the expected
  models. A failed case remains atomic and may contain no partial member answers.
- `grades.aggregate()` dispatches through the Benchmark's configured aggregator.
- `sf.aggregators.Mean()` is deterministic local arithmetic and makes no engine or model call.
- Mean uses one strict paired case set: a case contributes only when the Fusion and every member
  have valid grades.
- The Fusion score and every member score use that same set. `baseline` is the maximum member
  score and `gain` is Fusion score minus baseline.
- Metrics are averaged only when the metric exists on every paired grade for the corresponding
  target.
- If no paired case exists, Fusion, baseline, gain, and every member score are `None`; expected
  members and failures remain visible.
- `Fusion.evaluate(benchmark, first=...)` is exactly
  `Fusion.run(...).grade().aggregate()`.

## Implementation

- Added immutable public `Report` and `MemberReport` values with strict summary-state validation
  and JSON-compatible `to_dict()` snapshots.
- Added the internal Mean dispatcher and strict paired aggregation implementation.
- Extended `Run` and `Grades` with stable Fusion/member identity and strengthened successful-case
  validation.
- Added `Grades.aggregate()` and `Fusion.evaluate()` without introducing execution-policy
  parameters.
- Renamed URL4 call slots from `panel_n` to `member_n`. “Panel” remains useful research language,
  while `member_n` is the neutral machine identity shared by arbitrary Fusion shapes.

## Boundaries

- No engine-profile route, URL4 package, AI Gateway, authentication, persistence, cost, token,
  latency, confidence interval, or primary-metric behavior is added.
- An aggregator never calls a model. Model-backed judging remains grading work through the URL4
  engine.
- Phase 3D does not claim canonical DRACO readiness; the engine profile still needs the separately
  recorded DRACO model/tool capabilities.

## Verification

The implementation is covered by strict pairing, partial and total failure, metric intersection,
repeated-model identity, immutability, serialization, invalid report state, unsupported
aggregator, and exact `evaluate()` composition tests.

- 283 repository tests pass at 96.9% ScreamingFace coverage.
- 49 isolated screamingface-engine tests pass at 98.1% coverage.
- Owned-path Ruff lint and format, package Pyright, Phase 0 fixtures, deterministic Phase 1
  notebook regeneration, and wheel/sdist builds pass.

## Outcome

- **Runtime:** complete public `run -> grade -> aggregate` benchmark loop.
- **Engine-profile changes:** only the neutral `member_n` reducer input naming; no new behavior.
- **Next step:** review Phase 4 contracts before implementing additional benchmark discovery or
  workflow surfaces.
