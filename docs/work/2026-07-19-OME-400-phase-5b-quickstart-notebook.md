---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 5B bare-bones quickstart

## Intent

Publish the shortest honest path from Fusion construction to a paired GPQA comparison using the
public ScreamingFace SDK and configured HTTP URL4 engine. The quickstart should teach only
compose → evaluate → compare, avoid architecture detail already covered elsewhere, and keep the
15 provider-backed model calls in its five-case example behind an explicit default-off live gate.

## Planned changes

- Record the approved Phase 5B contract in the benchmark architecture plan and OME-400 task
  mirror.
- Add `packages/screamingface/scripts/build_quickstart.py` as the canonical notebook generator.
- Add the generated `packages/screamingface/examples/00_quickstart.ipynb` artifact.
- Add append-only tests for notebook structure, minimal public API flow, live-call gating, honest
  prerequisites, and the absence of architecture/legacy surfaces.
- Extend ScreamingFace CI to regenerate and diff-check the quickstart.
- Update the package README to link the new public entry point.

## Test plan

- First add a quickstart-contract test and run it before the generator exists to confirm RED.
- Assert the code uses `sf.config`, one three-member majority-vote Fusion, and one gated
  `fusion.evaluate("gpqa@1", first=5)` call.
- Assert the notebook explains score, baseline, and gain; documents Docker, Hugging Face, provider
  access, and 15 expected model calls; and creates no fabricated result when disabled.
- Assert raw URL4 requests, registry internals, explicit run/grade/aggregate stages, mocks, direct
  Gateway access, and private APIs are absent from the quickstart code and teaching flow.
- Assert every code cell is valid Python and the generator reproduces the committed artifact.
- Run the complete ScreamingFace gates and CI-parity checks.

## Acceptance

- The notebook is generated, deterministic, output-free, and concise.
- It uses only the implemented public SDK and configured HTTP URL4 engine.
- The default run performs no provider-backed calls and produces no substitute report.
- Enabling the live cell evaluates five canonical GPQA cases with three model members and local
  ExactChoice/Mean computation.
- The notebook teaches the three headline comparison values without exposing internals that belong
  in the architecture walkthrough.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the generated quickstart, generator, and notebook-contract tests; updated
  the architecture plan, task mirror, package README, and CI regeneration step.
- **Commits:** this commit — `docs(screamingface): add bare-bones quickstart`.
- **Gates:** append-only check, Ruff lint/format, Pyright, and 377 package tests green at 97.08%
  coverage; 81 engine tests green at 96.54% coverage; Phase 0 fixtures, all three deterministic
  notebook comparisons, and package build green.
- **Deviations:** live provider execution was not performed because the approved notebook defaults
  its 15 external model calls off and requires provider credentials. Every code cell was
  syntax-validated and the output-free artifact was regenerated deterministically.
