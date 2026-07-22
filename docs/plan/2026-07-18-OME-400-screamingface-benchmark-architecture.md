# OME-400 — ScreamingFace benchmark architecture

**Status:** full-run URL4 MVP implemented
**Created:** 2026-07-18
**Last updated:** 2026-07-21
**Normative runtime contract:**
[`2026-07-21-OME-400-full-run-url4-contract.md`](../spec/2026-07-21-OME-400-full-run-url4-contract.md)

This plan describes the current unreleased SDK directly. Earlier client-orchestrated designs remain
available in Git history and dated work notes, but are not compatibility requirements.

## Product boundary

```text
Researcher Python
  ScreamingFace SDK
    typed Model/Fusion and Benchmark manifests
    URL4 construction, preflight, report decoding, notebook UI
             |
             | one GET /v1?q=<complete benchmark-run URL4>
             v
  screamingface-engine
    persistent Url4Node
    benchmark cases, slice, Recipe execution, grading, aggregation
      |                    |                         |
      v                    v                         v
  AI Gateway       route-selected tools    canonical dataset source
  model calls      OpenRouter or Tavily     (GPQA: Hugging Face)
```

Load-bearing rules:

- The SDK contacts only the configured ScreamingFace engine.
- A complete benchmark run is one URL4 expression and one engine request.
- The engine owns benchmark case loading, slicing, model/reducer execution, grading, and
  aggregation.
- Only engine model routes contact AI Gateway. Tool policy is provider-neutral; the engine maps
  OpenRouter routes to managed server tools and verified Hugging Face routes to Tavily.
- Official tool-enabled manifests point to one immutable versioned policy data route. The URL4
  graph resolves it once per case and shares it with answer-producing members through a strict
  model-input envelope. Custom local Benchmarks retain portable inline policy.
- GPQA rows and answer keys are not bundled in the SDK or engine image.
- `HF_TOKEN` is an engine dataset credential and never appears in URL4 or AI Gateway traffic.
- The SDK has no mock engine, in-process runtime, direct Gateway client, or legacy case loop.
- URL4 remains generic. ScreamingFace-specific routes and schemas live in the
  `screamingface-engine` profile.
- Until a hosted deployment exists, the default engine is `http://127.0.0.1:4404`;
  `sf.config(engine=...)` overrides it.

## Public MVP

```python
import screamingface as sf

fusion = sf.Fusion(
    "frontier-trio",
    members=[
        "codex/gpt-5.5",
        "gemini/2.5-flash",
        "claude/sonnet-4.6",
    ],
    reducer=sf.reducers.MajorityVote(),
)

gpqa = sf.benchmarks.load("gpqa@1")
report = gpqa.evaluate(fusion, first=5)
```

`sf.Model` and nested `sf.Fusion` values implement `sf.Recipe`. `sf.benchmarks.load(...)` returns
an immutable engine-advertised manifest; it does not fetch cases into the SDK. The loaded manifest
gives early validation and type discovery before evaluation.

`Benchmark.evaluate(candidate, first=...)`:

1. refreshes and validates the engine registry;
2. validates the loaded manifest, models, reducer, tools, and connections;
3. compiles one full URL4 expression with the benchmark collection and half-open prefix slice;
4. sends exactly one `GET /v1?q=...` request; and
5. strictly decodes the plaintext `screamingface.report.v1` response into `sf.Report`.

The exact expression is retained as `report.url4`, making the selected benchmark prefix and
answer graph shareable together.

## Engine profile

`GET /.well-known/screamingface` advertises providers, models, benchmarks, reducers, response
schemas, and the request-target limit. The GPQA v1 execution graph uses:

- `/benchmarks/gpqa/1/cases`
- `/reducers/majority-vote/1`
- `/graders/exact-choice/1`
- `/aggregators/mean/1`

The persistent `Url4Node` registers these routes in-process. Model routes map URL4 context to the
user message, intent to the system message, and validated params to AI Gateway. Official
tool-enabled runs resolve a versioned `screamingface.tool-policy.v1` route and pass it with the
question as `screamingface.model-input.v1`; custom Benchmarks use `tools.max_calls` plus portable
`web_search.*` inline policy. The route selects OpenRouter-managed tools or the engine-owned Tavily
adapter.

GPQA's cases route returns NDJSON so URL4 iteration exposes structured `$item` fields. The grader
receives the resolved Recipe result as context and sealed case metadata as intent. The aggregator
receives URL4's collected iteration rows as its intent and returns plaintext JSON.

## Failure semantics

- A required model or reducer failure makes that case unsuccessful; it never becomes an empty
  answer or a zero score.
- URL4 collects independent case failures while continuing the selected iteration.
- If at least one case is gradeable, `Mean` returns a paired partial report with typed row failures
  and coverage based only on successful Recipe-versus-members rows.
- If no case is gradeable, the aggregator raises `benchmark_evaluation_failed`; the SDK raises a
  typed engine protocol error instead of fabricating a report or score.
- The SDK performs no automatic retries that could duplicate paid model calls.
- A report baseline is the best member score over the same paired successful cases, and gain is
  `score - baseline`.

Current URL4 collection errors do not preserve the failed source row's case ID, so partial failures
use stable positional IDs such as `row_2`. This is explicit rather than guessing an identity.

## Credentials

- Provider and route-required tool connections travel SDK → ScreamingFace engine → owning service.
  The SDK never talks directly to AI Gateway, OpenRouter, or Tavily.
- The local connection control plane is loopback-only. A future hosted control plane requires
  authenticated user scoping before exposure.
- `HF_TOKEN` is passed to the local engine process for gated benchmark data. The Hugging Face
  inference-provider connection shown by `sf.connect()` is separate.
- Secrets never appear in URLs, engine registries, notebook serialization, or report values.

## Verification gates

- strict constructors and immutable public values;
- registry/model/benchmark discovery and schema rejection;
- canonical mandatory-intent URL4 compilation;
- one-request full GPQA slice through a real `Url4Node` and controlled Gateway transport;
- exact-choice grading and paired mean aggregation, including partial and all-failed inputs;
- transport, HTTP, plaintext, duplicate-JSON, and malformed-report errors;
- SDK and engine coverage independently at or above 95%;
- deterministic generated notebooks;
- Ruff, Pyright, and package build; and
- no `packages/url4` overlay changes in the commit diff.

## Deferred deliberately

- claims that the substituted OpenRouter lineup reproduces the paper's published model ranking;
- shared multi-candidate execution is implemented first for DRACO Lite through one versioned engine
  route and one ordered candidate DAG inside the complete URL4;
- hosted engine identity and dataset-secret policy;
- uploads or remote registration for researcher-authored benchmarks; and
- retries, persistence, resume, billing, or leaderboard publication.

The local engine now advertises `draco-preview@1`, `draco-lite@1`, and `draco@1` only when the
pinned OpenRouter judge is part of AI Gateway's startup model snapshot. Preview uses the real cases
with one positive criterion and one pass. Lite fixes the workload to the first pinned case,
keeps five deterministic criteria spanning all four rubric sections, and uses one pass. Production uses all 100 complete rubrics and
five passes. Exact published-result claims still require an audited full run with the original
pinned model/provider configuration. The Lite profile's candidate-set route executes shared nodes
once and preserves independent root outcomes; production adoption remains a deliberate later gate.

## Repository map

```text
packages/screamingface/src/screamingface/
  public values, registry client, compiler, one-request evaluator, report UI

packages/screamingface/apps/screamingface-engine/
  temporary package-local persistent Url4Node application and Docker stack

packages/screamingface/examples/
  generated quickstart, architecture, discovery, fusion, authoring, connection, and DRACO notebooks

docs/spec/2026-07-21-OME-400-full-run-url4-contract.md
  normative wire/runtime contract
```
