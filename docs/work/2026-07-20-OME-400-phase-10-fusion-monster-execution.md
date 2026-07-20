---
ticket: OME-400
stack: screamingface
status: in_progress
started: 2026-07-20
finished:
---

# OME-400 — Model, Fusion, and FusionMonster execution

## Intent

Add the smallest reusable-system abstraction needed to express and run the historical DRACO
matrix correctly. Researchers should be able to name reusable model calls with `Model`, compose
those same values into existing `Fusion` objects, and evaluate a `FusionMonster` of models and
Fusions without regenerating or re-grading shared panel answers. The first worked target is the
complete historical
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

monster = sf.FusionMonster(
    "draco-substituted",
    systems=[opus, gpt, gemini, frontier_trio],
)

report = monster.evaluate("draco@1", first=1)
```

Contract decisions to approve before implementation:

- `Model(name, model, *, prompt, params)` is the typed, reusable model-call leaf.
- Ordinary `Fusion.models` continues accepting model strings and dictionaries, and additionally
  accepts `Model` values. Strings remain the quickstart shorthand for anonymous model leaves.
- `FusionMonster.systems` accepts only explicitly named `Model` and `Fusion` values so report keys
  and execution identity are stable.
- Reusing the same `Model` value across Fusions means one answer is generated per case and reused.
- Two separately named `Model` values may use the same model route and still produce independent
  samples.
- A Fusion may reference a `Model` that is not listed as a top-level FusionMonster system; its
  answer is generated and reused but is not independently graded or reported.
- A reducer model call is always a new synthesis call and never aliases a Model response.
- Every system name in a FusionMonster is unique; named dependency identities are unambiguous across
  the graph.
- FusionMonster execution emits multiple ordinary URL4 requests rather than one oversized
  expression: shared Model requests first, Fusion synthesis requests second, and judge requests
  during grading.
- `FusionMonsterReport.systems` maps each listed system name to its result. A FusionMonster does not
  invent a single score or `gain`; comparisons remain explicit across the included systems.
- `Suite` remains reserved for running one or more FusionMonsters across multiple benchmarks.

## Planned changes

### Phase 10A — authoring and graph contract (implemented)

- Add immutable `Model` and `FusionMonster` public values.
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
- Add immutable `FusionMonsterRun`, `FusionMonsterGrades`, and `FusionMonsterReport` values only
  where staged API parity requires them.
- Prove `monster.evaluate(...)` matches explicit `run().grade().aggregate()` orchestration.

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
- RED: FusionMonster rejects duplicate names and ambiguous dependency identities.
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
- A FusionMonster report exposes one result per listed system and no misleading aggregate score.
- The worked notebook clearly separates protocol parity from result comparability and cannot begin
  the expensive live run accidentally.

## Outcome (current Phase 10A checkpoint)

- **Actual files:** added `Model` normalization and identity to `model_inputs.py`, added the
  network-free `FusionMonster` graph value, exported both public types, added an append-only Phase
  10A suite, and updated the README, architecture plan, normative contract, and OME-400 task
  mirror. No notebook or runtime execution file changed.
- **Commits:** Phase 10A checkpoint — `feat(screamingface): add FusionMonster authoring graph`.
- **Gates:** focused RED then 15/15 GREEN; 56/56 value/compiler compatibility tests; Ruff,
  formatting, and Pyright pass; 451/451 package tests pass when the known quickstart saved-output
  assertion is excluded. The authoritative substantive gate reaches 95.46% coverage and 660/661
  tests; its only failure is the pre-existing modified `00_quickstart.ipynb` output-free assertion.
  The append-only precheck is intentionally skipped because all seven researcher-owned notebooks
  remain modified and untouched.
- **Deviations:** the named dependency order is private implementation state rather than a new
  public inspection property. Phase 10A adds authoring only; execution and reports remain pending.
