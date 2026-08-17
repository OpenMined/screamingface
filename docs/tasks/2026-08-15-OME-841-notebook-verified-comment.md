---
id: OME-841
linear_url: https://linear.app/openmined/issue/OME-841/correct-the-notebook-views-justification-for-removing-the-verified
status: In Progress
type: Task
priority: P4
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-15
closed:
---

# Correct the notebook view's justification for removing the verified filter

`OME-832` (merged as #601) removed the `verified` chip and the "verified only" filter from the
notebook leaderboard view. The removal was right; the reason recorded beside it is false and
undercuts it — it says `verified_by_openmined` is "uniform", when `OME-820` forbids a backfill so
rows predating it keep `false`.

The real reason is stronger: the field certifies nothing whatever it holds, so a filter would split
rows by whether they predate the default change while presenting itself as a verification filter.

Comments and one docstring only. No behaviour change.

Ledger: `docs/work/2026-08-15-OME-841-notebook-verified-comment.md` ·
Spec: `docs/spec/2026-08-15-OME-841-notebook-verified-comment.md` ·
Plan: `docs/plan/2026-08-15-OME-841-notebook-verified-comment.md`
