---
ticket: OME-400
stack: screamingface
status: in_progress
started: 2026-07-22
finished:
---

# OME-400 — Split the ScreamingFace SDK from its engine reference

## Intent

Make the researcher SDK independently releasable while preserving the working engine as a later,
stacked owner handoff. The checkpoint branch remains the complete historical spike.

## Phase 1 changes

- Created `OME-400-screamingface-sdk` from current `origin/main`.
- Restored only current SDK implementation, examples, public contracts, fixtures, and package
  registration changes.
- Removed the temporary engine app and all engine-owned canonical benchmark, grading, and reduction
  implementations from the SDK package.
- Removed the engine-only `datasets` dependency and refreshed the lockfile.
- Split Pytest, Pyright, CI, SDLC, documentation, and notebook setup from the engine source tree.
- Kept all tracked generated notebooks as researcher-facing SDK documentation.

## Verification

- Ruff lint: pass.
- Ruff format: pass.
- Pyright: pass.
- Pytest: 287 passed; 95.15% SDK coverage.
- Executable contract fixtures: pass.
- Deterministic notebooks: pass.
- Wheel and source distribution: pass.
- `git diff --check`: pass.
- No `screamingface_engine`, `screamingface._benchmarks`, `screamingface._exact_choice`, or
  `screamingface._reduction` import remains in SDK production/tests.

## Remaining work

Create the stacked `OME-400-screamingface-engine-reference` branch, relocate the engine-owned
implementations into its namespace, remove every private SDK import from engine production code,
and run its independent engine plus public-SDK integration gates before handoff.

## Outcome (fill at completion)

- **Actual files:** Phase 1 SDK split implemented; Phase 2 pending.
- **Commits:** pending.
- **Gates:** SDK-only gate green as recorded above.
- **Deviations:** none.
