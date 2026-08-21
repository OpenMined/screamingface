---
id: OME-692
linear_url: https://linear.app/openmined/issue/OME-692/use-and-expose-cache-provenance-in-the-screamingface-client
status: Blocked
type: Feature
priority: P1
labels: [py-screamingface]
created: 2026-07-30
closed:
---

# Use and expose cache provenance in the ScreamingFace Client

This increment preserves the Engine's per-call cache status and reason in typed Client Events and
surfaces authoritative live hit, miss, and bypass counts in the Evaluation panel. The broader issue
remains blocked on persisted saved-cost accounting; this increment neither invents savings nor
closes the Linear issue.

Spec: `docs/spec/2026-08-21-OME-692-live-cache-progress.md`.

