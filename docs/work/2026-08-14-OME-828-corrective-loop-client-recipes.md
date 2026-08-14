---
ticket: OME-828
stack: screamingface
status: in_progress
started: 2026-08-14
finished:
---

# OME-828 — Add benchmark-independent corrective Client Recipes

## Intent

Expose `sf.CorrectiveLoop` and `sf.SelfCorrective` as immutable, network-free Recipes
that compile their complete control flow into ordinary Engine-executable URL4 after the
selected Benchmark advertises a check surface.

## Planned changes

- Add the two public Recipe values with root-only compilation and a structural panel floor.
- Compile bounded rounds against the manifest route with no benchmark-specific Client code.
- Extend Recipe topology, editable URL4 reconstruction, replay projection, preflight, and
  notebook examples.
- Fail closed when executable corrective URL4 disagrees with its Recipe metadata.
- Surface the maximum paid check-call count before spend.

## Test plan

- Construction tests cover normalization, composite members, root-only use, round bounds,
  and panels beyond the former LANL four-member limit.
- Compilation tests cover gates, early exit, recursive Recipes, protocol prose, stable
  labels beyond `z`, and topology identity.
- Public replay tests reject undeclared retry calls before transport execution.
- Preflight tests cover absent, free, and paid check surfaces.

## Acceptance

- Changing the Benchmark id is the only Client change needed to run one loop on another
  compatible Benchmark.
- `Url4.to_python()` reconstructs the Recipe only when the entire executable loop matches
  its metadata; direct URL4 replay preserves the same Candidate projection.
- A paid check surface warns with the maximum check calls before execution.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** public corrective Recipes; Client compiler, topology, reconstruction,
  replay, preflight, reporting-kind, UI/notebook, and focused tests.
- **Commits:** PR #598 commits are recorded in the parent OME-796 ledger until squash.
- **Gates:** Client full gate green (Ruff, format, Pyright, tests/coverage, notebooks,
  build, distribution).
- **Deviations:** per-Case loop telemetry requires a Candidate Invocation provenance seam;
  its final disposition is recorded in the parent spec before merge.
