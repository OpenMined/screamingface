---
id: OME-670
linear_url: https://linear.app/openmined/issue/OME-670
parent: OME-666
status: In Progress
type: Task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-08-08
closed:
---

# Generate API reference for core classes

Fifth of six sub-issues under `OME-666` (Documentation for ScreamingFace Client V1). Adds the API
reference for the classes a reader constructs or reads.

The Linear issue has no description, so the spec is `OME-666`'s API-reference paragraph. Its list
of six core classes does not survive contact with the client: `sf.Case` is `CaseInfo` and carries
only an id and a prompt, `sf.StudyReport` was merged into `Report`, and the paragraph omits most
of the surface. Eighteen of the 36 names in `__all__` are class-shaped.

Four pages, grouped by what a reader is doing, rather than one page per class — thirteen of the
eighteen would be a single table:

```
API REFERENCE
  ▸ Core classes
      Recipes      Recipe · Model · Fusion · CorrectiveEnsemble
      Benchmarks   Benchmark · BenchmarkInfo · CaseInfo · ModelInfo
      Reports      Report · CandidateResult · MemberResult · OperationInfo · Usage · Failure
      Clients      Client · AsyncClient · Connection · ConnectionPanel
```

Two depths. Eight classes you construct or call get a full entry: signature, what it is,
parameters, returns, raises where the source raises, and one executed line. Ten you read but never
construct get a field table, because a "runnable line" for `Failure` or `MemberResult` would be
invented.

Modules, top-level functions, errors, warnings and event types belong to `OME-671`. That ticket's
own list is half-dead too (`sf.graders`, `sf.aggregators`, `sf.reducers`, `sf.tools` do not exist,
and `sf.config` is `sf.configure`), so it gains `sf.events`, `sf.errors` and `sf.warnings`, which
no ticket specified.

Branch `callis/ome-670-generate-api-reference-for-core-classes` is cut from the epic branch
`callis/ome-666-documentation-for-screamingface-client-v1`; its PR targets that branch, not `main`.

Milestone: Week 3.

Ledger: `docs/work/2026-08-08-OME-670-api-reference-core-classes.md`
