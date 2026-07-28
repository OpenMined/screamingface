---
id: OME-555
linear_url: https://linear.app/openmined/issue/OME-555/url4-cloud-e2e-developer-docs-sync-async-streaming-execution-sequence
status: done
type: task
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-22
closed: 2026-07-22
---

# OME-555 — url4-cloud e2e developer docs: sync / async / streaming execution + sequence diagrams

End-to-end developer guide in `apps/url4-cloud/docs/` walking the full path
client → `POST /token` → attach → `GET /?q=` → k8s Job/Runner → NATS → stream, for all three
execution modes:

- **sync** — `GET /` holds to the terminal frame, bounded by `SYNC_MAX_WAIT`, degrades to `202`
  past the bound;
- **async** — `Prefer: respond-async` → `202` + `Location`/`Link`, then poll;
- **streaming** — WS attach (`?ticket=`) + live CloudEvents + `ai.url4.stop`/`attach` resume.

Each mode gets a **sequence diagram** produced via the diagramming plugin
(`/diagramming:architecture-diagram` / its sequence variant), rendered to **SVG + PNG** under
`docs/diagrams/` per repo convention.

**Acceptance:** guide committed; 3 sequence diagrams rendered (SVG+PNG, verified via
`rsvg-convert`); `run_gates.py url4-cloud` green (docs-only). Follow sdlc-python (ledger first)
+ the diagramming skill.

Parent: alignment epic (`…-spec-c-alignment`).
