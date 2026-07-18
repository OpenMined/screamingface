---
id: OME-475
linear_url: https://linear.app/openmined/issue/OME-475/append-only-gate-detect-a-new-outer-decorator-skipxfail-stacked-on-an
status: backlog
type: task
priority: P3
labels: [repo, deferred, agentic]
created: 2026-07-18
closed:
---

Append-only gate follow-up (from PR #383 / OME-369): stacking a new outermost
decorator (`@pytest.mark.skip`/`xfail`) onto an existing test anchors at the
same diff position as legitimately inserting a new function above it, so the
gate can't see it — a direct way to silently disable a prior test. Deferred
because a correct fix needs old-vs-new AST identity matching (compare each
function's decorator list across versions), a different and larger mechanism
than the gate's line-position diffing; gated on a design pass for that
matching (renames, same-name functions, decorator-source comparison).
Documented as gap (5) in `run_gates.py`'s AIDEV-NOTE.
