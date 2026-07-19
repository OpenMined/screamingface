---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5C configuration and architecture notebook

## Intent

Replace the broad Phase 1 development walkthrough with one public architecture notebook that
explains the stable ScreamingFace SDK/engine boundary. It must run top-to-bottom against the local
Docker stack without provider credentials, show one real deterministic URL4 transaction, and keep
benchmark authoring and paid evaluation in their dedicated tutorials.

## Planned changes

- Record the approved Phase 5C replacement contract in the benchmark architecture plan and
  OME-400 task mirror.
- Add `packages/screamingface/scripts/build_architecture.py` and generated
  `packages/screamingface/examples/01_architecture.ipynb`.
- Add append-only architecture-notebook tests covering public configuration, registry discovery,
  URL4 recipe semantics, GET transport, deterministic reducer execution, plaintext parsing, and
  component ownership.
- Remove the explicitly superseded `phase_1_engine_profile.ipynb` and its generator.
- Replace the Phase 1 CI regeneration step and README references with the architecture notebook.

## Test plan

- First add a new architecture-notebook contract test and run it before the new generator/artifact
  exist to confirm RED.
- Assert every code cell is valid Python and the artifact is output-free and deterministic.
- Assert the notebook uses `sf.config`, raw registry inspection plus `sf.models.list()`, one local
  Fusion recipe, and one real `GET /v1?q=...` deterministic majority-vote request.
- Assert the request uses a canonical URL4 expression from public URL4 builders or a validated
  fixture, returns raw plaintext, requires no model/provider/dataset access, and never imports a
  private compiler or engine implementation.
- Assert the ownership table keeps dataset/reference/grading/aggregation work in the SDK process
  and model/tool execution behind the engine.
- Run complete ScreamingFace gates, all notebook regeneration checks, engine coverage, fixtures,
  and package build.

## Acceptance

- `01_architecture.ipynb` replaces the Phase 1 development artifact without retaining overlapping
  public documentation.
- The notebook runs with only the Docker stack and performs no paid or provider-backed call.
- It accurately distinguishes `fusion.url4` from a concrete encoded URL4 transaction and shows
  the real plaintext response boundary.
- It contains no benchmark loading, Fusion evaluation, runtime fallback, direct Gateway call,
  private compiler import, or in-process engine.
- Documentation and CI name only the current generated notebook series.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated architecture notebook, builder, and notebook-contract tests;
  removed the approved Phase 1 notebook/builder; updated the architecture plan, task mirror,
  package README, and CI regeneration step.
- **Commits:** pending owner commit for this completed worktree unit.
- **Gates:** append-only check, Ruff lint/format, Pyright, and 382 package tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, all three deterministic
  notebook comparisons, package build, and a real top-to-bottom notebook execution green.
- **Deviations:** none. The integration run used an isolated tracked stack on host ports
  14404/19105 because the owner's older spike owns 4404/9105; only the isolated stack was removed
  after verification.
