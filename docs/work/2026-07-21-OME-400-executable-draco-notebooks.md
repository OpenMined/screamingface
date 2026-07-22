# OME-400 work ledger — executable DRACO notebooks

## Goal

Provide one minimal real-data DRACO workflow and one complete architectural walkthrough backed by
an executable ScreamingFace-engine contract, using model routes currently available through the
local AI Gateway/OpenRouter profile.

## Decisions

- `draco-preview@1` is explicitly non-comparable: real cases, one positive criterion, one judge
  pass, full research-tool flow.
- `draco-lite@1` is a bounded protocol-faithful study: the first pinned case, five deterministic
  criteria spanning all four rubric sections, and one judge pass per criterion.
- `draco@1` uses the complete pinned rubric and five independent per-criterion passes.
- The engine advertises all three only when the pinned OpenRouter Gemini judge route exists.
- A DRACO Lite candidate study is one full URL4 and one HTTP request for the ordered candidate set.
- Recipe object identity defines shared nodes; separately constructed equal Models remain separate
  sampled calls.
- Candidate failures are isolated and only final candidate answers are graded.
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
- Added the 7-solo/9-Fusion candidate-set compiler, versioned engine evaluator, candidate
  aggregator, and strict immutable `StudyReport` decoder.

## Verification

- Focused candidate-study tests: 44 SDK tests and 34 engine tests passed.
- Full ScreamingFace-engine suite: 305 passed, 95.03% coverage.
- Full SDK suite: 698 passed, 95.08% coverage. Two unrelated notebook-shape assertions fail only
  because the preserved local `00_quickstart.ipynb` has executed outputs and a newer model
  selection than its generator.
- SDK and engine static gates: Ruff and Pyright pass.
- Both new DRACO notebooks match their deterministic builders exactly and every code cell compiles.
- Live local smoke: the registry advertises `draco-preview@1`, `draco@1`, and all eight substituted
  OpenRouter model routes. The SDK compiled a one-case preview into one 1,111-character URL4 with
  the expected case route, rubric grader route, and `iteration.slice=0:1`; no paid call was made.
- URL4 SDK and AI Gateway source trees remain unchanged.
