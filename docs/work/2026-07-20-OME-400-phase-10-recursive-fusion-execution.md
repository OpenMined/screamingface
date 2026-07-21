---
ticket: OME-400
stack: screamingface
status: in_progress
started: 2026-07-20
finished:
---

# OME-400 — Recursive Fusion execution

## Intent

Make `sf.Fusion` the one public answer-recipe node. An atomic Fusion calls one model; a composite
Fusion reduces the answers of one or more input Fusions. Raw model IDs remain concise anonymous
leaf shorthand. Reusing an explicit Fusion shares its result, nested Fusions form a DAG, and
`sf.evaluate([...], benchmark=...)` selects multiple roots for comparison. This directly expresses
the historical DRACO seven-baseline/nine-composite matrix without a second graph-container type.

This contract deliberately replaces the immediately preceding Phase 10A checkpoint. The SDK is
unreleased and the researcher explicitly approved removing `sf.Model` and `sf.FusionMonster`
rather than retaining compatibility aliases or tests for discarded concepts.

## Approved public contract

Atomic answer recipe:

```python
opus = sf.Fusion(
    "opus",
    model="anthropic/claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0.7, "max_tokens": 8192},
)
```

Recursive composition:

```python
frontier_trio = sf.Fusion(
    "frontier-trio",
    inputs=[opus, gpt, gemini],
    reducer=sf.reducers.Model(
        model="anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"max_tokens": 8192},
    ),
)

refined = sf.Fusion(
    "refined",
    inputs=[frontier_trio],
    reducer=sf.reducers.Model(
        model="anthropic/claude-opus-4.8",
        prompt="Critique and improve the answer.",
    ),
)
```

Concise quickstart shorthand:

```python
fusion = sf.Fusion(
    "frontier-trio",
    inputs=[
        "anthropic/claude-opus-4.8",
        "openai/gpt-5.5",
        "google/gemini-3.1-pro-preview",
    ],
    reducer=sf.reducers.MajorityVote(),
)
```

Multiple selected roots:

```python
report = sf.evaluate(
    [opus, gpt, frontier_trio, refined],
    benchmark="draco@1",
    first=1,
)
```

Contract rules:

- A Fusion is a shareable answer recipe. It calls one model directly or combines answers from
  other Fusions.
- Atomic mode requires `model`; it permits `prompt` and `params` and rejects `inputs`/`reducer`.
- Composite mode requires one or more `inputs` and one `reducer`; it rejects `model` and atomic
  model-call configuration.
- Composite inputs accept explicit Fusions or raw model-ID strings. Each raw string is a distinct
  anonymous leaf with the default answer prompt.
- One composite input is valid when the reducer performs refinement or another transformation.
- Reusing the same explicit Fusion object means one execution per case. Separately constructed
  Fusions remain independent even when their route and configuration match.
- Explicit names are unique across one selected union graph. Cycles fail before any engine call.
- A root graph compiles topologically into one URL4 expression per case; shared bindings execute
  once in the URL4 engine.
- `sf.evaluate([...])` grades only selected roots. Unselected dependencies still execute but are
  not independently reported.
- `Fusion.evaluate(benchmark, ...)` remains the one-root quickstart facade.
- `sf.Model`, `sf.model`, `sf.FusionMonster`, `sf.Experiment`, `sf.Solo`, and `sf.Lineup` do not
  exist.

## Planned changes

### Phase 10A-R — recursive authoring and compiler foundation

- Replace the discarded `Model`/`FusionMonster` checkpoint with atomic/composite Fusion modes.
- Rename `models=` to `inputs=` everywhere with no fallback alias.
- Normalize raw strings into private anonymous leaf calls; remove public Python configuration
  dictionaries in favor of explicit atomic Fusions.
- Validate variant state, names, shared identity, and recursive graph structure network-free.
- Compile one recursively nested root into one URL4 DAG while preserving flat quickstart behavior.
- Update current tests, generated-notebook sources, normative docs, and examples as one explicitly
  approved greenfield Confidence-Gate change.

### Phase 10B — multi-root case execution

- Add `sf.evaluate(roots, benchmark=..., first=..., progress=...)`.
- Compile the union graph once per selected case and return every selected root in one keyed
  plaintext response.
- Preserve atomic per-case failure semantics, request-size preflight, engine-only execution, and
  object-identity reuse.

### Phase 10C — multi-root grading and reports

- Grade each selected root exactly once with the loaded benchmark grader.
- Keep local exact grading and separate DRACO criterion/pass judge requests.
- Aggregate one result per selected root without inventing one overall score or gain.
- Preserve staged run/grade/aggregate parity for the multi-root API.

### Phase 10D — graph visualization and DRACO notebook

- Render the same recursive graph as compact terminal text and rich notebook HTML/SVG.
- Make shared nodes, reducers, selected roots, and dependency-only nodes visually distinct.
- Express all historical DRACO roots with explicit substitutions and one guarded live case.
- Label model/search substitutions as non-comparable and disclose the historical one-row judge
  load before paid execution.

## Test plan

- RED: atomic/composite constructor modes, immutability, and parameter ownership.
- RED: recursive inputs, one-input transformations, shorthand leaves, and no discarded aliases.
- RED: shared object identity, independent equal configurations, duplicate names, and cycles.
- RED: flat and nested URL4 recipes use one binding per shared node and one root result.
- RED: multi-root compilation uses one expression per case and returns only selected roots.
- RED: selected-root grading happens once while dependencies are not implicitly graded.
- RED: staged execution equals the `sf.evaluate(...)` facade.
- Run Ruff, formatting, Pyright, coverage, complete package tests, and the append-only audit. The
  planned replacement of the committed Phase 10A test is explicitly approved and recorded here;
  notebook source is synchronized from the generators without replacing saved outputs, execution
  counts, or kernel metadata.

## Phase 10A-R result — 2026-07-20

Complete:

- one immutable recursive `sf.Fusion` value now owns both atomic and composite answer recipes;
- recursive compilation emits one URL4 DAG, evaluates shared Fusion identities once, and keeps
  flattened atomic `member_n` evidence for baseline and gain;
- atomic Fusions are runnable and aggregate against themselves (`baseline == score`, `gain == 0`);
- nested reducer models, deterministic reducer routes, provider connections, and tool support are
  all included in preflight across the complete graph;
- public dict inputs and the discarded `Model`/`FusionMonster` source and tests are removed;
- README, normative architecture/spec, fixtures, generators, and current notebook source use the
  recursive contract; and
- 451 focused SDK tests, 205 screamingface-engine tests, Ruff, and Pyright pass. The focused recursive
  Url4Node test executes the complete nested expression and proves shared leaf reuse.

The authoritative gate uses the owner-approved `--skip-append-only` Confidence-Gate exception for
this clean replacement. After the owner approved resolution, all seven public notebooks were
regenerated as canonical output-free artifacts. The complete configured gate is green: Ruff lint
and format, Pyright, SDK coverage tests, engine coverage tests, Phase 1 fixtures, notebook
freshness, and wheel build.

Phases 10B through 10D remain unimplemented and require their own review/execution gates.

## Acceptance

- The quickstart remains a short inline-string Fusion.
- Atomic model baselines and arbitrary nested compositions use the same public Fusion type.
- The full DRACO root matrix can share dependencies without a custom runner or graph container.
- One case sends one generation URL4 expression, and the SDK never contacts AI Gateway directly.
- No discarded Phase 10A aliases, source files, tests, or documentation remain.

## Outcome (fill at the end)

- **Actual files:** pending
- **Commits:** pending
- **Gates:** pending
- **Deviations:** pending
