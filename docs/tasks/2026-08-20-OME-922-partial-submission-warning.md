---
id: OME-922
linear_url: https://linear.app/openmined/issue/OME-922/warn-on-partial-submission-that-only-full-runs-are-ranked
status: in_progress
type: improvement
priority: 3
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-20
closed:
---

# Warn that partial-submission scores are not directly comparable

Warn at `sf.leaderboards.submit(...)` when a Candidate covers fewer than all Benchmark
Cases or has incomplete grading coverage. The warning is advisory: the Client still sends
the submission, which may appear on the public leaderboard, while explaining that its score
is not directly comparable with scores from full runs.

In notebooks, render that advisory inside the published-score card using the canonical
ScreamingFace warning treatment. Preserve a `UserWarning` for headless callers.

Canonical artifacts:

- Spec: `docs/spec/2026-08-20-OME-922-partial-submission-warning.md`
- Plan: `docs/plan/2026-08-20-OME-922-partial-submission-warning.md`
- Ledger: `docs/work/2026-08-20-OME-922-partial-submission-warning.md`
