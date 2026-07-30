---
title: Client rich-display port
ticket: OME-626
status: approved
date: 2026-07-28
spec: docs/spec/2026-07-28-OME-626-client-rich-display-port.md
---

# OME-626 — Client rich-display port plan

1. Add failing tests for sequence behavior, compact text representation, escaped static HTML,
   interactive filtering, and notebook-extra absence.
2. Add a small public catalogue value module and a private display module adapted to `ModelInfo`
   and `BenchmarkInfo`.
3. Return the catalogue values from synchronous, asynchronous, explicit-Client, and lazy
   module-level discovery.
4. Add Model/Fusion cards and preserve Report URL4 presentation.
5. Consolidate object-card and catalogue styling behind one private brand-style module.
6. Run focused tests, the full Client suite, Ruff, formatting, Pyright, notebook validation,
   package build, and the repository ScreamingFace gate.
