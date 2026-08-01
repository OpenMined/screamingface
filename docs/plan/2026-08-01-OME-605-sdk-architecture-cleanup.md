---
title: Implement the ScreamingFace SDK architecture cleanup
ticket: OME-605
status: complete
date: 2026-08-01
spec: ../spec/2026-08-01-OME-605-sdk-architecture-cleanup.md
---

# Implement the ScreamingFace SDK architecture cleanup

1. Pin current behavior at the public Client, ConnectionPanel, and transport seams.
2. Move caller authentication contracts into core ports and keep adapter selection in the registry.
3. Extract the complete Evaluation workflow from `client.py`.
4. Separate panel state/control from static HTML and ipywidgets rendering.
5. Consolidate strict Engine wire decoding and remove shallow catalogue helpers.
6. Group private implementation under `_engine`, `_evaluation`, and `_ui` only where the seams are
   established by the preceding steps.
7. Replace private-state tests with interface-level tests where practical.
8. Run focused tests after each slice, then the full package and end-to-end gates.
