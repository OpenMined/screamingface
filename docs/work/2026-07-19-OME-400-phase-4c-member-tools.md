---
ticket: OME-400
status: implemented
phase: 4c-member-tools
date: 2026-07-19
---

# Phase 4C — member-only benchmark-tool compilation

Implemented the owner-approved SDK compiler slice. It carries benchmark-required named
capabilities through URL4 without implementing or advertising any engine capability.

## Public behavior

`Benchmark.tools` remains the only MVP declaration point. Tool IDs are ordered, unique lowercase
identifiers matching `[a-z][a-z0-9_]*`. The protocol key `tools` is reserved from generic member,
model-reducer, and rubric-grader parameters; any future member-specific capability selection must
receive an explicit API rather than masquerading as a sampling parameter.

`fusion.url4` remains a benchmark-independent shareable recipe, and `run.fusion_url4` preserves
that same recipe. During execution only, the compiler overlays the selected Benchmark's tools on
every answer-producing member call:

```url4
member_1=/codex/gpt-5.5?tools=web_search&q=($question)!'Answer the question.'
```

Multiple ordered capabilities use URL query encoding:

```url4
tools=web_search+code_execution
```

URL4 decodes that parameter for the endpoint as `"web_search code_execution"`. Deterministic
reducers, model reducers/synthesizers, and rubric judges do not inherit the overlay. Tool-free
benchmarks retain byte-identical compilation.

## Safety and execution boundary

Preflight still requires every Fusion member to advertise every benchmark tool before concrete
expressions or `/v1` traffic. Case inputs are the only benchmark data sent to member routes;
references and rubrics remain local and sealed. The engine registry is now validated against the
same tool-ID syntax, but the development engine remains honestly tool-free.

This phase does not change `screamingface-engine`, AI Gateway, URL4, authentication, concurrency,
notebooks, budgets, or telemetry. DRACO therefore remains non-runnable until a separately reviewed
engine slice adds a real `web_search` search-and-fetch adapter, compatible registry claims, and the
`gemini/3.1-pro-preview` judge route.

## Verification

Verification completed on 2026-07-19:

- 321 SDK tests passed with 97.09% coverage;
- 42 unchanged engine tests passed with 97.67% coverage;
- Ruff formatting and lint, Pyright, fixture construction, and notebook drift checks passed;
- single- and multiple-tool expressions round-tripped through a real `Url4Node` with member-only
  decoded parameters;
- the SDK wheel and source distribution built successfully; and
- both lockfiles and the engine Compose configuration validated.
