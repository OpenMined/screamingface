---
id: OME-633
linear_url: https://linear.app/openmined/issue/OME-633
status: In Progress
type: Task
priority: P2
labels: [url4-sdk, autonomous, agentic, task]
created: 2026-07-27
closed:
---

# Typecheck error in test_observe.py keeps the url4 CI gate red

One pyright error in `packages/url4/tests/unit/test_observe.py` — `_CORPUS: list[object]`
passed to `run(target: str | AstNode | Graph | DagNode, ...)` — fails the `Typecheck` step of
`url4-tests.yml`. Because that step runs before the test step, the 677-test url4 suite never
executes in CI on `OME-587-url4-cloud-engine-integration`; the red X hides an unrun suite.
Blocks PR #425. Fix is to type the corpus as `list[str | DagNode]` (`_BoomNode` structurally
satisfies the `DagNode` Protocol).

Landed with `OME-446` (commit `e3affad2`); parent epic `OME-513`.

Ledger: `docs/work/2026-07-27-OME-633-url4-typecheck-gate-red.md`
