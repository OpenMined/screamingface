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

Share the stacked engine-reference branch, engine handoff specification, and passing gate evidence
with Ionesio. Final app placement and URL4-cloud runner integration remain owner decisions.

## Outcome (fill at completion)

- **Actual files:** Phase 1 standalone SDK plus Phase 2 stacked engine-reference handoff.
- **Commits:** SDK `6700267`; engine-reference is this commit.
- **Gates:** SDK 287 tests/95.15%; engine 432 tests/95.09%; both lint, format, typecheck, and build
  gates green; SDK fixtures and generated notebooks deterministic; rebuilt Docker stack healthy.
- **Deviations:** none.
