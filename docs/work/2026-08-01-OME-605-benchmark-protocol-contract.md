---
ticket: OME-605
stack: screamingface
status: active
started: 2026-08-01
---

# OME-605 — Linked Benchmark and Candidate expressions

## Intent

Keep Candidate and Benchmark authoring minimal while preserving one complete, independently
executable URL4 per Candidate. Validate the design against every executable benchmark in the
latest `screamingface-benchmarks` checkout rather than treating DRACO as the universal shape.

## Decision

- Keep `screamingface.benchmark.v1`; the response represents a Benchmark, not a “program.”
- Replace the YAML manifest and Candidate-specific POST plan with one JSON Benchmark GET carrying
  a canonical Candidate-independent expression in `url4`.
- Compile the Candidate expression in the SDK and link it structurally through `$candidate`.
- Invoke it inside the Engine through the universal `/candidate` interface with `$input` bound.
- Use “Benchmark expression,” “Candidate expression,” and “Candidate Invocation”; avoid program,
  manifest, plan, workflow, harness, and template for the new contract.
- Keep Benchmark authoring in ordinary Engine-side Python returning typed URL4 nodes; add only a
  `candidate(input)` builder and no Client-interpreted DSL.

The accepted rationale and rejected alternatives are recorded in
`docs/adr/0001-link-benchmark-and-candidate-expressions.md`.

## Capability evidence

Throwaway probes against the installed URL4 runtime established that a bound expression is data
and a binding cannot choose a dynamic route, while static dependencies do carry earlier results.
A second probe used the public `Url4Node.evaluate(expression, env=...)` interface behind a generic
route and successfully invoked the same Candidate twice; the second input included the first
answer. No `url4` package change or nested control-plane request was required.

## Compatibility baseline

- Repository: `OpenMined/screamingface-benchmarks`
- Revision: `23524fdb60de5a56c7618339cc0423303997f529`
- Profiles: `draco`, `healthbench`, `medxpert`, `scicode`
- Existing fixed SDK runner: DRACO only

## Test plan

- Benchmark GET decoding and structural linking through sync/async Client interfaces.
- Candidate default and override precedence through public Model/Fusion construction.
- `/candidate` execution invariants for Model, Fusion, state, tools, usage, cancellation, and
  failures.
- Benchmark expression fixtures for all four benchmark families.
- Runtime capability failure before paid execution.
- Raw and encoded full-suite URL4 size gates.
- DRACO URL4 Cloud unit/integration and live lifecycle execution.
- Full lint, type, coverage, notebook-blob, build, and distribution gates.

## Outcome

The foundational vertical slice is implemented:

- URL4 Cloud serves one cacheable JSON Benchmark resource and no Candidate-specific planning POST.
- DRACO builds a Candidate-independent typed URL4 expression through the shared `Benchmark`
  authoring boundary.
- The SDK compiles Candidate policy locally, links the two ASTs once per Candidate, and uses a
  single Benchmark fetch for an Evaluation of any number of Candidates.
- The Runner's reserved `/candidate` route executes Model and nested Fusion expressions in-process
  with bounded recursion/calls and inherited cancellation, errors, and usage.
- The same boundary preserves HealthBench-style native histories, MedXpert-style reasoning/commit
  turns, and SciCode-style ordered code/sandbox state in representative execution tests.
- A deterministic cross-package DRACO run now covers the actual Engine definition, SDK linker,
  Runner Candidate Invocation, three fixed Judge passes, and production Aggregation code.
- The linked full-suite DRACO URL4 remains compact because Case iteration is not statically
  expanded: a Model measured 1,925 raw / 2,435 encoded-query bytes, and a two-member Fusion
  measured 2,589 raw / 3,265 encoded-query bytes. The corresponding one-Case expressions were
  slightly larger because they carry an explicit slice (1,945 / 2,461 and 2,609 / 3,291 bytes).
- The complete Python package suite passes with 345 tests and 14 skips; the complete URL4 Cloud
  suite passes with 644 tests and 5 skips. Ruff and Pyright pass for both projects.

SciCode, HealthBench, and MedXpert adapters, their full transport-size gates, notebook fixture
reconciliation, and live paid execution remain before OME-605 is complete. The wheel and source
distribution checks pass; the notebook check is intentionally left failing rather than overwriting
the user's two edited notebooks.

## Prospective IFEval compatibility

The IFEval reference kit reviewed on 2026-08-02 contains the pinned 541-row `google/IFEval`
dataset and the Apache-licensed Python verifier at commit
`0c495b2f95155e8b10acb919ae283bfb4d5be6e2`. Standard IFEval fits the accepted boundary without an
SDK change: one text Candidate Invocation per Case, one Engine-owned programmatic verifier call
using that Case's instruction IDs and kwargs, and an aggregate over prompt/instruction accuracy
under strict and loose readings. The Benchmark image must pin the verifier, `langdetect`, and
vendored NLTK `punkt`/`punkt_tab` data so grading remains offline and comparable. The official
verifier's randomized non-ASCII preprocessing must also be preserved and reported rather than
quietly "fixed."

The archive's LANL checker-in-the-loop ensemble is a separate Candidate algorithm, not part of the
IFEval grading protocol. The current opaque Fusion returns one final string, so it cannot faithfully
expose each member to mid-loop verification, conditionally retry failed members, and tie-break only
compliant member outputs. Standard IFEval and ordinary Model/Fusion comparisons work now; exact
LANL reproduction requires an explicit future Candidate strategy/interface. It must not add
IFEval-specific dispatch to the SDK or weaken the universal Benchmark resource.
