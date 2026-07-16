---
id: OME-400
linear_url: https://linear.app/openmined/issue/OME-400
status: in_progress
type: task
priority: unknown
labels: [Python SDK, agentic, autonomous, Feature]
created: unknown
closed:
---

Ship `00_quickstart.ipynb` as the SDK-side mirror and executable specification of the
connect → compose → run → compare loop. The notebook requires a real importable
`screamingface` package surface: `sf.setup()`, `sf.models.list(max_price=20)`,
`sf.Fusion(..., reduce="majority_vote", judge=<member>)`, a shareable URL4 recipe,
`fusion.evaluate("gpqa", first=20, seed=0)`, and `score` / `baseline` / `gain` results.

The committed notebook executes end to end without credentials in explicit deterministic mock
mode, with static widgets and visibly simulated outputs. The production default is live mode:
the same SDK surface authenticates to AI Gateway and runs real provider completions behind the
completion port.

Owner metadata sync still required: confirm the Linear priority/created date and add/register the
new package landing label (`pkg/screamingface-sdk`) in Linear and
`.claude/task-board.local.md`.
