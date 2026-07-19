---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 3C complete grading execution

## Intent

Lock the complete `Run.grade()` and model-backed Rubric behavior before changing runtime code.
Preserve the architecture in which ExactChoice is deterministic SDK computation, rubric judges
are ordinary URL4 model calls through the configured engine, and only the engine contacts AI
Gateway.

## Approved public boundary

- `run.grade()` accepts no arguments and returns `Grades` for the captured Run.
- It grades the captured Fusion answer and every captured member answer without rerunning panel
  models or the reducer.
- Failed Run cases receive no grading calls and retain their original `RunFailure` in `CaseGrades`.
- ExactChoice and Rubric are the only supported grader strategies. An unsupported strategy raises
  before grading work begins.
- ExactChoice remains local and deterministic. Rubric uses the configured HTTP URL4 engine.
- Phase 3C does not add aggregation, reports, or `Fusion.evaluate()`; those remain Phase 3D.

## Rubric preflight

Before any judge request, the SDK validates every selected rubric reference together, including a
reference belonging to a case whose captured Run result failed. A valid rubric has:

- at least one section;
- at least one criterion and one positive-weight criterion in every section;
- stable non-blank section identities that remain unique after metric-key normalization and do
  not collide with the reserved `pass_rate` key;
- globally unique non-blank criterion IDs;
- non-blank requirements; and
- finite, non-zero numeric weights, with booleans rejected.

The SDK also confirms that the configured engine still advertises the judge model before judge
traffic begins. Generic URL4 parameter shape remains SDK validation; model-specific parameter
compatibility remains engine-owned so the SDK does not duplicate a drifting provider contract.
The engine must reject incompatible parameters before contacting AI Gateway.

## Judge request protocol

Each successful case produces grading targets in this semantic order: Fusion, then member slots in
their captured Run order. For every target, each pass and criterion produces one ordinary model
expression sent through `GET /v1?q=<URL-encoded-expression>`.

The expression maps:

```text
URL4 model route  -> configured rubric judge model
URL4 parameters   -> configured Rubric parameters
URL4 context      -> criterion type, requirement, question, and captured answer
URL4 intent       -> pinned judge system prompt
```

Weights are not shown to the judge. The context labels a criterion `negative` only when its weight
is below zero; otherwise it is `positive`. Passes contain no salt, pass number, or hidden prompt
mutation. Every pass is a byte-identical independent request, and the engine must leave response
caching disabled for judge work.

The engine returns the judge model output as plaintext. A successful output contains exactly:

```json
{
  "explanation": "The response contains the required fact.",
  "criterion_status": "MET"
}
```

The SDK may extract the first JSON object from a short preamble or Markdown fence, then requires
exactly one non-blank string explanation and a `MET` or `UNMET` status. Duplicate keys or extra
fields are invalid.

## Retries, failures, and ordering

- Invalid judge output alone permits two retries, for three total byte-identical attempts.
- Connection, timeout, HTTP, URL4, and engine-protocol failures receive no SDK retry.
- One failed verdict does not cancel unrelated criteria, passes, targets, or cases.
- At most 16 judge requests run concurrently. This supersedes Phase 3A's proposed 32 because the
  current engine rejects work above its 16-request admission limit.
- Concurrency never changes returned order: cases, targets, passes, criteria, verdict failures,
  and summary failures retain stable semantic ordering.
- A failed verdict retains the final available plaintext response. Earlier malformed retry bodies
  are not separately retained by the MVP's singular `raw_response` field.

## Coverage and scoring

Every expected target/criterion/pass produces one `CriterionVerdict`. An unresolved verdict has
`status=None` and a typed `GradeFailure`.

```text
coverage = resolved verdicts / expected verdicts
```

A score and metrics are published only at `coverage == 1.0`. Otherwise the target retains all
evidence, has `score=None`, empty metrics, and one `incomplete_verdicts` summary failure. Missing
work is never inferred as `UNMET` or converted into a partial score.

For each complete pass, the SDK applies DRACO's positive/negative weighted formula and clamps the
result to `0..1`. The final grade score is the mean pass score. Metrics contain only the unweighted
`pass_rate` and mean weighted section scores. Section identities become deterministic lowercase
underscore keys; collisions are rejected during preflight.

## Verification boundary

Phase 3C tests should exercise a real URL4 node/HTTP boundary with deterministic test handlers;
they must not add a runtime mock mode, an in-process production engine, or direct SDK access to AI
Gateway. Tests cover preflight-before-traffic, ExactChoice dispatch, literal URL4 judge requests,
strict plaintext parsing, validation-only retries, all failure kinds, concurrency bounds, stable
ordering, complete and incomplete scoring, and immutable evidence snapshots.

## Current engine-profile dependencies

The SDK slice can be implemented independently, but canonical DRACO cannot yet run through the
current local profile because:

- `gemini/3.1-pro-preview` is not advertised as a model route; and
- panel routes do not advertise or implement the benchmark's required `web_search` tool.

Those are explicit screamingface-engine profile follow-ups. They are not URL4 package changes and
are not part of Phase 3C.

## Outcome

- **Runtime changes:** implemented public `Run.grade()`, local ExactChoice dispatch, Rubric
  preflight/orchestration, URL4 judge compilation, structured failures/evidence, complete-coverage
  scoring, and shared engine HTTP decoding.
- **Engine-profile changes:** none.
- **Tests:** 270 repository tests pass with 97.6% ScreamingFace coverage; 49 engine-profile tests
  pass with 98.1% coverage. Lint, formatting, typing, fixtures, notebook regeneration, and package
  builds pass.
- **Documentation changes:** recorded the Phase 3C contract and implementation; updated the
  package README, normative spec, plan, task ledger, and Phase 3A concurrency note.
- **Next step:** review Phase 3D aggregation, report, and `Fusion.evaluate()` contracts before
  implementation.
