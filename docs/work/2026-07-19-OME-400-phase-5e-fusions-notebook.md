---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5E Fusion construction notebook

## Intent

Add one generated public notebook that teaches the complete network-free Fusion authoring surface
without mixing construction with discovery or execution. Researchers should understand concise
model IDs, explicit per-member configuration, duplicate-model sampling, deterministic and
model-backed reducers, and the public values available for inspection.

## Planned changes

- Record the approved Phase 5E contract in the benchmark architecture plan and OME-400 task mirror.
- Add `packages/screamingface/scripts/build_fusions.py` and generated
  `packages/screamingface/examples/03_fusions.ipynb`.
- Add append-only notebook-contract tests covering concise and explicit member forms, shared and
  overridden prompts, scalar parameters, duplicate model IDs, reducer semantics, and public
  inspection values.
- Add the Fusion notebook to the package README and CI regeneration checks.

## Test plan

- Add the Phase 5E notebook test first and confirm RED because the generator and artifact do not
  yet exist.
- Assert the generated artifact is output-free, deterministic, and contains only valid Python code.
- Assert the concise example uses string model IDs, a shared prompt, and `MajorityVote`.
- Assert the explicit example uses only the public `model`, `prompt`, and `params` mapping fields.
- Assert a self-Fusion repeats one model ID with different prompts/parameters and uses a public
  `sf.reducers.Model(...)` configuration.
- Assert the notebook inspects only `models`, `model_ids`, `reducer`, and `url4`, and correctly
  explains stable order, scalar parameters, reserved `tools`, and reducer call counts.
- Assert the notebook contains no configuration, discovery, benchmark, run, evaluation, YAML,
  private compiler, HTTP, mock, or authentication path.
- Run complete ScreamingFace gates and all deterministic notebook regeneration checks.

## Acceptance

- `03_fusions.ipynb` runs top-to-bottom without Docker, credentials, datasets, or network access.
- The string and mapping forms have one clear rule: use strings by default and mappings only for
  member-specific overrides.
- Duplicate model IDs and the distinction between deterministic and model-backed reducers are
  accurately explained.
- Construction and `.url4` remain visibly network-free; compatibility is deferred to execution.
- No SDK runtime, engine, URL4, AI Gateway, authentication, or dataset behavior changes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated Fusion notebook, builder, notebook-contract tests, and this
  ledger; updated the architecture plan, task mirror, package README, and CI regeneration workflow.
  No runtime file or prior test changed.
- **Commits:** pending owner commit for this completed worktree unit.
- **Gates:** append-only enforcement, Ruff lint/format, Pyright, and 396 SDK tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, all five deterministic
  notebook regenerations, package build, and a fresh-kernel top-to-bottom notebook execution green.
- **Deviations:** none.
