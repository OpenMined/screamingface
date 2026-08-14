---
id: OME-832
linear_url: https://linear.app/openmined/issue/OME-832/hide-the-verified-chip-and-filter-in-the-python-leaderboard-view
status: In Progress
type: Task
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-14
closed:
---

# Hide the verified chip and filter in the Python leaderboard view

Client half of the `OME-820` review fix, raised by `@HupBaHa` on PR #588. The notebook view is what
Monday's tester cohort sees in Colab, and it rendered a `verified` chip on every row plus a
"verified only" filter that removed nothing.

The deletion had a trap: `_row_chip` fell through to its `baseline` branch on
`python_source is None`, so removing the `verified` branch alone would have labelled a candidate
with an unforkable url4 as **"baseline"**. The predicate now keys on `kind`, which also fixes the
same mislabel for unverified candidates — a pre-existing bug confirmed by a failing test.

Spec: `docs/spec/2026-08-14-OME-832-hide-verified-chip.md`
Plan: `docs/plan/2026-08-14-OME-832-hide-verified-chip.md`
Ledger: `docs/work/2026-08-14-OME-832-hide-verified-chip.md`
