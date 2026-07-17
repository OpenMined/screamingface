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

Ship the importable ScreamingFace Python SDK and its executable quickstart as a URL4-native
compose → run → compare path.

Current public surface:

- optional `sf.config(engine=..., mode=...)`, with independent engine/data selection;
- `sf.models`, strict model dictionaries, and `sf.Fusion`/`Fusion.from_yaml`;
- `sf.MajorityVote`, `sf.ModelReducer`, canonical `.url4`, and concrete `request_for(...)`;
- `fusion.evaluate("gpqa" | "draco", first=..., seed=...)`; and
- immutable `Run`/`ModelResult`/`RunFailure` provenance and comparison results.

The zero-setup path runs complete expressions through a real in-process `Url4Node` and uses
deterministic handlers only at registered model routes. It never calls AI Gateway or providers.
An explicitly selected HTTP URL4 engine is strict and never falls back. Only a production URL4
model-route adapter may call AI Gateway.

Documentation deliverables are:

- a deliberately small `00_quickstart.ipynb`;
- a detailed `sf_url4_engine.ipynb` request/node/response walkthrough;
- a DRACO panel/reducer/judge walkthrough;
- a brand-aligned static HTML reference covering every exported API; and
- reconciled README/spec/plan/task/work records that remove the superseded direct-gateway design.

Owner metadata sync remains required: confirm Linear priority/created date and add/register the
`pkg/screamingface-sdk` landing label in Linear and `.claude/task-board.local.md`.
