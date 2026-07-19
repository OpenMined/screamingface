---
ticket: OME-400
status: approved
phase: 4-contract
date: 2026-07-19
---

# Phase 4 contract — canonical GPQA and DRACO definitions

This record captures the owner-approved Phase 4 decisions. It changes the normative plan,
contract, and syntax fixtures only. No SDK, engine, AI Gateway, test, or notebook runtime behavior
is implemented by this review.

## Reference boundary

The DRACO behavior is based on the executable pipeline in
`../screamingface-benchmarks/notebooks/pipeline_walkthrough.ipynb`, its canonical
`benchmarks_config/draco.yaml`, and the code those entry points invoke. The paper is used to pin
the Appendix F.5 judge prompt and explain the scoring method, but the `draco@1` identity does not
claim literal reproduction of the paper's five-pass Gemini 3 run.

One inconsistency was resolved explicitly: the walkthrough notebook's inline configuration omits
`eval.tools`, even though its prose says it mirrors the pipeline. The canonical YAML and the
validated reproduction use both search and fetch. Phase 5 must correct the notebook; Phase 4 must
not interpret the omission as a tool-free DRACO protocol.

## Canonical GPQA definition

- source: `Idavidrein/gpqa`, subset `gpqa_diamond`, split `train`;
- revision: `633f5ee89ab8ad4522a9f850766b73f62147ffdd`;
- exactly 198 cases with unique non-blank source `Record ID` identities;
- source row order is canonical;
- each record gets one fixed option order derived from SHA-256 over the benchmark identity,
  record ID, and original option position;
- the correct label is computed from the tagged correct option after permutation;
- the input is question, blank line, A-D choices, blank line, and
  `Reply with only A, B, C, or D.`;
- metadata maps source `High-level domain` and `Subdomain` to `domain` and `subdomain`; and
- the complete source/schema is validated before any cases are returned, then normalized cases
  are cached once per researcher process.

## Canonical DRACO definition

- source: `perplexity-ai/draco`, default configuration, split `test`;
- revision: `ce076749809027649ebd331bcb70f42bf720d387`;
- source JSONL SHA-256:
  `e35bfe78cd827fa1d541b79fbc7bc7b91966d3227d8742c83e99d26d4ac4679a`;
- exactly 100 cases, 100 unique source UUIDs, ten domains, four rubric sections per case, and
  3,934 criteria;
- source JSONL order is canonical so `first=` matches the benchmark pipeline;
- `Case.input` is the exact `problem`, `Case.reference` is the complete parsed `answer` rubric,
  and metadata contains `domain`;
- JSON uses duplicate-key rejection and every rubric is fully schema-validated before any cases
  are published; and
- normalized cases are cached once per researcher process.

The source pin and digest are internal definition controls. The public `Benchmark` does not grow
a provenance or hash field in this MVP.

## `draco@1` judge contract

The SDK-local benchmark definition declares:

```json
{
  "type": "rubric",
  "model": "gemini/3.1-pro-preview",
  "prompt": "<exact Appendix F.5 text>",
  "passes": 3,
  "params": {
    "temperature": 0.2,
    "reasoning": "low",
    "max_tokens": 4096
  }
}
```

The exact system prompt is 5,196 UTF-8 bytes with SHA-256
`dbc1ae32e32be6fbc47180b4a246b997d299bb0e25373a8cde87c6461cb2397b`. The public
engine ID is `gemini/3.1-pro-preview`; any Gateway/provider ID remains engine-private.

Each captured Fusion or member answer produces one ordinary judge-model URL4 request for every
criterion and pass. Context is the judge user text containing criterion type, requirement, query,
and response. Intent is the exact Appendix F.5 system prompt. Criterion weights remain hidden.
The SDK allows up to 32 judge requests concurrently for this publication.

Invalid model output alone receives up to two byte-identical retries. Transport, HTTP, timeout,
URL4, and engine-protocol failures are not retried by the SDK. Gateway/provider transient retries
remain an engine-side transport concern. Judge caching is disabled.

The response parser extracts the first JSON object after an optional fence or short preamble and
then requires exactly `explanation` and `criterion_status`, with status `MET` or `UNMET`.
Positive/negative weighting, section scores, overall score, and `pass_rate` use the already
implemented local scoring contract. Unlike the benchmark pipeline's partial-score path, the SDK
requires complete verdict coverage: missing work preserves evidence but yields `score=None`.

## Tool contract

`draco@1` declares `tools=("web_search",)`. ScreamingFace automatically adds it only to the
answer-producing Fusion member routes. It is absent from deterministic reducers, model
synthesizers, and rubric judges.

`web_search` is one public named capability. In the engine profile it includes both searching and
opening/fetching source content, matching the two-tool benchmark pipeline without exposing
provider-specific payloads in the SDK. Every advertised model route needs its own tested adapter.
The adapter must block access to benchmark rubrics, sealed references, and stored benchmark
results.

MVP intentionally excludes public tool budgets, provider selection, Bash, custom blocklists,
tool-profile objects, and tool/cost telemetry. Plaintext URL4 success responses do not change.

## Catalog and engine capability boundary

The engine registry remains restricted to executable response schemas, models with
`supported_tools`, and reducers. It has no benchmark, grader, or aggregator entries. The SDK's
installed benchmark catalog owns IDs and local definitions; those definitions select grader,
aggregator, and required tools.

`draco@1` remains absent from the SDK catalog until its canonical local definition passes its
invariants. It is runnable only when all of these are true:

1. the canonical local cases and benchmark definition pass their invariants;
2. `gemini/3.1-pro-preview` is registered and works through AI Gateway;
3. at least one complete Fusion lineup supports the real `web_search` capability;
4. model/reducer/judge calls complete through SDK -> URL4 engine -> AI Gateway -> provider;
5. real source retrieval is proven and benchmark-source leakage is rejected; and
6. all SDK and engine quality gates pass.

The full reproduction notebook is a stronger Phase 5 gate: it requires the benchmark pipeline's
complete seven-solo/nine-fusion lineup and should not be conflated with local catalog inclusion.

## Implementation gaps recorded at approval time

- GPQA was unpinned, used generated row IDs, and used Python `random` (resolved in Phase 4A);
- the current compiler validates benchmark tools but does not add them to member routes;
- the current engine Gateway adapter rejects `tools`;
- the current profile does not register `gemini/3.1-pro-preview` or advertise any tool support;
- the current AI Gateway model registry does not expose the required Gemini 3.1 route;
- the current SDK judge bound is 16 rather than the approved pipeline-aligned 32; and
- the current DRACO reference text in normative material used five passes/Appendix C.5 and is
  corrected by this review to three passes/Appendix F.5.

No URL4-core modification is authorized or required by this contract. Provider and Gateway gaps
must be resolved through their owners or through the screamingface-engine's public integration
seams, not by patching `packages/url4`.

## Reviewed implementation slices

Implementation still requires explicit owner approval for each slice:

1. canonical pinned GPQA SDK definition and contract tests;
2. hidden canonical DRACO SDK definition and contract tests;
3. compiler member-only tool injection plus engine named-tool adapter and leakage tests;
4. Gemini 3.1 judge route, three-pass/32-way integration, and plaintext parsing tests; and
5. SDK catalog exposure plus complete Docker/provider-backed acceptance proof.

Notebook regeneration and the full DRACO reproduction remain Phase 5.
