---
ticket: OME-843
stack: screamingface
status: in_progress
started: 2026-08-17
finished:
---

# OME-843 (client slice) — Tolerate and surface per-operation outputs in the case result contract

## Intent

Lockstep prerequisite for the engine-side member-output capture (OME-843, sub-issue of
OME-784): the Client's case decoder rejects unknown case-row keys by design, so it must
learn the optional `operations` key BEFORE any engine emits it. Absent field → behavior
and exports byte-identical; present → member/synthesis outputs surface on
`CaseResult.operations` and through `report.json`. A dedicated Linear sub-issue for this
client slice is pending (Linear MCP token expired mid-session); it will be filed under
OME-784 and this ledger updated.

## Planned changes

- `packages/screamingface/src/screamingface/case_result.py` — new `CaseOperation` value
  (`operation_id`, `output`, `finish_reason`); `CaseResult` gains optional
  `operations: tuple[CaseOperation, ...] | None`; `to_dict()` emits the key only when
  present.
- `packages/screamingface/src/screamingface/_evaluation/results.py` — `_case_result`
  tolerates optional `operations`; strict per-entry decode (`_case_operation`).

## Test plan

- RED in `tests/test_case_outcome_decoding.py` (append-only): decode + exact round-trip
  with `operations`; absent key → `operations is None` and no key in export (byte-identical
  invariant); per-entry strictness (unknown/missing entry keys, blank operation_id reject);
  other unknown case keys still reject (strictness intact).

## Acceptance

- Old-shape payloads decode and export exactly as today; new payloads round-trip the
  `operations` key; screamingface stack gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `case_result.py` (CaseOperation + CaseResult.operations +
  conditional export), `_evaluation/results.py` (optional key + `_case_operations` /
  `_case_operation` strict decode), `tests/test_case_outcome_decoding.py` (+7 tests,
  append-only).
- **Commits:** (filled post-commit)
- **Gates:** run_gates.py screamingface ALL GREEN — ruff check/format, pyright, pytest
  859 passed/1 skipped (cov ≥95), notebook check, uv build, distribution check,
  append-only test check.
- **Deviations:** dedicated client sub-issue not yet filed (Linear MCP token expired
  mid-session); unit runs under OME-843 with the client slice named in this ledger.
  `CaseOperation` deliberately not added to the public `sf.` namespace in this slice —
  reachable via `CaseResult.operations`; exporting it is a follow-up decision.
