---
ticket: OME-723
linear_url: https://linear.app/openmined/issue/OME-723/serve-paginated-benchmark-cases-on-the-engine-control-plane
status: todo
type: feature
priority: P2
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-03
closed:
---

# Serve paginated benchmark cases on the Engine control plane

`GET /v1/benchmarks/{id}/cases?limit=&offset=` in `apps/url4-cloud/rest/benchmarks.py`:
`{object: "list", total, limit, offset, data: [{id, input}]}`, ETag + Cache-Control like
the sibling catalog routes; 404 problem+json unknown id; unavailable when assets missing.
Generic over the `BENCHMARKS` registry. Prompt inputs only — never instruction specs or
answer keys. Parent: `OME-722`.
