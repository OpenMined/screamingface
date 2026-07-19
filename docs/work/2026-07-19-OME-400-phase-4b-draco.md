---
ticket: OME-400
status: implemented
phase: 4b-draco
date: 2026-07-19
---

# Phase 4B — canonical SDK-local DRACO definition

Implemented the owner-approved DRACO source and benchmark-definition slice. The work is local to
the ScreamingFace SDK: no URL4 engine, AI Gateway, compiler, tool-injection, concurrency, or
notebook behavior changed.

## Source and normalization

- loads `perplexity-ai/draco`, default configuration, split `test`, at revision
  `ce076749809027649ebd331bcb70f42bf720d387` through the researcher's Hugging Face session;
- requires exactly the source fields `id`, `problem`, `answer`, and `domain`;
- validates 100 source-order canonical UUID cases across the exact ten-domain set;
- parses every JSON-encoded rubric with recursive duplicate-key and non-finite-constant rejection;
- requires exactly four sections per case, 400 sections total, and 3,934 criteria total;
- requires exact rubric/section/criterion fields, unique rubric IDs across the source, unique
  section and criterion IDs within a case, nonblank identities/text, noncolliding metric keys,
  finite nonzero signed weights, and at least one positive criterion per section; and
- validates the complete source before returning any cases, then caches the immutable normalized
  tuple once per researcher process.

Each source row maps without model-visible reference leakage:

```text
id      -> Case.id
problem -> Case.input
answer  -> parsed, sealed Case.reference
domain  -> Case.metadata["domain"]
```

## Benchmark and judge definition

The SDK catalog now lists `draco@1` with `tools=("web_search",)`. Loading returns a `Benchmark`
using local `Mean` aggregation and the generic `Rubric` grader configured with:

```text
model       gemini/3.1-pro-preview
passes      3
temperature 0.2
reasoning   low
max_tokens  4096
```

The internal official per-criterion system prompt is 5,196 UTF-8 bytes with SHA-256
`dbc1ae32e32be6fbc47180b4a246b997d299bb0e25373a8cde87c6461cb2397b`. The executable pipeline
identifies it as Appendix C.5. The three-pass Gemini 3.1 configuration is pipeline-aligned and
does not claim literal parity with the paper's five-pass Gemini 3 run.

Judge concurrency remains the SDK's internal 16-request execution policy and is not benchmark
configuration. Increasing it requires a separate review with the engine's admission capacity.

## Execution boundary

Benchmark discovery and loading do not contact the configured engine. The current engine cannot
execute DRACO because it lacks the judge route and advertises no `web_search` support. Evaluation
therefore fails capability preflight before `/v1` model traffic. Phase 4C subsequently implemented
member-only benchmark-tool compilation; later engine work still owns the named search-and-fetch
adapter and judge route.

## Live-source verification

The pinned revision passed the complete validator with 100 cases, beginning at
`0c2c668a-c3bf-41af-93c9-b5614ff63508` and ending at
`91408757-a874-44b5-ad5a-66a22b39141d`, across 400 sections and 3,934 criteria.

## Verification

Verification completed on 2026-07-19:

- 313 SDK tests passed with 97% coverage;
- 42 engine tests passed with 97.67% coverage;
- Ruff formatting and lint, Pyright, fixture construction, and notebook drift checks passed;
- the SDK wheel and source distribution built successfully;
- both lockfiles and the engine Compose configuration validated;
- the embedded prompt byte length and SHA-256 matched their pinned values; and
- the live pinned Hugging Face revision passed the complete 100-case validator.
