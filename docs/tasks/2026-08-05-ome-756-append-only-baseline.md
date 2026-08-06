---
id: OME-756
linear_url: https://linear.app/openmined/issue/OME-756/use-originmain-as-the-append-only-baseline-for-pr-level-gate-runs
status: backlog
type: task
priority: P3
labels: [repo, autonomous, agentic, task]
created: 2026-08-05
closed:
---

# OME-756 — origin/main as the append-only baseline for PR-level gate runs

`run_gates.py`'s append-only check compares `git diff --name-status <base>` with `--base`
defaulting to `HEAD`. Right for a per-commit loop, wrong for a PR: it treats a test file written
minutes earlier **in the same unit** as a "prior test", so any later edit to it fails the gate.

Hit in both `OME-745` and `OME-746`. In `OME-746` the append was verifiably additive (86
insertions, 0 deletions, no prior test altered) and still failed, because the check reads file
*status*, not content. Both units worked around it by putting new tests in a new module rather
than the natural one — test organisation driven by a tool artifact rather than cohesion.

`--base origin/main` is the semantically correct PR-level baseline and already works. Does **not**
duplicate `OME-369`/#383: line-level diffing and the right baseline fix different halves, and
#383 alone would still flag a genuine edit to a test the same PR introduced.
