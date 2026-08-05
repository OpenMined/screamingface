---
id: OME-745
linear_url: https://linear.app/openmined/issue/OME-745/capture-finish-reason-and-the-provider-refusal-field-and-classify-a
status: done
type:
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-08-04
closed: 2026-08-05
---

# OME-745 — capture finish_reason / refusal and classify a refused turn

Sub-issue of `OME-679`, and the hop where the signal is actually lost today.

`_parse_choice` in `apps/url4-cloud/src/url4_cloud/runner/connector.py` pulled only `content` and
`tool_calls` out of `data["choices"][0]["message"]`. `finish_reason` was never read — aigateway
produces it and this hop discarded it, so **the finish reason died at the url4 boundary**. The
provider `refusal` field was read nowhere in the repo at all.

A hard refusal (`content_filter`, or empty content carrying a `refusal` string) collapsed into
the generic `aigateway_bad_response` error — indistinguishable from a malformed payload, which is
exactly the conflation `OME-679` exists to remove.

Builds on `OME-744` (merged as `b787cf5d`), which added the `ModelResponse` event and
`current_response_sink()`.

## Scope

Three seams, because that is how far the signal has to travel:

1. `runner/connector.py` — read `finish_reason` + `message.refusal`; report on **every** round
   trip; a refused turn raises `ResolutionError(code="provider_refusal", permanent=True)`.
2. `runner/executor.py` — `_RunState` folds those events onto the owning span, accumulating.
3. `packages/url4/.../protocol/signals.py` — `SpanData` carries them on the wire,
   `finish_reasons` under the OTel `gen_ai.response.finish_reasons` name.

## Out of scope

Splitting `connector.py` (648 lines, over the 450 guidance — the Tavily tool-loop cluster is the
natural extraction), and the SDK-side refusal failure kind, which waits on the `packages/screamingface`
drafts landing.

Ledger: `docs/work/2026-08-04-OME-745-url4-cloud-finish-reason.md`
