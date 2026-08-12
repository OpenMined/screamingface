---
title: Serial Pipeline and recursive Candidate composition
ticket: OME-786
status: approved
date: 2026-08-12
---

# Serial Pipeline and recursive Candidate composition

## Outcome

Researchers can express serial model pipelines and arbitrarily nest the Client's serial and
parallel composition structures without authoring raw URL4 or moving benchmark protocols into the
Client.

`sf.Pipeline([...])` is the canonical serial value. `Recipe.then(...)` is immutable shorthand for
constructing that same value. `sf.Fusion([...], synthesizer=...)` remains the explicit parallel
fan-out-and-synthesis value.

## Domain model

- A **Recipe** is an immutable, network-free description of Candidate-owned answer production.
- A **Model** is one atomic model-backed Recipe.
- A **Pipeline** is an ordered serial Recipe whose stages are Recipes.
- A **Fusion** is an ordered parallel collection of Recipe members followed by a synthesizer.
- A **complete Recipe** accepts one input and produces one final answer.
- Every public Recipe is complete. A bare multi-output fan-out is not a Recipe.
- A **Candidate** is the complete root Recipe selected for evaluation; nested values remain Recipes.

The root public type determines the Candidate kind: `model`, `fusion`, or `pipeline`. Nested
topology remains visible through ordered operations rather than being flattened into a misleading
kind.

## Public interface

```python
pipeline = sf.Pipeline(
    [model_a, model_b, model_c],
    name="draft-review-final",
)

candidate = sf.Fusion(
    [
        model_d,
        pipeline,
        sf.Fusion([model_e, model_f], synthesizer=model_g),
    ],
    synthesizer=sf.Pipeline([judge, writer]),
)

chained = model_a.then(model_b).then(model_c)
constructed = sf.Pipeline([model_a, model_b, model_c])
assert chained.stages == constructed.stages
```

The value interfaces are:

```python
Pipeline(stages: Sequence[str | Recipe], *, name: str | None = None)

Fusion(
    members: Sequence[str | Recipe],
    *,
    name: str | None = None,
    synthesizer: str | Recipe,
)

Recipe.then(next_recipe: str | Recipe) -> Pipeline
```

A route string normalizes immediately to `Model(route)` anywhere a Recipe is expected. Explicit
`Model(...)` remains available for prompts, parameters, and names. `.then()` accepts exactly one
complete Recipe or route string and never accepts a list, performs network access, or executes
work. Lists acquire meaning only inside the explicit `Fusion([...])` and `Pipeline([...])`
constructors. There is no fluent `.Fusion(...)` method whose meaning changes between scalar and
list arguments.

Recipes are immutable configuration values with structural equality. Names participate in value
equality and provenance but never alter executable model requests. Graph position, rather than
Python object identity or equality, defines one logical invocation.

## Serial semantics

- A Pipeline contains at least one stage.
- The first stage receives the Pipeline input.
- Every later stage receives only the immediately preceding stage's final answer.
- No original input or accumulated stage history is injected implicitly.
- A failed stage prevents downstream stages from executing.
- Pipelines flatten only where doing so is behaviorally and representationally lossless; an
  explicitly named nested Pipeline retains its grouping.

Original-input or history carrying is a future explicit context capability, not hidden Pipeline
behavior.

## Recursive composition

Models, Fusions, and Pipelines may be Pipeline stages, Fusion members, or Fusion synthesizers.
Consequently a Pipeline may contain a Fusion, a Fusion may contain Pipelines, and a Fusion may use
a Pipeline or Fusion to synthesize its member answers. A Fusion contains at least one member and
always requires its explicit `synthesizer=` keyword.

Structural Benchmark protocols do not obtain incomplete Fusion internals from the Client.
Benchmark-independent strategies such as a corrective loop become their own complete Recipe types
and pass through the same `$candidate` seam. Canonical Benchmarks consuming the whole `$candidate`
accept any complete Recipe. Genuine input/output incompatibilities fail during authoritative
Engine preflight before spend.

## Compilation invariants

- Compilation emits ordinary Engine-executable URL4 and uses the existing `sf.evaluate(...)`
  lifecycle; Pipeline introduces no execution endpoint or second protocol.
- Fusion member order and Pipeline stage order are stable.
- Operation dependencies faithfully distinguish serial edges from parallel fan-out and synthesis.
- Every graph placement creates a distinct logical invocation, even when the same Recipe object or
  an equal Recipe value appears more than once. The compiler never merges placements. Engine cache
  policy may reuse the result of each stable invocation across replays but cannot collapse two
  declared positions into one invocation.
- Every reachable model route and explicitly supplied parameter set participates in all-before-any
  no-spend preflight. The SDK emits no universal generation parameter defaults; a parameter-free
  Model delegates parameter defaults to its provider/model contract.
- Cycles and malformed local structure fail without network access. Engine-owned facts such as
  route availability, parameter support, credentials, Benchmark compatibility, capabilities, and
  execution limits are validated authoritatively by the Engine before paid execution.
- Every complete Recipe URL4 carries one root `_sf_recipe` descriptor using the
  `screamingface.recipe.v1` schema. Replay and Python reconstruction require that canonical
  descriptor; there is no call-graph inference fallback.

## Fusion semantics

- Every Fusion member receives the same Fusion input and executes as an independent parallel
  branch.
- Any member failure fails the Fusion and prevents synthesis. Partial panels, quorum behavior, and
  fallback are separate future Recipes.
- The synthesizer receives one URL4-native canonical JSON object containing the original input and
  ordered outputs:

  ```json
  {
    "input": "original request",
    "outputs": {
      "member_1": "first answer",
      "member_2": "second answer"
    }
  }
  ```

  URL4 performs runtime substitution and JSON escaping. Display names are excluded from this
  executable context.
- A Pipeline used as synthesizer receives that context at its first stage; later stages retain
  normal previous-output-only Pipeline semantics.
- Fusion carries no prompt or generation defaults. Configuration belongs to its Model Recipes.
  No parameters propagate implicitly through nested Recipes.

## Prompt and parameter policy

- The SDK retains documented answer and synthesis prompts for route-string convenience.
- A Model in an ordinary answer position uses the answer default when no prompt is supplied.
- A direct Model synthesizer, or the first stage of a synthesizer Pipeline, uses the synthesis
  default when no prompt is supplied. Later Pipeline stages use the ordinary answer default.
- An explicit prompt completely replaces the role default; no hidden text is appended or merged.
- The SDK no longer injects `max_tokens=4096`, `web_search=false`, or any other model/request
  parameter. Every model-call parameter emitted by the SDK represents an explicit user choice.
  An omitted parameter, including `web_search`, uses the Engine's configured default. A Benchmark
  may still impose an explicit execution policy in its own URL4 protocol.
- URL4-to-Python reconstruction omits an effective prompt only when it equals the applicable SDK
  role default. It preserves every parameter present in executable URL4, including an explicit
  `max_tokens=4096`.

## Validation and limits

- Constructors are network-free and validate local type, non-empty collection, required
  synthesizer, cycle, and structural invariants.
- The Client does not invent expression-byte, operation-count, Recipe-node, or public nesting-depth
  limits. URL4 Cloud owns and reports real execution limits. Untrusted topology decoding uses safe
  traversal and converts malformed or resource-exhausting inputs into clear errors without
  presenting parser safeguards as product limits.
- Recipe is a sealed public interface in v1. Unknown subclasses fail clearly until a deliberate
  compilation-extension interface exists.

## Results and representation

Pipeline roots report `kind="pipeline"`. Ordered operation metadata, failures, usage, export,
notebook representation, and supported URL4-to-Python reconstruction preserve serial structure.
The notebook card follows SFDS v2 in both light and dark themes and represents serial flow without
using colour as the only encoding.

`Url4.to_python()` reconstructs semantic Recipe configuration rather than the caller's original
Python spelling. It preserves routes, explicit parameters, non-default prompts, names, named
Pipeline groups, topology, and ordering; shorthand, comments, and variable names are not
recoverable. The executable URL4 remains the effective-behavior source of truth, while
`screamingface.recipe.v1` records topology only and is checked against executable dependencies.

## Exclusions

- Arbitrary DAG or raw URL4 Candidate authoring.
- Bare multi-output fan-out without synthesis.
- Routing, cascading, retry loops, boosting, voting, early exit, or other control-flow policies.
- `MajorityVote`, `ChooseBest`, `CorrectiveLoop`, presets, routers, or placeholder interfaces for
  those future complete Recipes.
- Hidden original-input/history propagation.
- Generalizing Engine Benchmark checking or aggregation.
- A fluent `.Fusion(...)` builder.

## Compatibility

This is the clean v1 interface and intentionally provides no legacy aliases or fallback compiler:

- incomplete Fusion construction is rejected;
- `models=`, `steps=`, and other constructor aliases are not accepted;
- old URL4 without `screamingface.recipe.v1` is not reconstructable through `to_python()`;
- the removed generation default is not emulated; and
- explicitly configured existing parameters remain stable, while parameter-free Model/Fusion URL4
  intentionally stops carrying `max_tokens=4096` and Fusion URL4 intentionally adopts structured
  synthesis context.

Those capabilities may later compose with Recipe, but this unit does not guess their interfaces.
