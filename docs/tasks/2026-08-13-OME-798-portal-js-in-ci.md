---
id: OME-798
linear_url: https://linear.app/openmined/issue/OME-798/run-the-portals-js-tests-in-ci-and-the-scoreboard-gate-list
status: In Progress
type: Task
priority: P3
labels: [scoreboard, agentic, autonomous, task]
created: 2026-08-12
closed:
---

# Run the portal's JS tests in CI and the scoreboard gate list

`OME-769` (merged `2a20c154`) shipped 14 tests covering the board's load-bearing judgements. Nothing
executed them: no JS step in `scoreboard-tests.yml`, no JS entry in the `scoreboard` gate list.

The wiring is two lines. The substance is **which** two lines: measured on Node v24.10.0, the
directory form fails outright and **both** glob forms exit `0` reporting `pass 0` when nothing
matches — because Node expands globs itself, so shell quoting is irrelevant. Either would have left
a permanently green step covering nothing the moment a file was renamed. The explicit path exits `1`
when the file is absent, so that is what both call sites use.

Spec: `docs/spec/2026-08-13-OME-798-portal-js-in-ci.md`
Plan: `docs/plan/2026-08-13-OME-798-portal-js-in-ci.md`
Ledger: `docs/work/2026-08-13-OME-798-portal-js-in-ci.md`
