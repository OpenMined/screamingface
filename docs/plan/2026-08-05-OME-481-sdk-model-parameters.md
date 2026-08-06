---
title: OME-481 SDK model parameters — implementation plan
status: approved
created: 2026-08-05
ticket: OME-481
spec: docs/spec/2026-08-05-OME-481-sdk-model-parameters.md
ledger: docs/work/2026-08-05-OME-481-sdk-model-parameters.md
---

# OME-481 implementation plan

This is a separate SDK review unit stacked after OME-480 and the existing SDK stack.

## Slice 1 — typed discovery

- Extend model-list decoding without making summaries pretend to be detail documents.
- Add immutable `ModelDetails`, parameter/schema, and capability values.
- Add sync/async/default `models.get()` through the existing authenticated Engine HTTP seam.
- RED first at the public Client boundary.

## Slice 2 — targeted Evaluation preflight

- Retain explicit parameter assignments on benchmark-independent compiled operations, then filter
  them through the Benchmark-linked operation set.
- Deduplicate profile-specific detail reads by canonical model id.
- Validate enabled status and the published value schema before transport execution.
- RED first at `Client.evaluate()` and `AsyncClient.evaluate()` with a forbidden transport.

## Verification

- Focused new tests while iterating.
- Distribution/public-interface, notebook, and full SDK gates.
- Final diff review against the captured pre-OME-481 dirty SDK state.

No AI Gateway, URL4 Cloud, URL4, Benchmark protocol, notebook content, or Linear mutation belongs
in this unit.
