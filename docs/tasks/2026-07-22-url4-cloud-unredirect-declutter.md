---
id: OME-566
linear_url: https://linear.app/openmined/issue/OME-566/un-redirect-scalar-asyncapi-serve-direct-scalar-pages-keep-docs
status: done
type: task
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-22
closed: 2026-07-22
---

# OME-566 — Direct doc pages + declutter the REST reference

Owner-decided: keep `/docs` as the REST ⇄ Stream switcher, drop the OME-565 redirects (`/scalar`
+ `/asyncapi` serve their own direct Scalar pages), and remove the empty **Stream** + **Ops** tags
plus the leaked `/healthz` operation from the OpenAPI so `/scalar` shows only the real API surface.
Sub-issue of the url4-cloud app epic (`OME-513`). Ledger:
`docs/work/2026-07-22-OME-566-unredirect-viewers.md`.
