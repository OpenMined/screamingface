---
id: OME-810
linear_url: https://linear.app/openmined/issue/OME-810/public-docs-v1-bring-api-docs-back-in-sync-with-the-screamingface
status: in_progress
type: task
priority: P1
labels: [repo, agentic, autonomous, task]
created: 2026-08-13
closed:
---

Epic: bring `public-docs/` back in sync with the shipped `packages/screamingface` public API. The
API reference and Fusions guide describe removed symbols (`Fusion(reducer=...)`, `sf.reducers.*`,
`sf.CorrectiveEnsemble`) and omit `Pipeline`; documented examples raise on copy-paste because
`synthesizer` is now required.

Four workstreams, one sub-issue each:

- OME-811 (WS1, High) — recipe correctness: RecipesPage, FusionsPage, new Pipelines guide.
- OME-812 (WS2) — new API pages: Leaderboards, Errors, Events, Url4.
- OME-813 (WS3) — new/expanded guides: Leaderboards (incl. the `sf.Url4(...)` copy-and-edit loop),
  Errors, Events.
- OME-814 (WS4, blocked-by 811/812/813) — nav + version footer + global stale-term sweep + repr
  audit + GitHub-link refresh.

Plan: `.claude/plans/can-you-generate-me-effervescent-crane.md`. Prior art: OME-667, OME-668, OME-672.
