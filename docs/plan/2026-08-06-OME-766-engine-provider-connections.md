---
title: Implement ScreamingFace Engine provider connections
ticket: OME-766
status: approved
date: 2026-08-06
spec: ../spec/2026-08-06-OME-766-engine-provider-connections.md
---

# Implement ScreamingFace Engine provider connections

1. Add an Engine-facing provider-connection port with secret-free public values and typed errors.
2. Add an AI Gateway adapter that combines provider capabilities with the caller-scoped,
   `screamingface`-designated row and validates every value that may enter a request path.
3. Add REST routes for list, API-key connect/replace, OAuth start, and idempotent disconnect.
4. Forward only the verified identity headers selected by the existing Engine identity contract.
5. Wire the adapter into production and local composition, including deterministic shutdown.
6. Publish concrete connection response schemas, errors, routes, and tag in OpenAPI.
7. Add focused adapter, route, local-composition, identity, malformed-response, timeout, and
   secret-safety tests.
8. Run `python3 .claude/scripts/run_gates.py url4-cloud` and review the direct
   `origin/main...HEAD` diff.

No external Linear mutation is part of this implementation pass.
