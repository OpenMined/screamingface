---
id: OME-477
linear_url: https://linear.app/openmined/issue/OME-477/enforce-the-append-only-test-gate-in-ci-against-the-real-merge-base
status: backlog
type: task
priority: P2
labels: [repo, design-session, agentic]
created: 2026-07-18
closed:
---

Rule 5 (append-only tests) has zero independent enforcement: no CI workflow
or hook runs `run_gates.py`, and every documented invocation defaults to
`--base HEAD` (uncommitted delta only — a test weakened in an earlier commit
of the same branch is invisible to later local runs). The gate is voluntary
and local; nothing server-side re-verifies before merge, which caps the value
of all the diff-logic hardening done in OME-369. Design-session fork: where
it runs (per-component workflows vs. repo-wide vs. pre-push hook), the base
ref (PR merge-base for CI), and enforcement level (required check vs.
advisory, plus a deliberate override path for Confidence-Gate-approved prior
test changes). Found during PR #383's review; distinct infra unit from
OME-369's code fixes.
