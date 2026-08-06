---
id: OME-762
linear_url: https://linear.app/openmined/issue/OME-762/rerun-the-open-fusion-baselines-on-the-engine-and-publish-the-worst
status: backlog
type:
priority: P1
labels: [py-screamingface, human, deferred]
created: 2026-08-06
closed:
---

# OME-762 — Rerun the open-fusion baselines on the engine and publish the worst-30% target

Run item of `OME-759` — **executed by Khoa personally, never agentic** (paid model
calls; agent prepares configs, Khoa fires). Rerun open solos + fusions on
`healthbench/worst30`; the best open-fusion unclipped mean becomes the published
challenge target (July −0.211 = provenance only). Requires judge coverage 1.0; records
cost actuals (feeds D4 credit sizing + the Siddhant judge-inclusion question). Blocked
by `OME-760` + `OME-761`.
