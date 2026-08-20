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

# Warn that partial submissions are not ranked

Warn at `sf.leaderboards.submit(...)` when a Candidate covers fewer than all Benchmark
Cases or has incomplete grading coverage. The warning is advisory: the Client still sends
the submission, while the public leaderboard ranks only full runs.

Canonical artifacts:

- Spec: `docs/spec/2026-08-20-OME-922-partial-submission-warning.md`
- Plan: `docs/plan/2026-08-20-OME-922-partial-submission-warning.md`
- Ledger: `docs/work/2026-08-20-OME-922-partial-submission-warning.md`
