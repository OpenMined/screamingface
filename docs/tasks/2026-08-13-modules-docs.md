---
id: OME-671
linear_url: https://linear.app/openmined/issue/OME-671
parent: OME-666
status: Done
type: Task
priority: P2
labels: [repo-dev-processes, agentic, task]
created: 2026-07-29
closed: 2026-08-13
---

# Generate modules docs

Sixth and last sub-issue under `OME-666` (Documentation for ScreamingFace Client V1). Adds the API
reference pages `OME-670` left out.

Four pages under `API Reference`, in a `Modules & types` subgroup:

```
API REFERENCE
  ▸ Core classes        Recipes · Benchmarks · Reports · Clients
  ▸ Modules & types
      Modules           the five modules and five top-level functions
      Errors            the error hierarchy and what a diagnostic error carries
      Events            the seven event types
      Leaderboards      the five leaderboard values
```

`api/LeaderboardsPage` is the field reference for the five values; `guides/LeaderboardsPage` is the
task walkthrough. Same split as the two Benchmarks pages.

Every signature, field and literal is derived at runtime from the client on `main`, never from
reading source.

This ticket also corrected the reference and guides against the merged client, and that work was
dropped: Irina had done the same independently and more currently, against `b698fcff`. See the
ledger for what was compared and why nothing was lost.

Branch `callis/ome-671-generate-modules-docs` is cut from `origin/main`; `OME-666` is merged, so
its PR targets `main`.

Milestone: Week 3.

Ledger: `docs/work/2026-08-13-OME-671-modules-docs.md`
