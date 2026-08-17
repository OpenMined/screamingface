---
id: OME-847
linear_url: https://linear.app/openmined/issue/OME-847/add-a-clients-vs-sf-shortcuts-user-guide-to-the-docs-site
status: In Progress
type: Docs
priority: P2
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-17
closed:
---

# Add a "Clients vs sf.* shortcuts" user guide to the docs site

New `public-docs` User Guide explaining the two ways to call the ScreamingFace Client SDK —
the module-level `sf.*` shortcuts (one lazy, process-wide default `Client`) vs an explicit
`Client` / `AsyncClient` the caller constructs and owns. Comprehensive scope: config source,
lifecycle, async (no module-level async), custom transports, thread model, multiple engines.
Placed first under _User Guides_, titled **Clients**. Complements the existing API
Reference › Clients page (which documents the types); this guide covers *when to use which*.
