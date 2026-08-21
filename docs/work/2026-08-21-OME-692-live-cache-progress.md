---
ticket: OME-692
stack: screamingface
status: done
started: 2026-08-21
finished: 2026-08-21
---

# OME-692 — Show authoritative live cache progress

## Intent

Preserve cache provenance already emitted by the Engine and expose live, evidence-backed cache
progress in the Evaluation panel so researchers can diagnose whether a promised cached Evaluation
is actually hitting without waiting for terminal logs.

## Planned changes

- Add optional, validated cache status and reason fields to public Span Events.
- Decode the existing Engine Span fields in the Client contract adapter.
- Fold live per-Run counts and reconcile them with authoritative final summary Logs.
- Add a fourth SFDS-aligned cache stat cell after Cost.
- Add contract, fold, rendering, boundary, and reconciliation tests.

## Test plan

- RED: typed Event accepts the three statuses and rejects unknown statuses and blank reasons.
- RED: Engine Span decoding preserves status and reason.
- RED: hits, misses, and bypasses update live and hit rate excludes bypasses.
- RED: a final summary replaces live counts and multiple Candidate Runs aggregate.
- RED: no evidence renders unavailable; known counts render percentage and receipts.
- GREEN/refactor: run focused tests, all prior package tests, and every screamingface quality gate.

## Acceptance

- Every criterion in `docs/spec/2026-08-21-OME-692-live-cache-progress.md` passes.
- Existing Event, Evaluation progress, notebook, build, and distribution gates remain green.
- No cache behavior, savings, or provenance is inferred by the Client.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the four planned Client modules, three planned focused test modules, and the
  OME-692 spec, plan, task mirror, and work ledger.
- **Commits:** `feat(client): show live cache progress` (this commit).
- **Gates:** `run_gates.py screamingface` — all gates green; full package suite 983 passed,
  1 skipped; focused Event/contract/progress suite 86 passed; Ruff, format, Pyright, 95% coverage,
  notebook determinism, build, and distribution checks green.
- **Deviations:** the broader Linear issue remains Blocked because persisted saved-cost accounting
  is unfinished. This independently shippable Client-only increment does not close or change it.
