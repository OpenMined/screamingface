---
id: OME-672
linear_url: https://linear.app/openmined/issue/OME-672
parent: OME-666
status: In Progress
type: Task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-08-08
closed:
---

# Add installation tutorial

Fourth of six sub-issues under `OME-666` (Documentation for ScreamingFace Client V1). Replaces
the `Installation` stub under Get Started.

The Linear issue has no description, so the spec is `OME-666`'s Installation paragraph —
restructured, because that paragraph is local-first and names API that no longer exists
(`sf.config`, engine port `:4404`).

Two paths, in order:

1. **Hosted** — install the client, point it at the engine, log in, connect a provider.
2. **Self-hosted** — run AI Gateway and the Engine yourself. Covers what actually blocked us
   bringing one up: `aigateway migrate`, `AIGW_AUTH_MODE=disabled`,
   `AIGW_OPENROUTER_ENABLED=true`, and preparing benchmark assets.

Vocabulary follows the Learn section: bundled / self-hosted / hosted. The client cannot bundle an
engine — its dependencies carry no `url4-cloud` and it has no in-process execution path — so
"bundled" describes the url4 SDK, not this client.

`screamingface` is not on PyPI yet, so the install block says so and gives the source route.

Branch `callis/ome-672-add-installation-tutorial` is cut from the epic branch
`callis/ome-666-documentation-for-screamingface-client-v1`; its PR targets that branch, not
`main`.

Milestone: Week 3.

Ledger: `docs/work/2026-08-08-OME-672-installation-tutorial.md`
