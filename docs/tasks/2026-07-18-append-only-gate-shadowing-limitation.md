---
id: OME-476
linear_url: https://linear.app/openmined/issue/OME-476/append-only-gate-name-shadowingmonkeypatching-bypass-decide-accept-vs
status: backlog
type: task
priority: P3
labels: [repo, design-session, agentic]
created: 2026-07-18
closed:
---

Append-only gate follow-up (from PR #383 / OME-369): name-shadowing /
monkeypatching / mutation-in-place appends (same-name redefinition,
`test_foo = lambda: None`, `del test_foo`, `compute = lambda: 42` at EOF,
`_CASES.append(...)`) change prior tests' behavior without touching their
lines — indistinguishable from legitimate additions at the diff level, so no
line-diff fix exists and the mechanism list is open-ended. Design-session
fork for the owner: (1) accept permanently as a documented limitation,
(2) invest in semantic/data-flow analysis of appended statements, or
(3) behavioral verification (run prior tests old-vs-new and diff outcomes).
Documented as gap (4) in `run_gates.py`'s AIDEV-NOTE.
