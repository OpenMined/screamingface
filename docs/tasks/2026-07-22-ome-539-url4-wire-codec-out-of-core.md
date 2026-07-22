---
id: OME-539
linear_url: https://linear.app/openmined/issue/OME-539
status: Backlog
type: Refactor
priority: P2
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: move the HTTP wire codec out of core/

core/subrequest.py holds percent-encoding, query splitting and a heuristic sniffing which URL-encoding convention an HTTP client used — transport concerns inside the transport-free core. Leaves the anticipated WS/streaming transport with no seam: RelUrlNode/RemoteFetchNode would need rewriting rather than a new adapter. The one genuine layering inversion in the package.

Spec → plan → owner approval before code. Under OME-537.
