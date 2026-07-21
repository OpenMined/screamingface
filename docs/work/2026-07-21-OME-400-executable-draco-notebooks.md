# OME-400 work ledger — executable DRACO notebooks

## Goal

Provide one minimal real-data DRACO workflow and one complete architectural walkthrough backed by
an executable ScreamingFace-engine contract, using model routes currently available through the
local AI Gateway/OpenRouter profile.

## Decisions

- `draco-preview@1` is explicitly non-comparable: real cases, one positive criterion, one judge
  pass, full research-tool flow.
- `draco-lite@1` is a bounded realistic run: the first two pinned cases, their complete rubrics,
  and two independent per-criterion judge passes.
- `draco@1` uses the complete pinned rubric and five independent per-criterion passes.
- The engine advertises all three only when the pinned OpenRouter Gemini judge route exists.
- A benchmark run is one full URL4 and one HTTP request per candidate.
- The SDK remains the URL4 constructor and strict response decoder. All cases, tools, models,
  grading, and aggregation execute behind the ScreamingFace engine.
- No URL4 SDK or AI Gateway source is modified.

## Implementation

- Added real DRACO, Lite, and Preview case routes around the SDK's pinned dataset validator.
- Added the versioned DRACO rubric grader with strict MET/UNMET parsing, two validation retries,
  official weight semantics, per-pass statistics, axis metrics, and bounded judge concurrency.
- Added rubric grader configuration to the strict engine manifest decoder.
- Preserved rubric metrics through mean aggregation.
- Added `Benchmark.url4(...)` for spend-free inspection of the complete reproducible transaction.
- Added local OpenRouter startup seeds for all substituted DRACO model routes.
- Made generated `05_draco_quickstart.ipynb` the bounded DRACO Lite walkthrough; retained
  `08_draco_explained.ipynb` as the full architecture reference and updated OpenAPI/README.

## Verification

- Focused SDK DRACO/compiler/registry/progress tests: 91 passed.
- Focused engine DRACO/catalog/profile/benchmark tests: 44 passed.
- Full ScreamingFace-engine suite: 279 passed, 95.07% coverage.
- SDK static gates: Ruff and Pyright pass.
- Full combined SDK/engine suite: 650 passed and 95.01% coverage; two notebook-shape assertions
  fail only because the preserved local `00_quickstart.ipynb` has executed outputs and a newer
  model selection than its generator.
- Both new DRACO notebooks match their deterministic builders exactly and every code cell compiles.
- Live local smoke: the registry advertises `draco-preview@1`, `draco@1`, and all eight substituted
  OpenRouter model routes. The SDK compiled a one-case preview into one 1,111-character URL4 with
  the expected case route, rubric grader route, and `iteration.slice=0:1`; no paid call was made.
- URL4 SDK and AI Gateway source trees remain unchanged.
