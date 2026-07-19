---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5F custom benchmarks notebook

## Intent

Add one generated public notebook that shows where researcher-owned data preparation ends and the
ScreamingFace benchmark contract begins. Researchers should be able to create local cases, assemble
an immutable benchmark with existing grader and aggregator strategies, understand the sealed
reference boundary, and optionally run that benchmark without introducing an ETL framework.

## Planned changes

- Record the approved Phase 5F contract in the benchmark architecture plan and OME-400 task mirror.
- Add `packages/screamingface/scripts/build_custom_benchmarks.py` and generated
  `packages/screamingface/examples/04_custom_benchmarks.ipynb`.
- Add append-only notebook-contract tests covering case fields, benchmark construction, public
  inspection, researcher-owned loaders, tools, sealed references, and the default-off live path.
- Add the custom-benchmark notebook to the package README and CI regeneration checks.

## Test plan

- Add the Phase 5F notebook test first and confirm RED because the generator and artifact do not
  yet exist.
- Assert the artifact is output-free, deterministic, and contains only valid Python code.
- Assert the primary example creates three `sf.Case` values with stable IDs, exact inputs, sealed
  choice references, and optional metadata.
- Assert `sf.Benchmark` uses a versioned ID, title, `ExactChoice`, `Mean`, and the in-memory cases.
- Assert only the public benchmark definition fields and the researcher's own `cases` variable are
  inspected; no case-iteration SDK is invented.
- Assert the loader alternative stays an illustrative researcher-owned boundary rather than an
  executable ETL dependency.
- Assert benchmark `tools` semantics and the reference/model-request boundary are explicit.
- Assert the optional three-member, three-case evaluation defaults off, documents nine provider
  calls, and creates no substitute report.
- Run complete ScreamingFace gates and all deterministic notebook regeneration checks.

## Acceptance

- `04_custom_benchmarks.ipynb` runs top-to-bottom without Docker, credentials, datasets, or network
  access in its default state.
- The primary benchmark is a real immutable SDK value composed from ordinary local `sf.Case` values.
- Data loading and cleaning remain researcher-owned; ScreamingFace starts at validated cases.
- References are accessible to the researcher and local grader but never compiled into model input.
- The optional live path accurately uses the configured engine and states its call cost.
- No SDK runtime, engine, URL4, AI Gateway, authentication, or dataset behavior changes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated custom-benchmark notebook, builder, notebook-contract
  tests, and this ledger; updated the architecture plan, task mirror, package README, and CI
  regeneration workflow. No runtime file or prior test changed.
- **Commits:** pending owner commit for this completed worktree unit.
- **Gates:** append-only enforcement, Ruff lint/format, Pyright, and 403 SDK tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, all six deterministic
  notebook regenerations, package build, and a fresh-kernel top-to-bottom notebook execution green.
- **Deviations:** none.
