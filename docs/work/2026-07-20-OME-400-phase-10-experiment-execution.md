---
ticket: OME-400
stack: screamingface
status: in_progress
started: 2026-07-20
finished:
---

# OME-400 — Model, Fusion, and Experiment execution

## Intent

Add the smallest reusable-system abstraction needed to express and run the historical DRACO
matrix correctly. Researchers should be able to name reusable model calls with `Model`, compose
those same values into existing `Fusion` objects, and evaluate an `Experiment` of models and
Fusions without
regenerating or re-grading shared panel answers. The first worked target is the complete historical
DRACO topology on one case, with unavailable models substituted and the result labeled as a
non-comparable reproduction of the protocol rather than the published scores.

## Public-contract review

Proposed authoring surface:

```python
opus = sf.Model(
    "opus",
    "anthropic/claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT,
    params={"max_tokens": 8192},
)

frontier_trio = sf.Fusion(
    "frontier-trio",
    models=[opus, gpt, gemini],
    reducer=sf.reducers.Model(
        model="anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params={"max_tokens": 8192},
    ),
)

experiment = sf.Experiment(
    "draco-substituted",
    systems=[opus, gpt, gemini, frontier_trio],
)

report = experiment.evaluate("draco@1", first=1)
```

Contract decisions to approve before implementation:

- `Model(name, model, *, prompt, params)` is the typed, reusable model-call leaf.
- Ordinary `Fusion.models` continues accepting model strings and dictionaries, and additionally
  accepts `Model` values. Strings remain the quickstart shorthand for anonymous model leaves.
- `Experiment.systems` accepts only explicitly named `Model` and `Fusion` values so report keys and
  execution identity are stable.
- Reusing the same `Model` value across Fusions means one answer is generated per case and reused.
- Two separately named `Model` values may use the same model route and still produce independent
  samples.
- A Fusion may reference a `Model` that is not listed as a top-level Experiment system; its answer is
  generated and reused but is not independently graded or reported.
- A reducer model call is always a new synthesis call and never aliases a Model response.
- Every system name in an Experiment is unique; named dependency identities are unambiguous across
  the graph.
- Experiment execution emits multiple ordinary URL4 requests rather than one oversized expression:
  shared Model requests first, Fusion synthesis requests second, and judge requests during grading.
- `ExperimentReport.systems` maps each listed system name to its result. An Experiment does not invent a
  single score or `gain`; comparisons remain explicit across the included systems.
- `Suite` remains reserved for running one or more Experiments across multiple benchmarks.

## Planned changes

### Phase 10A — authoring and graph contract

- Add immutable `Model` and `Experiment` public values.
- Allow `Fusion` members to reference `Model` values without breaking string/dictionary shorthand.
- Validate names, dependencies, and duplicate identity before any engine request.
- Add focused value and graph tests before implementation.

### Phase 10B — shared one-case execution

- Compile and execute each required Model exactly once per case.
- Compile Fusion synthesis requests from the reused plaintext Model answers.
- Preserve engine-only model execution, progress, failure, and stop semantics.
- Add request-count and independent-sample tests before implementation.

### Phase 10C — grading and reporting

- Grade each listed Model/Fusion output exactly once using the loaded benchmark grader.
- Aggregate one result per listed system without duplicating member grading.
- Add immutable `ExperimentRun`, `ExperimentGrades`, and `ExperimentReport` values only where staged API parity
  requires them.
- Prove `experiment.evaluate(...)` matches explicit `run().grade().aggregate()` orchestration.

### Phase 10D — one-case DRACO topology notebook

- Express the historical seven model systems and nine Fusions, including the Fusion-only Qwen role.
- Reuse shared model answers exactly as `reuse_panel_answers: true` did historically.
- Use the canonical answer/synthesis prompts, rubric topology, judge passes, parameters, and tool
  requirements where the current engine contract supports them.
- Substitute unavailable model routes explicitly and show the mapping before execution.
- Require an explicit live-run switch because a full 16-system, full-rubric row can make roughly
  1,867 judge calls and historically averaged about $34.87 per source row.
- Label Tavily-versus-OpenRouter search and model substitutions as non-comparable protocol
  reproduction differences.

## Test plan

- RED: `Model` constructor validation, immutability, and stable identity.
- RED: Fusion accepts strings, dictionaries, and Model values with deterministic member IDs.
- RED: Experiment rejects duplicate names and ambiguous dependency identities.
- RED: the same Model reused by multiple Fusions makes one model request per case.
- RED: two distinct Models using the same route make two independent model requests per case.
- RED: Fusion-only Model dependencies execute but are absent from top-level grading/reporting.
- RED: reducer synthesis calls are never deduplicated with Model calls.
- RED: each listed system is graded once and staged execution equals `evaluate()`.
- RED: failures preserve the affected dependency/system graph without converting missing scores to
  zero or silently repeating paid work.
- Run package lint, formatting, type checking, tests, coverage, and append-only test audit.

## Acceptance

- The complete historical DRACO seven-model/nine-Fusion topology can be authored without a custom
  benchmark runner.
- Evaluating one case reuses every named shared Model response across all dependent Fusions.
- The SDK still sends all model and judge requests exclusively to the configured
  screamingface-engine URL4 endpoint.
- An Experiment report exposes one result per listed system and no misleading aggregate score.
- The worked notebook clearly separates protocol parity from result comparability and cannot begin
  the expensive live run accidentally.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** pending
- **Commits:** pending
- **Gates:** pending
- **Deviations:** pending
