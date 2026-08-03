---
ticket: OME-605
status: approved
date: 2026-07-31
---

# OpenRouter connection vertical slice

1. Add a dependency-free Engine connection port and an AI Gateway HTTP adapter.
2. Add the three sanitized SF Engine REST operations and wire the adapter at the
   composition root.
3. Cover identity forwarding, secret safety, upstream validation, replacement,
   deletion, response validation, and error mapping.
4. Add immutable Client connection values and strict sync/async HTTP adapters.
5. Restore the rich connection widget against the explicit Client rather than global
   transport state.
6. Expose module-level lazy helpers plus explicit `Client` and `AsyncClient` methods.
7. Update the quickstart material and run focused and full package/Engine gates.
