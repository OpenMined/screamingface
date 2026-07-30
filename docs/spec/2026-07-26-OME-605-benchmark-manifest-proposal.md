---
title: SF Engine Benchmark Manifest v1 proposal
ticket: OME-605
status: proposed
date: 2026-07-26
---

# SF Engine Benchmark Manifest v1 proposal

## Decision requested

Publish one canonical immutable YAML document for every registered Benchmark revision. The
manifest contains every Benchmark-owned, non-dynamic rule needed to reproduce and validate a
submission.

## Five-minute owner review

OME-587 has already settled how a real URL4 is executed locally or when hosted. This proposal does
not add another runner, change `url4-cloud`, or make the SF Client call AI Gateway. It asks the SF
Engine owners to confirm only the no-spend planning interface used before the Client submits each
Candidate URL4 to the existing runner.

The approved Client behavior is:

```text
Recipe values
  -> Client resolves one pinned Benchmark Manifest
  -> Client constructs one complete URL4 per Candidate
  -> Engine parses, canonicalizes, and inspects each URL4 without paid execution
  -> Client returns the Engine-validated Plan
  -> run(plan) submits those URL4s through the proven OME-587 lifecycle
```

Four owner decisions unblock implementation:

1. **Manifest resource:** confirm the stable-name and immutable-revision routes, caller
   authentication, media type, and not-found/unauthorized errors.
2. **Identity:** confirm that the canonical YAML bytes are returned with an immutable Benchmark
   ID and digest, and that changing any score-affecting rule creates a new revision.
3. **Compilation ABI:** confirm which strict typed manifest fields or graph templates let the
   Client construct Candidate → grade → aggregate URL4 without Benchmark-specific Client code.
4. **First DRACO revision:** identify the exact cases, prompts, Tool policy, Judge, passes,
   grading, and aggregation configuration that may be named `draco@1`.

Recommended minimum resource interface:

```http
GET /v1/benchmarks/draco/manifest
Accept: application/yaml
```

```http
200 OK
Content-Type: application/yaml
Content-Location: /v1/benchmarks/draco@1/manifest
ETag: "sha256:..."
Content-Digest: sha-256=:...:
```

The manifest needs only the common envelope and the typed sections that affect scientific
meaning:

```yaml
schema: screamingface.benchmark-manifest.v1
id: draco@1
title: DRACO

cases: {}
answer: {}
grading: {}
aggregation: {}
```

`synthesis` and `provenance` are optional when relevant. Candidate lineups, selected limits,
credentials, capability negotiation, cache infrastructure, transport settings, results, and
usage never belong in this document.

The exact copy-paste owner question is:

> Can SF Engine expose one immutable YAML Benchmark Manifest resource with the identity and cache
> semantics above, and confirm the typed compilation ABI the Client uses to construct a complete
> Candidate URL4 before submitting it to the proposed no-spend inspection interface and the
> existing OME-587 execution lifecycle? For the first implementation, which exact DRACO
> configuration should be pinned as `draco@1`?

Everything below is supporting detail for those four decisions. It is not four additional public
Client interfaces.

Manifest v1 must support the known Benchmark families from its first release:

- single-turn prompted generation, including DRACO;
- native multi-turn conversations and repeated samples, including HealthBench;
- generated multi-turn answer protocols, including MedXpert;
- stateful workflows and sandbox grading, including SciCode; and
- exact-match, rubric, model-judged, and sandbox grading followed by typed aggregation.

The format must not be shaped around DRACO alone. It uses one small common envelope and typed
protocols for the stages that genuinely vary. Simple Benchmarks remain short; only advanced
Benchmarks pay for advanced configuration.

DRACO itself uses only the `single_turn` answer protocol. Its Fusion Synthesis, rubric grading,
and aggregation are later evaluation stages and must not be represented as additional Candidate
answer turns.

The manifest is the friendly file that authors review and share and the authoritative protocol
that the Engine validates and serves. It does not contain a Candidate lineup, start execution, or
expose credentials and infrastructure.

## Recommended HTTP contract

```http
GET /v1/benchmarks/draco/manifest
Accept: application/yaml
```

The stable-name request returns the currently selected immutable revision and its canonical URL:

```http
Content-Type: application/yaml
Content-Location: /v1/benchmarks/draco@1/manifest
ETag: "sha256:..."
Content-Digest: sha-256=:...:
Cache-Control: no-cache
```

`GET /v1/benchmarks/draco@1/manifest` must always return the same semantic document. Changing any
Benchmark-owned case source, prompt, answer protocol, Tool policy, Synthesis default, grading
rule, aggregation rule, or referenced workflow behavior creates a new Benchmark revision.

The immutable response may use `Cache-Control: private, max-age=31536000, immutable`; the moving
stable-name alias must always revalidate.

## Manifest model

Every manifest has the same top-level shape:

```yaml
schema: screamingface.benchmark-manifest.v1
id: example@1

cases: {}
answer: {}
grading: {}
aggregation: {}
```

Optional Benchmark-owned sections such as `synthesis` and `provenance` are added only when
relevant.

`answer.protocol`, `grading.protocol`, and `aggregation.protocol` are discriminators. Each
protocol has a strict versioned schema; they are not arbitrary option dictionaries. Adding a new
protocol must not change the common manifest envelope.

## Case input contract

The manifest is YAML, but runtime Case inputs are structured JSON. The versioned Case-source
route yields ordered candidate-visible values with one minimal common envelope:

```json
{
  "id": "case-42",
  "input": {
    "question": "Explain the staggered-adoption critique of TWFE."
  }
}
```

- `id` is the stable identity of the Case within the immutable Benchmark revision.
- `input` contains everything the Candidate may see.

The Benchmark's versioned Case-input schema validates `input`. The common v1 envelope does not
include generic `metadata`, `attributes`, or `dimensions` fields, and it never contains hidden
rubrics, correct answers, tests, or aggregation slices.

The Case-source route is a URL4 execution source, not a requirement to publish the underlying
dataset as a browsable public API. SF Engine may back it with a database, JSONL file, pinned
dataset snapshot, or another immutable store. That storage choice is private to Benchmark
registration.

Hidden evaluation data remains inside SF Engine. The grading route receives a `case_id` and the
Candidate outcome, then resolves the corresponding rubric, reference answer, or hidden tests
internally. Hidden evaluation data must never appear in Candidate inputs, Client Plans, URL4
expressions, ordinary Client Reports, or Client-addressable Case responses.

## Case outcome contract

Candidate execution produces one strict JSON success/failure value per Case. This is an Engine
runtime contract, not YAML authored by a researcher and not part of the Benchmark Manifest.

Model success:

```json
{
  "case_id": "case-42",
  "status": "succeeded",
  "output": "The final Candidate answer."
}
```

Failure:

```json
{
  "case_id": "case-42",
  "status": "failed",
  "failure": {
    "stage": "candidate",
    "code": "gateway_timeout",
    "message": "The model request timed out.",
    "retryable": true,
    "operation_id": "op_answer_2"
  }
}
```

A Fusion success may additionally contain ordered direct `members`, each with the same
success/failure semantics. A successful outcome has `output` and never `failure`; a failed outcome
has `failure` and never `output`. Generic Fusion execution passes only successful member outputs
to the Reducer, preserving their relative declared order and identities. One successful member is
sufficient to attempt reduction. A Fusion may therefore succeed while retaining failed-member
evidence; it fails when no member succeeds or its Reducer fails.

`output` may be any value permitted by the answer protocol's schema; v1 Model and Fusion output is
normally text. Timing, usage, Tool calls, and transport Events remain execution evidence rather
than fields in this semantic value.

The SF Client may later expose typed Case outcomes for detailed inspection, but ordinary Reports
remain summaries and do not embed every raw answer. The SF App consumes typed Client values and
Events through its sidecar rather than depending directly on this raw Engine JSON.

## Case grade contract

Grading settles every selected Case into one runtime JSON value. A successful grade contains
finite numeric `metrics` and may include `evidence` typed by the manifest's grading protocol:

```json
{
  "case_id": "case-42",
  "status": "succeeded",
  "metrics": {
    "normalized_score": 0.72,
    "pass_rate": 0.8
  },
  "evidence": {
    "verdicts": [
      {
        "criterion_id": "criterion-1",
        "status": "MET",
        "explanation": "The response explains negative weighting."
      }
    ]
  }
}
```

When Candidate execution or grading prevents a usable grade, the same Case position contains a
typed Failure:

```json
{
  "case_id": "case-42",
  "status": "failed",
  "failure": {
    "stage": "grading",
    "code": "judge_invalid_response",
    "message": "The judge returned an invalid verdict.",
    "retryable": true,
    "operation_id": "op_grade_1"
  }
}
```

`failure.stage` distinguishes at least `candidate` and `grading`. A successful Case Grade has
`metrics` and never `failure`; a failed Case Grade has `failure` and never `metrics` or
`evidence`. The contract does not duplicate a generic top-level `score`: the manifest's
`aggregation.primary_metric` identifies the primary metric.

Timing, usage, Judge transcripts, and transport telemetry are execution evidence rather than
semantic grade fields. Ordinary Reports remain summaries; a later typed detail surface may expose
protocol evidence without making the SF App consume raw Engine JSON.

## Candidate result contract

The Benchmark's aggregation route consumes the ordered settled Case Grades and returns one
runtime JSON `CandidateResult` for the independently executed Candidate:

```json
{
  "schema": "screamingface.candidate-result.v1",
  "benchmark": {
    "id": "draco@1",
    "manifest_digest": "sha256:..."
  },
  "case_counts": {
    "selected": 5,
    "succeeded": 5,
    "failed": 0
  },
  "metrics": {
    "normalized_score": 0.66,
    "pass_rate": 0.72,
    "coverage": 1.0
  },
  "members": [
    {
      "operation_id": "op_01K_opus",
      "failures": []
    },
    {
      "operation_id": "op_01K_gpt",
      "failures": []
    }
  ],
  "failures": []
}
```

`case_counts.succeeded + case_counts.failed` must equal `case_counts.selected`. Metrics contain
finite numeric values only. The Manifest identifies the primary metric; the Engine result does
not duplicate it as a generic `score` field. The Client's `CandidateResult.score` is a convenience
view of that named metric, not Client-side grading or aggregation.

V1 publishes aggregate metrics only when every selected Case has a successful Case Grade. After
the responsible operational layer exhausts its bounded attempt policy, any failed Case makes that
Candidate unscored:
`metrics` is absent, the failed Case remains visible in `case_counts`, and the ordered typed
Failures are retained. Other Candidates continue independently.

This rule distinguishes benchmark evidence from operational failure:

- a valid Candidate output that is wrong, empty, refused, unparsable, times out inside a
  successfully operated benchmark sandbox, or otherwise fails the Benchmark's answer semantics
  may receive a legitimate zero-valued Case Grade; but
- a provider timeout, unavailable Tool, failed Synthesis request, invalid Judge response, or
  sandbox-infrastructure failure is a typed Failure and is never silently converted into a zero
  score.

A Fusion with one failed direct member may still produce a successful Case Outcome when at least
one member succeeds and Synthesis produces a valid answer. The member Failure remains visible,
but the Case itself is not failed merely because it was degraded. This is generic Recipe
execution behavior and cannot vary between Benchmark manifests.

The Manifest therefore does not expose a generic `exclude | zero | fail` switch. Benchmarks that
define a missing or invalid answer as incorrect express that through their grading protocol, not
by reclassifying infrastructure failures. If aggregation itself fails after complete grading,
aggregate metrics are absent and an `aggregation` Failure is present.

An exhausted failed Case therefore returns a valid but unscored Candidate Result:

```json
{
  "schema": "screamingface.candidate-result.v1",
  "benchmark": {
    "id": "draco@1",
    "manifest_digest": "sha256:..."
  },
  "case_counts": {
    "selected": 5,
    "succeeded": 4,
    "failed": 1
  },
  "members": [],
  "failures": [
    {
      "stage": "grading",
      "code": "judge_invalid_response",
      "message": "The judge returned an invalid verdict.",
      "retryable": true,
      "operation_id": "op_grade_1",
      "case_id": "case-42"
    }
  ]
}
```

`members` is always present: empty for a Model and one entry per direct Fusion member in declared
order. Each entry contains only its opaque stable `operation_id` and owned Failures. Names, Recipe
kinds, and model routes come from the inspected Plan and are not duplicated. The
Client validates that every planned direct member appears exactly once, so equal-looking
independent members remain distinct.

Run identity, URL4, timestamps, duration, usage, and transport state are not duplicated in the
Candidate Result. The Client combines the validated Candidate Result with the corresponding Plan
and lifecycle Events to construct one `CandidateResult`; ordered Candidate Results form the final
multi-Candidate `Report`.

## Failure contract

Every domain Failure retained by a Case Outcome, Case Grade, Candidate Result, Candidate Result,
or Report has one shape:

```json
{
  "stage": "candidate",
  "code": "gateway_timeout",
  "message": "The model request timed out.",
  "retryable": true,
  "operation_id": "op_answer_2",
  "case_id": "case-42"
}
```

`stage`, `code`, `message`, `retryable`, and `operation_id` are required. `stage` is one of
`candidate`, `grading`, or `aggregation`. `code` is lowercase snake_case. `case_id` is optional
only because aggregation-level Failures may not belong to one Case.

The contract deliberately excludes HTTP status, arbitrary details, timestamps, attempts,
provider/model names, and stack traces. Those are transport or execution evidence available
through the Plan and lifecycle Events. Failure messages must be safe for direct UI display and
must never contain credentials or raw provider payloads.

## DRACO-shaped example

The values below demonstrate the intended shape. The Engine owner must still pin the exact
production routes, prompts, judge identity, and Tool policy before publishing `draco@1`.

```yaml
schema: screamingface.benchmark-manifest.v1
id: draco@1
title: DRACO
description: Research-quality rubric evaluation.

cases:
  route: /benchmarks/draco/1/cases
  schema: screamingface.draco-case-input.v1
  count: 100
  ordering: stable

provenance:
  cases:
    dataset: perplexity-ai/draco
    split: test
    revision: ce076749809027649ebd331bcb70f42bf720d387

answer:
  protocol: single_turn
  instructions: |
    Full pinned DRACO answer instructions go here.
  max_output_tokens: 8192
  tools:
    max_calls: 12
    excluded_domains:
      - huggingface.co/datasets/perplexity-ai/draco
      - openrouter.ai/blog/announcements/fusion-beats-frontier
    web_search:
      max_results: 5
    web_fetch: {}

synthesis:
  instructions: |
    Full pinned DRACO synthesis instructions go here.
  max_output_tokens: 8192

grading:
  route: /benchmarks/draco/1/grade
  protocol: rubric
  judge:
    model: openrouter/google/gemini-3.1-pro-preview
    passes: 5
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
    instructions: |
      Full pinned Appendix C.5 judge instructions go here.

aggregation:
  route: /benchmarks/draco/1/aggregate
  protocol: mean
  primary_metric: normalized_score
  score_direction: maximize
  metrics:
    - normalized_score
    - pass_rate
    - coverage
```

Synthesis instructions are Benchmark-owned only when that Benchmark fixes a default protocol.
The Synthesis model remains part of the researcher's Fusion. Generic ordered member outcomes and
partial-member failure preservation are SF Recipe execution semantics, not fields repeated in
each Benchmark manifest. In particular, Synthesis does not make DRACO a multi-turn answer
protocol.

## Other v1 protocol shapes

These fragments show how the same envelope covers the other existing Benchmark families. Exact
field names remain subject to schema review, but these capabilities are required in v1.

### Native conversation and repeated samples

```yaml
answer:
  protocol: native_chat
  samples: 8
  max_output_tokens: 4096
```

The Case supplies the pinned message history. The Engine obtains the declared number of
independent Candidate answers before grading. This covers the HealthBench execution shape
without embedding its operational runner settings.

### Generated multi-turn answer protocol

```yaml
answer:
  protocol: multi_turn
  turns:
    - instructions: |
        Explain your reasoning.
    - instructions: |
        Return only the final answer.
```

Each turn is an ordered Benchmark-owned operation and may consume earlier turn output according
to the versioned `multi_turn` protocol. This covers the MedXpert execution shape.

### Stateful workflow and sandbox grading

```yaml
answer:
  protocol: workflow
  route: /benchmarks/scicode/1/run-case

grading:
  protocol: sandbox
  route: /benchmarks/scicode/1/grade

aggregation:
  protocol: mean
  route: /benchmarks/scicode/1/aggregate
  primary_metric: score
  score_direction: maximize
```

`workflow` is a typed escape hatch for protocols whose state machine cannot be faithfully
expressed as a short prompt sequence. The referenced route is part of the immutable Benchmark
revision. Its inputs, outputs, operation attribution, and failure behavior are fixed by the
versioned workflow contract; `workflow` is not an untyped implementation-options block.

## Reproducibility

A reproducible submission combines four distinct artifacts:

1. the immutable Benchmark Manifest;
2. the researcher's Candidate definitions;
3. the selected Case scope;
4. the generated Candidate Evaluation URL4s and their execution results.

The Benchmark Manifest defines the protocol. It deliberately does not claim that a Candidate
lineup or one particular run is part of the Benchmark itself.

During URL4 execution, the Engine obtains canonical candidate-visible Case inputs from
`cases.route`; the Client never loads a Hugging Face dataset, database, or local Case file.
Dataset ingestion and storage are Engine registration concerns. `provenance.cases` may identify
the original source for researchers, but it does not select a Client execution adapter or expose
hidden evaluation data.

The Engine must guarantee that a versioned Benchmark route and any workflow it references cannot
change semantics in place. If Cases or behavior change, the Benchmark receives a new revision.
The HTTP `Content-Digest` verifies the exact served YAML without embedding a circular digest
inside the file.

## Strict YAML profile

The Engine and Client use YAML 1.2 safe loading and reject features that make identity or typing
surprising:

- duplicate mapping keys;
- custom tags or executable object constructors;
- anchors, aliases, and merge keys;
- non-string mapping keys;
- non-finite numbers; and
- more than one YAML document in the response.

The parsed value is validated against the versioned Benchmark Manifest schema. Formatting and
comments are part of the canonical file's byte identity, while semantic compatibility is
identified by its immutable Benchmark `id`.

## What belongs in the manifest

- Canonical immutable Benchmark identity.
- Canonical Case count, ordering, candidate-input schema, route, and `id`/`input` contract.
- The grading route through which SF Engine privately resolves rubric, reference-answer, or
  hidden-test data by `case_id`.
- Optional Case-source provenance for research and reproduction.
- The complete Benchmark-owned answer protocol and instructions.
- Permitted Tool operations and policies.
- Benchmark-owned Synthesis defaults.
- Grading method, rubric behavior, Judge identity and settings, or sandbox contract.
- Aggregation method, metrics, primary metric, and score direction.
- Scientific repetitions such as answer samples and Judge passes.
- Typed protocol-specific invalid-output repair when its attempts, prompts, or exhaustion
  behavior affect the meaning of a score.
- Immutable typed workflow references when behavior cannot be expressed declaratively.

## What does not belong in the manifest

- The researcher's Models, Fusions, Reducers, or Candidate lineup.
- The run's Case limit or selected Case IDs.
- Run identity, timestamps, observed results, usage, or Failures.
- Provider credentials, Run capabilities, caller identity, or deployment origin.
- NATS, WebSocket, worker, cache-storage, or AI Gateway implementation details.
- Operational Provider/Tool retries, backoff, concurrency, logging, tracing, queue, and
  infrastructure settings.
- A generic `execution.retry` block that conflates scientific repetitions with infrastructure
  recovery.
- Fusion member-failure behavior, which is a generic Recipe execution invariant.
- Case-source adapters or ingestion instructions that the Client would need to execute.
- Capability-discovery and compatibility-profile data, which have their own versioned Engine
  contract and cache lifecycle.
- A separately editable JSON copy of the same manifest.

The source repository's current Benchmark configuration files may continue to contain internal
runner and deployment configuration. They can generate or validate this public manifest, but
they are not themselves the public reproducibility contract.

## DRACO conformance notes

The active `screamingface-benchmarks` configuration and the historical reference Engine are
useful inputs but are not themselves this public contract:

- the active repository configuration currently declares three judge passes despite comments
  requiring five for paper-aligned runs;
- Gemini 3.1 Pro Preview substitutes for the unavailable exact paper Judge;
- the Tool blocklist and twelve-call limit contain reconstructed values;
- bash is disabled because the current model endpoint cannot provide it.

The Benchmark-specific choices above must be pinned in the canonical manifest identity. A reduced
or substituted protocol needs a distinct revision or Benchmark name and cannot be labelled
paper-exact.

## Owner questions

1. Will the Engine expose one immutable manifest endpoint with a canonical revision URL and
   digest?
2. Which exact versioned schemas define `single_turn`, `native_chat`, `multi_turn`, `workflow`,
   `rubric`, `sandbox`, and the aggregation protocols?
3. What common Case, Candidate outcome, grade, and aggregation contracts let the Client compile
   each typed protocol without Benchmark-specific code?
4. How are immutable workflow routes registered and prevented from changing behavior within a
   Benchmark revision?
5. Which exact DRACO configuration should become the first canonical `draco@1`: repository
   reproduction, paper-aligned protocol, or an explicitly named substitute?

No Client manifest decoder or compiler should be implemented until these contracts are confirmed.
