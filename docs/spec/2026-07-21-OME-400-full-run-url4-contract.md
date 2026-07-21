# OME-400 — Full benchmark-run URL4 contract

**Status:** implemented
**Date:** 2026-07-21

This contract supersedes the earlier client-orchestrated benchmark execution boundary. A benchmark
evaluation is one reproducible URL4 expression and one `GET /v1?q=...` request. The ScreamingFace
SDK constructs that expression; the configured ScreamingFace engine loads cases, applies the
slice, executes the Recipe, grades every result, aggregates the selected rows, and returns one
plaintext report.

## Public SDK flow

```python
import screamingface as sf

gpqa = sf.benchmarks.load("gpqa@1")
fusion = sf.Fusion(...)
report = gpqa.evaluate(fusion, first=5)
```

`sf.benchmarks.load(...)` loads an immutable engine-advertised benchmark manifest. It does not
download benchmark rows into the researcher process. `first=5` is compiled into the URL4
iteration slice, so the shareable run expression identifies the exact canonical prefix.

## Engine manifest

`GET /.well-known/screamingface` advertises each benchmark's stable ID, title, case collection
route, grader route, aggregator route, tool requirements, and tool-round policy. For GPQA v1 the
executable routes are:

- `/benchmarks/gpqa/1/cases`
- `/graders/exact-choice/1`
- `/aggregators/mean/1`

The cases route returns NDJSON and registers `application/x-ndjson` with `Url4Node`; that media
type is what makes `$item.input`, `$item.reference`, and other structured row fields available to
the iteration body.

## Canonical expression shape

The exact member graph is produced by the public URL4 builders, but the resulting execution has
this shape:

```url4
(
  /benchmarks/gpqa/1/cases*(
    question=$item.input,
    member_1=/codex/gpt-5.5($question)!'Answer the question.',
    member_2=/gemini/2.5($question)!'Answer the question.',
    member_answers={member_1:'$member_1',member_2:'$member_2'},
    recipe_answer=/reducers/majority-vote/1()!$member_answers,
    recipe_result={
      schema:'screamingface.recipe-result.v1',
      members:{
        member_1:{model:'codex/gpt-5.5',answer:'$member_1'},
        member_2:{model:'gemini/2.5',answer:'$member_2'}
      },
      answer:'$recipe_answer'
    },
    grade_input={case_id:'$item.id',reference:'$item.reference'},
    case_result=/graders/exact-choice/1($recipe_result)!$grade_input
  )!'$case_result';
  iteration.slice=0:5;
  iteration.on_error=collect
)!/aggregators/mean/1()!'Aggregate benchmark results'
```

Mandatory-intent rules from the current URL4 SDK are load-bearing:

- the per-row expression returns the named `case_result` binding with `!'$case_result'`;
- reducer payloads are sent as endpoint intent, not context;
- a grader receives the serialized Recipe result as context and case metadata as intent; and
- the cross-row aggregator is itself an intent-bearing reducer call.

The full shape above has been executed network-free against the current
`OME-466-url4-serve` implementation, including a real half-open `0:1` slice, two member calls,
majority reduction, exact-choice grading, and mean aggregation.

Named tool lists use a colon-delimited scalar parameter (for example,
`tools=web_search:web_fetch`), because the current URL4 parameter grammar permits `:` but not the
earlier `+` separator.

## Response

The engine returns `text/plain` containing exactly one JSON object with schema
`screamingface.report.v1`. It contains benchmark identity, selected case IDs, paired Recipe and
member scores, coverage, failures, and completion state. The SDK validates this strictly and
attaches the original full run expression as `Report.url4`; the engine does not echo the request.

This report requires at least one gradeable paired row. When URL4 collects some failed rows, the
engine reports them alongside scores over the successful paired subset. When every selected row
fails, the aggregator raises the typed `benchmark_evaluation_failed` URL4 error instead of
inventing member identities or returning an all-null score report. Current URL4 collected errors
do not retain the failed source case ID, so partial reports use stable positional failure IDs such
as `row_2`.

## Dataset credentials

Canonical benchmark data is an engine concern. GPQA is not bundled or copied into the SDK or
engine image. The local Docker stack reads `HF_TOKEN` from its environment and the engine uses it
only to load the pinned gated dataset. It is never embedded in URL4 and is never sent to AI
Gateway. The `huggingface` connection shown by `sf.connect()` remains a separate AI Gateway
inference-provider credential.

For a future hosted engine, benchmark-data authorization must be supplied by that deployment's
identity/secret boundary. This MVP does not pretend that a researcher's local Hugging Face login
is automatically available inside a remote deployment.

## Explicit non-goals for this slice

- no client-side case loop, grading, or aggregation;
- no direct SDK traffic to AI Gateway, Tavily, or Hugging Face datasets;
- no bundled GPQA rows or answer keys;
- no compatibility aliases for the old unversioned execution routes; and
- no claim that URL4 yet preserves independent typed failures for every nested named system in a
  full DRACO graph. That remains the separately raised URL4 settlement question.
