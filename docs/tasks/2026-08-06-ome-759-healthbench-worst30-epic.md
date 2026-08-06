---
id: OME-759
linear_url: https://linear.app/openmined/issue/OME-759/ship-the-healthbench-worst-30percent-challenge-exam-on-the-sf-engine
status: backlog
type:
priority: P1
labels: [url4-cloud, py-screamingface, agentic, autonomous]
created: 2026-08-06
closed:
---

# OME-759 — Ship the HealthBench worst-30% challenge exam on the SF engine

Epic. HealthBench onto the engine as `healthbench-worst30`: 157 hardest Professional
rows, per-item GPT-5.4 judging (billed to the submitter's OpenRouter key, judge
included), unclipped-mean challenge metric, target =
our open-fusion baseline rerun on the engine. Built against
`integration/keelan-all-changes-20260806` (Keelan's ask — its client→benchmark flow is
the client-v1 freeze).

Design: `.dk/plans/2026-08-05-healthbench-sf.md` (decisions D1–D6, technical §4,
re-baseline §7).

Sub-issues (one per landing + the human run item):

- `OME-760` — engine exam (`url4-cloud`)
- `OME-761` — spend-gated e2e notebook (`py-screamingface`), blocked by 760
- `OME-762` — baseline rerun + published target (human: Khoa; paid runs are never
  agentic), blocked by 760+761
