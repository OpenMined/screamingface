---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5A DRACO SDK walkthrough

## Intent

Publish an honest generated notebook that teaches the implemented DRACO workflow through the
public ScreamingFace SDK and configured HTTP URL4 engine. The notebook must distinguish a valid
DRACO run for one compatible Fusion from a reproduction of the benchmark pipeline's complete
model comparison, and it must not spend on model or judge calls unless the researcher explicitly
enables live execution.

## Planned changes

- Record the approved Phase 5A contract in the benchmark architecture plan and OME-400 task
  mirror.
- Add `packages/screamingface/scripts/build_draco_walkthrough.py` as the canonical notebook
  generator.
- Add the generated `packages/screamingface/examples/05_draco.ipynb` artifact.
- Add append-only tests for notebook structure, public-SDK usage, live-call gating, accurate
  engine boundaries, and the absence of mocks or reproduction claims.
- Extend ScreamingFace CI/gates to regenerate and diff-check the notebook.

## Test plan

- First add a notebook-contract test and run it before the generator exists to confirm RED.
- Assert the generated notebook uses `sf.config`, `sf.benchmarks.load("draco@1")`, an available
  web-research panel, a model reducer, explicit `run -> grade -> aggregate` stages, and only one
  optional `evaluate` illustration.
- Assert all paid work is dominated by `RUN_LIVE = False`, no mock/in-process/direct-Gateway
  path appears, and the text labels the result as a walkthrough rather than a full reproduction.
- Assert the generator deterministically reproduces the committed notebook.
- Run the complete ScreamingFace gate suite and generated-artifact checks.

## Acceptance

- The notebook is generated, deterministic, clean of saved outputs, and uses only the approved
  public SDK plus the configured HTTP URL4 engine.
- Loading DRACO is documented as SDK-local Hugging Face access; model and judge work is documented
  as engine-only; aggregation is documented as deterministic local Python.
- The default run performs no paid model or judge calls and produces no fabricated result.
- The live path uses the canonical `draco@1` benchmark and warns that one case can require
  hundreds of independent judge requests.
- The notebook makes no full-reproduction claim while the complete benchmark-pipeline lineup is
  unavailable.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated notebook, generator, and notebook-contract tests; updated
  the architecture plan, task mirror, package README, and ScreamingFace CI regeneration step.
- **Commits:** this commit — `docs(screamingface): add DRACO SDK walkthrough`.
- **Gates:** append-only check, Ruff lint/format, Pyright, and 372 package tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, both deterministic notebook
  comparisons, and package build green.
- **Deviations:** the approved review proposed showing one concrete case expression. The public SDK
  intentionally has no `request_for(case)` surface, so the notebook shows `fusion.url4`, the exact
  HTTP request shape, and the response contract without importing `_compiler` or reconstructing a
  request inaccurately. Live provider execution was not performed because it requires external
  provider credentials and hundreds of paid judge requests; the artifact and every code cell were
  validated deterministically.
