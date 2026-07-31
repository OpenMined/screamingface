---
id: OME-667
linear_url: https://linear.app/openmined/issue/OME-667
parent: OME-666
status: In Progress
type: Task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-07-30
closed:
---

# Update layout on the website + overview + quickstart

First of six sub-issues under `OME-666` (Documentation for ScreamingFace Client V1). Delivers the
docs site layout and its first two pages.

**Layout** — sidebar per `OME-666`: Overview ungrouped, then `Get Started` with Quickstart and
Installation. Quickstart routes at `/sf-client/quickstart`.

**Overview** — what ScreamingFace is · headline gain figure · 6-line example · 2-line how-it-works
(the SDK talks only to the SF Engine; URL4 is the contract) · links.

**Quickstart** — DRACO-Lite end to end, outcome first: `sf.config` → `sf.connect` → Models + Fusion
→ `sf.benchmarks.load("draco-lite@1")` → `benchmark.evaluate([candidates])` → read the
`StudyReport`. Source: `packages/screamingface/examples/05_draco_quickstart.ipynb`. Receipts:
1 case · 10 criteria · 1 judge pass · 7 solo + 9 Fusion candidates.

Result figures ship as marked placeholders (owner-approved) — no notebook in the repo has committed
outputs, so no verified DRACO-Lite score exists to quote.

Branch `callis/ome-667-update-layout-on-the-website-overview-quickstart` is cut from the epic branch
`callis/ome-666-documentation-for-screamingface-client-v1`; its PR targets that branch, not `main`.

Milestone: Week 3.

Ledger: `docs/work/2026-07-30-OME-667-docs-layout-overview-quickstart.md`
