---
id: OME-564
linear_url: https://linear.app/openmined/issue/OME-564/render-asyncapi-with-scalar-unify-doc-viewers-drop-asyncapiweb
status: done
type: task
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-22
closed: 2026-07-22
---

# OME-564 — Render /asyncapi with Scalar (unify doc viewers, drop @asyncapi/web-component)

Scalar ≥ 1.61 (June 2026) renders AsyncAPI 3.x with the same UI as OpenAPI. Swap `/asyncapi` from
the `@asyncapi/web-component` to a Scalar embed on `/asyncapi.json` — one polished, same-origin
viewer for both docs; removes the web-component dependency and the shadow-DOM `cssImportPath`
workaround (supersedes `OME-553` / `0dbf119`).

Sub-issue of the url4-cloud app epic (`OME-513`). Ledger:
`docs/work/2026-07-22-OME-564-asyncapi-via-scalar.md`.
