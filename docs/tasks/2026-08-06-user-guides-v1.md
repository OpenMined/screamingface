---
id: OME-668
linear_url: https://linear.app/openmined/issue/OME-668
parent: OME-666
status: In Progress
type: Task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-08-06
closed:
---

# User guides v1 for connections, compose (models, fusions), benchmarks (first only), running an evaluation

Second of six sub-issues under `OME-666` (Documentation for ScreamingFace Client V1). Adds six of
the parent's ten user-guide pages; `OME-669` covers the remaining four.

Pages, in sidebar order:

```
USER GUIDES
  Connections
  ▸ Compose
      Models
      Fusions
  Benchmarks
  Running an evaluation
  Reproduce & share (URL4)
```

Every guide follows the parent's five-part shape — what it is · what you can do with it · main
APIs · how to · links — and ends with `Based on state at commit e387aefd`.

Written against `OME-605-screamingface-client-v1` @ `e387aefd`. The client moved off the
`OME-400` branch, so the parent's spec and the merged Overview and Quickstart name API that no
longer exists (`sf.config`, `StudyReport`, reducers, `draco-lite`). Every sample here is verified
against `e387aefd` and executed against a local Engine, using `ifeval` — its grading is
deterministic and costs nothing.

Branch `callis/ome-668-user-guides-v1-for-connections-compose-models-fusions` is cut from the epic
branch `callis/ome-666-documentation-for-screamingface-client-v1`; its PR targets that branch, not
`main`.

Milestone: Week 3.

Ledger: `docs/work/2026-08-06-OME-668-user-guides-v1.md`
