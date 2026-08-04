---
id: OME-746
linear_url: https://linear.app/openmined/issue/OME-746/stop-fabricating-the-codex-finish-reason-derive-it-from-status-and
status: in_progress
type:
priority: P2
labels: [aigateway, autonomous, agentic]
created: 2026-08-04
closed:
---

# OME-746 — derive the Codex finish_reason instead of fabricating "stop"

Sub-issue of `OME-679`, which it blocks: `OME-679` makes a provider refusal distinguishable from
a bad answer via `finish_reason`, and that is worthless if a provider invents the value.

`plugins/codex_provider/chat_handler.py:215` hardcodes `"finish_reason": "stop"` on every
response the plugin builds.

## The finding

The defect is bigger than the hardcoded value. `_consume_sse_event` treats **`response.completed`
as the only terminal event**, but the Responses API also terminates with **`response.incomplete`**
— exactly how a length-truncated or content-filtered answer arrives. Nothing matches it, so
`_model_response_from_state` raises `CustomLLMError(502, "Codex upstream did not complete
response")`.

Today a truncated Codex answer is not mislabeled `stop` — **it is discarded entirely as a 502**,
partial content and all. The `length` acceptance criterion cannot be met without handling
`response.incomplete`, so that handling belongs to this unit.

Verified from the API's own definitions rather than memory: `ResponseIncompleteEvent.type` is
always `response.incomplete` and carries the full `Response` (OpenAI OpenAPI spec);
`IncompleteDetails.reason` is `Literal["max_output_tokens", "content_filter"]` (installed SDK,
`openai/types/responses/response.py`).

## Scope

- `src/aigateway/plugins/codex_provider/chat_handler.py` — terminate on either terminal event;
  state key `completed` → `final`; derive the reason (`max_output_tokens` → `length`,
  `content_filter` → `content_filter`, else `stop`), mirroring the normalizer shape at
  `plugins/gemini_provider/message_adapter.py:103-111`.

## Out of scope

De-duplicating the byte-identical mapper in `gemini_provider/message_adapter.py` and
`antigravity_provider/message_adapter.py` — real DRY debt, separate refactor.

Ledger: `docs/work/2026-08-04-OME-746-codex-finish-reason.md`
