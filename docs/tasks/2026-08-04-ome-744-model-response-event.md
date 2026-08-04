---
id: OME-744
linear_url: https://linear.app/openmined/issue/OME-744/add-a-modelresponse-observation-event-so-a-world-adapter-can-report
status: in_progress
type:
priority: P2
labels: [url4-python-sdk, autonomous, agentic]
created: 2026-08-04
closed:
---

# OME-744 — a ModelResponse observation event for finish_reason and refusal

Sub-issue of `OME-679` (finish reason and refusal retrieved in the model response).

`url4.observe` is the engine's observation seam: "a passive, pure-data event stream" carrying
`RunStarted | NodeStarted | NodeFinished | Log | Usage | RunFinished`, plus a contextvar-bound
`UsageSink` so a world adapter with no `ExecutionContext` of its own can still attribute a fact
to the currently-resolving node's span.

There is **no equivalent seam for response metadata**. A url4 endpoint's contract is `-> str`,
so a model call's `finish_reason` and the provider `refusal` field have nowhere to travel and
are discarded at the adapter — which is exactly where `OME-679` says the signal is lost.

## Why a new event, not a field on `Usage`

`Usage` is token accounting, and url4-cloud's executor derives `CostUsageData` from the span's
usage tuple. Widening that tuple would push a non-cost fact into cost accounting and change what
every existing cost consumer sees. `ObservationEvent` is a union and the module docstring frames
the event set as the extension point, so a new member is the sanctioned move.

## Scope

- `src/url4/observe.py` — `ModelResponse(span_id, finish_reason, refusal)`; union + `__all__`;
  `ResponseSink` + `_response_sink` contextvar + `current_response_sink()`.
- `src/url4/dag/node.py` — `ExecutionContext.report_response(*, finish_reason, refusal)`.
- `src/url4/dag/executor.py` — bind `_response_sink` in the same `try/finally` as `_usage_sink`.
- `src/url4/streaming/protocol/signals.py` — `SpanData` gains `finish_reasons` aliased to
  `gen_ai.response.finish_reasons` (OTel semconv) and `refusal`.

## Out of scope

Consuming the event — `OME-745` (`apps/url4-cloud`).

Ledger: `docs/work/2026-08-04-OME-744-model-response-event.md`
