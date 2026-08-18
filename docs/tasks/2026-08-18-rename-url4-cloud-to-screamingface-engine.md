---
id: OME-876
linear_url: https://linear.app/openmined/issue/OME-876/rename-appsurl4-cloud-to-appsscreamingface-engine
status: in_progress
type: task
priority: 3
labels: [screamingface-engine, agentic, autonomous, task]
created: 2026-08-18
closed:
---

# Rename `apps/url4-cloud` to `apps/screamingface-engine`

Repo-side rename of the Engine app so the directory, Python package, distribution, console
scripts, Helm chart, container images, CI lanes and release identity match the product name
already used in Linear and in the published image prefix.

Scope **T2 / Path A**: identity, CI, release and chart naming change. The `URL4_CLOUD_*` env
prefix, the NATS subject/stream prefix and the Kubernetes pod labels are deliberately left in
place so the deploy stays an ordinary rolling update and `apps/aigateway` needs no change.
`packages/url4` is not touched.

Deferred names tracked in `OME-877`.

- Spec: `docs/spec/2026-08-18-screamingface-engine-rename.md`
- Plan: `docs/plan/2026-08-18-screamingface-engine-rename.md`
- Ledger: `docs/work/2026-08-18-OME-876-rename-url4-cloud-to-screamingface-engine.md`
