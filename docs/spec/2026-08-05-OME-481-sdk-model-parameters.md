---
title: ScreamingFace SDK model capability discovery and preflight
status: approved
created: 2026-08-05
ticket: OME-481
upstream: OME-480
---

# SDK model capability discovery and preflight

## Public API

```python
summary = client.models.list()[0]
summary.supported_parameters

details = client.models.get("openrouter/openai/gpt-5.5")
temperature = details.parameters["temperature"]
temperature.schema.minimum
```

The asynchronous equivalents are `await client.models.list()` and
`await client.models.get(model_id)`. The lazy default surface exposes `sf.models.list()` and
`sf.models.get(model_id)`.

`ModelInfo` is a lightweight model-list row. `ModelDetails` is a distinct profile-specific value;
the SDK never manufactures empty detail fields on a summary. Parameter schemas, gateway policy,
provider evidence, tools, transport, context identity, and freshness are decoded from the Engine's
version-1 document. Model/provider names are data, never SDK branches or hardcoded tables.

## Evaluation preflight

Before the first paid operation, `evaluate()`:

1. validates Benchmark and Candidate structure;
2. confirms every required model is in `models.list()`;
3. retains parameters explicitly supplied by the user on their compiled model-call operations,
   then keeps only operations the selected Benchmark actually links;
4. fetches `models.get()` once per distinct selected model;
5. rejects a missing, disabled, or schema-invalid explicit parameter;
6. starts execution only after every preflight succeeds.

Models with no explicit parameters cause no detail request. The SDK's versioned Candidate defaults
are not user overrides and do not trigger detail lookup; AI Gateway remains authoritative when the
actual request reaches it.

An unused structural component cannot block an Evaluation: for example, a member-only Benchmark
does not fetch or validate the ordinary Fusion synthesizer's parameters. Operation identity—not a
walk over the raw Recipe—defines what the executable Evaluation selected.

## Value boundary

The SDK mirrors the published v1 schema vocabulary: scalar and structural type names, unions,
numeric bounds, enum, typed array items, string pattern, and maximum length. This keeps discovery
complete and future-compatible without introducing a DSL.

Candidate `params` remain JSON scalar values because readable/executable URL4 parameter values do
not currently carry general JSON arrays or objects. Supporting structured Candidate overrides is a
separate URL4 contract decision; this unit neither Base64-encodes them nor changes URL4 grammar.

## Failures

- Malformed list/detail documents fail as permanent `PlanningError(code="invalid_catalogue")`.
- Missing/disabled names fail as permanent
  `PlanningError(code="unsupported_model_parameter")`.
- Values that violate the advertised schema fail as permanent
  `PlanningError(code="invalid_model_parameter")`.
- Engine authentication and availability keep their existing typed errors.
- No preflight failure calls the paid run transport.

## Acceptance

1. Sync, async, and lazy-default discovery expose the same typed values.
2. No GPT/provider-specific table or branch exists.
3. Explicit valid parameters execute; unsupported, disabled, and invalid values fail first.
4. Detail requests are deduplicated by canonical model id.
5. Parameter-free Evaluations perform no detail request.
6. Existing benchmark, report, notebook, authentication, and execution behavior remains green.
