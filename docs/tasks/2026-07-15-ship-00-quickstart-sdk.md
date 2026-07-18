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

Superseded implementation state (not a compatibility target):

- optional `sf.config(engine=..., mode=...)`, with independent engine/data selection;
- `sf.models`, strict model dictionaries, and `sf.Fusion`/`Fusion.from_yaml`;
- `sf.MajorityVote`, `sf.ModelReducer`, canonical `.url4`, and concrete `request_for(...)`;
- `fusion.evaluate("gpqa" | "draco", first=...)`; and
- immutable `Run`/`ModelResult`/`RunFailure` execution identity and comparison results.

The existing in-process `Url4Node`, deterministic model responses, and mock/live mode are slated
for removal. The target SDK always calls the effective HTTP URL4 engine; local development uses
the Dockerized `.docs/spikes/sf-url4-engine` stack, and only that engine reaches AI Gateway.

Documentation deliverables are:

- a deliberately small `00_quickstart.ipynb`;
- a detailed `sf_url4_engine.ipynb` request/node/response walkthrough;
- a DRACO panel/reducer/judge walkthrough;
- a brand-aligned static HTML reference covering every exported API; and
- reconciled README/spec/plan/task/work records that remove the superseded direct-gateway design.

Owner metadata sync remains required: confirm Linear priority/created date and add/register the
`pkg/screamingface-sdk` landing label in Linear and `.claude/task-board.local.md`.

## Greenfield benchmark architecture — 2026-07-18

The owner confirmed that the SDK and notebooks have no external users and authorized replacing
the current public evaluation surface without compatibility wrappers. The approved direction is
recorded in:

- `docs/plan/2026-07-18-OME-400-screamingface-benchmark-architecture.md`; and
- `docs/spec/2026-07-18-OME-400-benchmark-public-contract.md`.

Phase 0 locks universal cases, plain-Python benchmark recipes, and immutable in-memory
`Run` → `Grades` → `Report` artifacts before production implementation. Persistence and budget
enforcement are later additive contracts once their engine and storage requirements exist.
