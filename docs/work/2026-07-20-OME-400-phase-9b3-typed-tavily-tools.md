---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 9B.3 typed Tavily tool policy

## Intent

Replace benchmark string tool names with immutable, typed Tavily search and extract policies.
Make the benchmark own a required tool-round budget, compile the complete stable policy into each
answer-producing URL4 model request, and keep reducers and graders tool-free. This phase defines
the reproducible SDK-to-engine contract only; Phase 9B.4 will execute the resulting Tavily agent
loop inside ScreamingFace Engine.

## Planned changes

- Add public `sf.tools.TavilySearch` and `sf.tools.TavilyExtract` value objects with the approved
  Tavily request-policy fields and strict cross-field validation.
- Change `sf.Benchmark.tools` to accept only typed tool objects and require
  `max_tool_rounds` whenever tools are configured; remove legacy string-tool support.
- Compile deterministic scalar URL4 parameters for tool IDs, tool rounds, Tavily search policy,
  Tavily extract policy, and numbered domain filters on every fusion member request.
- Keep reducer requests tool-free and preserve string tool IDs only on registry/discovery
  boundaries where the engine advertises capabilities.
- Migrate the built-in DRACO definitions, specifications, documentation, fixtures, and generated
  notebooks to the typed contract without adding a Tavily Python dependency or tool execution.

## Test plan

- RED: public tool values cover defaults, immutability, every enum/range/type boundary, dates,
  domain limits, and approved cross-field invariants.
- RED: benchmarks reject strings, duplicate tool kinds, missing/invalid round budgets, and round
  budgets on tool-free definitions.
- RED: compilation emits a stable parseable URL4 expression with the complete tool policy on
  members only and no tool parameters on the model reducer.
- RED: execution preflight derives capability IDs from typed tools and still rejects unsupported
  model/tool combinations before model requests.
- GREEN: run focused SDK tests, deterministic notebook checks, and the authoritative
  ScreamingFace gate without installing a Tavily client library.

## Acceptance

- Researchers configure Tavily through `sf.tools.TavilySearch(...)` and
  `sf.tools.TavilyExtract(...)`, never an untyped parameter dictionary or legacy string.
- Tool-enabled benchmarks require an explicit positive `max_tool_rounds`; tool-free benchmarks
  keep it `None`.
- A Fusion evaluation serializes one deterministic, shareable URL4 request policy per member;
  reducers and graders receive no benchmark tools.
- Registry/discovery continues to expose ordinary capability strings such as `web_search` and
  `web_fetch`, while benchmark definitions remain typed.
- No Tavily credential appears in a benchmark, URL4 expression, model prompt, response, or log.
- No Tavily Python dependency, AI Gateway change, or premature tool-loop implementation is added.

## Outcome

- **Actual files:** added the public immutable `sf.tools.TavilySearch`/`TavilyExtract` values and
  strict validation; changed Benchmark, compiler, execution preflight, built-in DRACO definitions,
  discovery metadata, tests, fixtures, README, plan/spec/task records, and the generated custom
  benchmark notebook to the typed contract.
- **Commits:** `feat(screamingface): add typed Tavily benchmark tools` (this commit).
- **Gates:** 40 focused Phase 9B.3 tests and all 436 SDK tests passed.
  `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` passed Ruff
  lint/format, Pyright, SDK and engine coverage thresholds, fixture checks, deterministic notebook
  checks, and wheel build.
- **Deviations:** the append-only precheck was skipped under the owner's approved clean break
  because the unreleased string-tool tests and examples had to move to typed values; their member-
  only and reducer-free invariants were retained. Search/extract execution, HF tool advertisement,
  SearXNG removal, and live DRACO acceptance remain Phase 9B.4/9B.5 as planned. No Tavily Python
  dependency or AI Gateway change was added.
