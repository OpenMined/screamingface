---
ticket: OME-786
stack: screamingface
status: in_progress
started: 2026-08-12
finished:
---

# OME-786 — serial Pipeline and recursive Candidate composition

## Intent

Add the missing serial composition primitive to the public Client while keeping URL4 as the sole
executable representation and preserving the distinction between serial Pipeline and parallel
Fusion.

## Planned changes

- `packages/screamingface/src/screamingface/pipeline.py`, `recipe.py`, `fusion.py`, and public exports
- Candidate compilation, linking, operation projection, result/report, and URL4-to-Python modules
- Pipeline notebook representation under `packages/screamingface/src/screamingface/_ui/`
- new append-only public-interface, compilation, integration, representation, and UI tests
- `CONTEXT.md` and focused Client documentation
- this unit's task mirror, specification, plan, and ledger

## Test plan

- Construct, name, compare, represent, and reject malformed immutable Pipelines.
- Prove `.then()` is exact Pipeline shorthand across Models, Fusions, Pipelines, and model-route
  strings, and rejects ambiguous list arguments.
- Compile serial Model stages and verify exact URL4 data flow and ordered operation dependencies.
- Compile Pipelines nested in Fusion members and synthesizers, and Fusions nested in Pipelines.
- Preserve distinct invocations when one Recipe is rebound to different Pipeline inputs.
- Reject cycles, unsupported Recipe extensions, and obsolete structural Benchmark bindings before
  spend.
- Emit one canonical `screamingface.recipe.v1` descriptor for every complete Recipe URL4 and
  preserve all-before-any preflight.
- Decode/report/export/reconstruct a Pipeline Candidate without relabeling it as a Fusion.
- Render accessible SFDS v2 Pipeline cards in light and dark themes.

## Acceptance

- Researchers can evaluate `sf.Pipeline([...])` against a canonical Benchmark.
- Any complete Recipe can occupy serial stages, parallel members, and the synthesis role.
- `a.then(b).then(c)` constructs the same serial graph as `sf.Pipeline([a, b, c])`.
- Invalid or incomplete graphs fail with clear typed no-spend errors.
- Model, Fusion, and Pipeline use the same required Recipe descriptor with no inference fallback.
- The complete screamingface gate is green without modifying or weakening prior tests.

## Outcome

- **Actual files:** `CONTEXT.md`; `packages/screamingface/README.md`;
  `src/screamingface/{pipeline,recipe,fusion,report,url4}.py`; public exports; Candidate
  compilation/model/replay/topology modules; notebook cards/styles; focused Pipeline, replay,
  preflight, report, and display tests; this unit's spec, plan, task mirror, and ledger.
- **Commits:** pending
- **Gates:** `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` → ALL GATES
  GREEN: Ruff check/format, Pyright, 95% coverage suite, deterministic notebooks, wheel/sdist
  build, and distribution check. Direct package suite before the final focused reconstruction fix:
  688 passed / 1 skipped; the repository gate reran the complete suite after that fix.
- **Deviations:** The owner explicitly selected a clean v1 contract with no compatibility path.
  Existing tests for incomplete Fusions, structural member/synthesizer Benchmark projections,
  Client-side content deduplication, two-member minimums, prose synthesis context, and injected
  generation defaults were therefore replaced with assertions for the new contract. The public
  surface assertion adds `Pipeline`. The sanctioned `--skip-append-only` flag covers these
  intentional Confidence-Gate changes; no production fallback was added to preserve the removed
  behavior.

## Design resolution

Every complete compiled Recipe carries exactly one root `_sf_recipe` source with schema
`screamingface.recipe.v1`. This is the sole authoring-structure contract for replay reporting and
`Url4.to_python()`; neither operation falls back to guessing Model/Fusion/Pipeline topology from the
executable call graph. Nested Recipes live inside that single descriptor rather than adding a
descriptor per nested node.
