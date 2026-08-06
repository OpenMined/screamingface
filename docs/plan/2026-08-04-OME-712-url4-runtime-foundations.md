# OME-712 URL4 runtime foundations — implementation and certification plan

**Ticket:** OME-712
**Spec:** `docs/spec/2026-08-04-OME-712-url4-runtime-foundations.md`

## Goal

Certify the five focused `packages/url4` commits that support Engine-owned benchmark URL4,
remove any defects found by review, and leave a small independently reviewable base for the
AI Gateway and URL4 Cloud layers.

## Review seams

1. **Compiler seam:** public `url4` text evaluation and parsed-AST evaluation must agree.
2. **Command-route seam:** `make_command_handler(..., stdin=...)` determines child stdin and
   rejects invalid selectors.
3. **Observation seam:** emitted usage/span facts preserve provider-reported model identity.

Tests exercise behavior only through those seams. They do not assert private helper call
graphs or mock compiler internals.

## Phase 1 — Establish traceability and baseline

- [x] Mirror OME-712 locally without changing Linear.
- [x] Record the package-level contract in a focused specification.
- [x] Create the work ledger before running tests or modifying Python.
- [x] Run the canonical `url4` gate on the unchanged branch and record the baseline.

## Phase 2 — Review the five-commit diff

- [x] Check text/AST semantic parity, row-name shadowing, dependency direction, and nested
      iteration behavior against the URL4 language specification.
- [x] Check command stdin selection for compatibility, size boundary, error handling, quoting,
      and secret exposure.
- [x] Check response-model attribution for absence semantics and downstream compatibility.
- [x] Identify duplication, dead compatibility paths, misleading comments, and production
      modules made materially less focused by this diff.

## Phase 3 — Correct only evidence-backed defects

- [x] No evidence-backed defect in the three changed contracts required another production
      correction.
- [x] Keep inherited tests append-only; no inherited test was changed, skipped, or weakened.
- [x] Keep adjacent URL4 language behavior outside this benchmark-foundation PR.
- [x] Refactor only changed logic whose complexity obstructs review; none did.

## Phase 4 — Certify and hand off

- [ ] Run `uv run .claude/scripts/run_gates.py url4` from the repository root.
- [ ] Complete the ledger with exact files, gate counts, deviations, and commit evidence.
- [ ] Prepare a reviewer packet covering contract, risks, tests, and the next-layer dependency.
- [ ] Propose, but do not apply, Linear label/status/body corrections and PR operations.

## Explicit process deviations

- OME-712 is an existing cross-cutting issue rather than one sub-issue per landing, per the
  owner's instruction not to create additional issues for this cleanup.
- The implementation predates these local artifacts. This plan certifies and, if necessary,
  corrects that implementation before any further code is added.
- The final PR topology is stacked by explicit owner decision even though the repository guide
  defaults to branches from `main`; that exception must be stated in every affected PR.
