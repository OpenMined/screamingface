---
id: OME-397
linear_url: https://linear.app/openmined/issue/OME-397/package-and-commit-url4-sdk-v1-under-sdlc
status: done
type: task
priority: P2
labels: [pkg/url4-python-sdk, Python SDK, autonomous, agentic, Feature]
created: 2026-07-11
closed: 2026-07-14
---

Land **url4 v1** into the monorepo at `packages/url4` as one SDLC-tracked unit, in three
phases. **(1) Engine core** — package and commit the existing framework-free library for the
url4 expression protocol (`(sources)!intent` compiled into an executable DAG of typed nodes,
I/O inverted behind an `IOLayer` port) off up-to-date `main` without altering main history, with
an as-built technical spec and architecture diagrams. **(2) SDK product surface** — the renderer
(`render`), Python builders, the `Client` + `Url4Result` façade, and the `Url4Node` node/server
SDK with a framework-free ASGI shim. **(3) Package integration** — a path-filtered CI workflow, a
95% coverage gate, an `.claude/sdlc.local.md` stack entry, and a `release-please` lane. Relationship:
lands the package that the earlier deferred extraction item `OME-367` anticipated.
