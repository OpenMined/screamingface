---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5D model and benchmark discovery notebook

## Intent

Add one generated public notebook that teaches the two deliberately different discovery
boundaries: executable models come from the configured ScreamingFace engine, while canonical
benchmarks come from the installed SDK. The notebook must run with only the local Docker stack,
make no provider or dataset request, and explain benchmark materialization without pretending that
listing and loading are the same operation.

## Planned changes

- Record the approved Phase 5D contract in the benchmark architecture plan and OME-400 task mirror.
- Add `packages/screamingface/scripts/build_discovery.py` and generated
  `packages/screamingface/examples/02_discovery.ipynb`.
- Add append-only notebook-contract tests covering configuration, model and benchmark discovery
  ownership, `query`/`tools`/`limit` filters, and the default-off GPQA loading example.
- Add the discovery notebook to the package README and CI regeneration checks.

## Test plan

- Add the Phase 5D notebook test first and confirm RED because the generator and artifact do not
  yet exist.
- Assert the generated artifact is output-free, deterministic, and contains only valid Python code.
- Assert model discovery uses `sf.models.list(...)` through the configured engine and demonstrates
  `query`, `tools`, and `limit` independently.
- Assert benchmark discovery uses `sf.benchmarks.list(...)`, returns IDs only, and never derives
  results from the engine registry.
- Assert `sf.benchmarks.load("gpqa@1")` is visible but disabled by default, with the Hugging Face
  access and source-materialization boundary explained.
- Assert the notebook contains no Fusion, evaluation, model call, mock, authentication widget,
  raw registry parsing, private API, or direct AI Gateway call.
- Run the complete ScreamingFace gates and all deterministic notebook regeneration checks.

## Acceptance

- `02_discovery.ipynb` runs top-to-bottom with only the local Docker stack.
- Researchers can distinguish engine-backed model discovery from SDK-local benchmark discovery.
- The public filtering examples exactly match the existing `query`, `tools`, and `limit` API.
- Benchmark loading is taught honestly without requiring Hugging Face access during the default run.
- No SDK runtime, engine, URL4, AI Gateway, authentication, or dataset behavior changes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated discovery notebook, builder, notebook-contract tests, and
  this ledger; updated the architecture plan, task mirror, package README, and CI regeneration
  workflow. No runtime file changed.
- **Commits:** pending owner commit for this completed worktree unit.
- **Gates:** append-only enforcement, Ruff lint/format, Pyright, and 389 SDK tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, all four deterministic
  notebook regenerations, package build, and a real top-to-bottom notebook execution green.
- **Deviations:** none. The integration run used the tracked Docker stack on isolated host ports
  14404/19105 because the owner's existing spike owns 4404/9105; only the isolated stack was
  removed after verification.
