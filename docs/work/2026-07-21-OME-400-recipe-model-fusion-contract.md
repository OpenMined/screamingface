---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-21
finished: 2026-07-21
---

# OME-400 — Recipe, Model, and Fusion contract

## Intent

Replace the overly broad definition “every answer recipe is a Fusion” with a vocabulary that
matches ordinary researcher expectations:

- `Recipe` is the shared URL4-backed answer interface;
- `Model` is an atomic Recipe backed by one model route; and
- `Fusion` is a composite Recipe that combines Models and/or nested Fusions.

The SDK is unreleased. The owner explicitly approved this clean replacement of the immediately
preceding recursive-Fusion checkpoint; no `inputs=` or atomic-Fusion compatibility surface is
retained.

## Approved public contract

```python
opus = sf.Model(
    "anthropic/claude-opus-4.8",
    name="opus-sample-1",
    prompt=DRACO_ANSWER_PROMPT,
    params={"temperature": 0.7},
)

frontier = sf.Fusion(
    "frontier-trio",
    members=[opus, gpt, gemini],
    reducer=sf.reducers.Model(...),
)

draco = sf.benchmarks.load("draco@1")
report = draco.evaluate(frontier, first=1)
solo_report = draco.evaluate(opus, first=1)
```

Rules:

- `sf.Model(model_id, *, name=None, prompt=None, params=None)` is the deliberately small leaf API.
- `sf.Fusion(name, *, members, reducer)` is always composite.
- `Fusion.members` accepts Models, Fusions, and model-ID strings as concise default-Model
  shorthand; dictionaries are rejected.
- Public `Fusion.members` is normalized to Model/Fusion values immediately.
- Reusing one object shares execution identity. Repeated strings or separately constructed
  Models remain independent calls.
- A Model name defaults to its model ID. Explicit names disambiguate independent samples.
- Both Model and Fusion expose the same network-free `.url4`; the loaded Benchmark owns
  `.evaluate(candidate, ...)` and sends the complete run as one URL4 request.
- Runtime metadata and the plaintext engine envelope use “recipe”, not “fusion”, where the value
  can represent either public type.
- No top-level `sf.run`, `sf.evaluate`, or `sf.compare` is added in this MVP.

## Implementation plan

1. Add failing value, graph, compiler, and solo-evaluation tests.
2. Add the non-constructible Recipe base/common behavior and the immutable Model leaf.
3. Make Fusion composite-only with normalized `members=`.
4. Generalize compiler, execution, requirements, grading, reports, progress, and the engine
   response envelope from Fusion to Recipe.
5. Update current docs, fixtures, generators, notebooks, and engine-profile fixtures with no
   compatibility aliases.
6. Run the complete configured gate under the owner-approved append-only Confidence-Gate
   exception.

## Acceptance

- Quickstart strings remain concise while inspection returns real Model/Fusion member values.
- A standalone Model can compile and be evaluated by a Benchmark without being called a Fusion
  anywhere in its public record.
- Nested Fusions and shared Model/Fusion objects still compile into one URL4 DAG per case.
- Current documentation contains one vocabulary: Recipe is the umbrella; Model is atomic; Fusion
  is composite.
- Full repository gates are green.

## Outcome

- **Actual files:** added `recipe.py`, `model.py`, and the Phase 10B contract tests; replaced the
  recursive-Fusion implementation and terminology across compiler, execution, results, engine
  profile, normative docs, fixtures, generators, and regenerated public notebooks.
- **Gates:** full `run_gates.py screamingface --skip-append-only` green: Ruff, formatting,
  Pyright, 95% SDK and engine coverage gates, fixture checks, notebook freshness, and wheel build.
- **Commit:** pending owner handoff.
- **Deviations:** the append-only test check was skipped under the recorded owner-approved clean
  replacement because the obsolete Phase 10A recursive-Fusion contract test was deleted. No
  runtime compatibility alias was retained. URL4-to-Recipe importing remains separate OME-408
  work because the current expression does not yet preserve every author-facing name losslessly.
