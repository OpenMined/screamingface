---
ticket: OME-746
stack: aigateway
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-746 — derive the Codex finish_reason instead of fabricating "stop"

## Intent

Sub-issue of `OME-679`. `OME-679` wants a provider **refusal** to be distinguishable from a **bad
answer**, and the mechanism is `finish_reason`. That is worthless if a provider *invents* the
value, which is what the Codex plugin does today:
`plugins/codex_provider/chat_handler.py:215` hardcodes `"finish_reason": "stop"` on every
response it builds.

## The finding — the defect is bigger than the hardcoded value

Investigating the fix surfaced a second, worse bug underneath it.

`_consume_sse_event` (`chat_handler.py:148-167`) treats **`response.completed` as the only
terminal event**. The OpenAI Responses API also terminates a stream with **`response.incomplete`**
— that is exactly how a length-truncated or content-filtered answer arrives. Because nothing
matches it, `state["completed"]` is never set, the loop drains the stream, and
`_model_response_from_state` raises `CustomLLMError(502, "Codex upstream did not complete
response")`.

So today a truncated Codex answer is not merely mislabeled `stop` — **it is discarded entirely as
a 502, partial content and all.** The `length` acceptance criterion on this issue cannot be met
without handling `response.incomplete` first, so that handling is part of this unit rather than
scope creep.

**Verified, not assumed** (both from the API's own definitions, not memory):

- `ResponseIncompleteEvent` — `type` is always `response.incomplete`, carries the full `Response`
  (OpenAI OpenAPI spec).
- `Response.status` — `completed | failed | in_progress | cancelled | queued | incomplete`
  (same spec).
- `IncompleteDetails.reason` — `Literal["max_output_tokens", "content_filter"]`, read from the
  installed SDK at `openai/types/responses/response.py`.

## Design

- Terminate on **either** terminal event, storing the `Response` under one state key (`final`)
  rather than `completed` — the old name would be a lie for an incomplete response. No test
  couples to the state dict, so the rename is free.
- Derive the reason from the `Response` itself:
  `incomplete_details.reason == "max_output_tokens"` → `length`;
  `== "content_filter"` → `content_filter`; otherwise → `stop`.
  Mirrors the shape of the existing normalizer at
  `plugins/gemini_provider/message_adapter.py:103-111`.
- `response.failed` / `error` keep raising — unchanged.

## Planned changes

- `src/aigateway/plugins/codex_provider/chat_handler.py` — `_consume_sse_event` also terminates
  on `response.incomplete`; state key `completed` → `final`; new `_finish_reason(response)`;
  `_model_response_from_state` uses it instead of the literal `"stop"`.
- `tests/unit/codex/test_chat_handler.py` — **append only**, no prior test touched.

No schema/model change, so S1 (migrations) does not apply. No credential/secret surface touched,
so the aigateway card INVARIANTS (ORMStore-only credentials, no keychain, no litellm-enterprise)
are unaffected.

## Test plan

Failing tests first:

- **The silently-wrong case** — a `response.incomplete` stream with
  `incomplete_details.reason = "max_output_tokens"` yields `finish_reason == "length"` **and
  preserves the partial content** (today: a 502, content lost).
- **Refusal** — `reason = "content_filter"` yields `finish_reason == "content_filter"`, the value
  `OME-679` keys refusal detection on.
- **Regression guard** — a normal `response.completed` still yields `stop` (the behavior every
  existing test asserts).
- **Boundary** — `status: "incomplete"` with `incomplete_details` absent/`null` falls back to
  `stop` rather than raising.
- **Error path unchanged** — `response.failed` still raises `CustomLLMError`, and a stream with
  no terminal event at all still raises "did not complete response".

## Acceptance

- `incomplete_details.reason = "max_output_tokens"` surfaces as `length`, with content intact.
- A normal completion still surfaces `stop`.
- No prior test modified.
- Gates green: `uv run .claude/scripts/run_gates.py aigateway`.

## Outcome

- **Merged:** `29487f20` squash-merged as `0571f440` (#501), remote CI **6/6 pass**.
- **Actual files:**

  | File | Planned? | What |
  |---|---|---|
  | `src/aigateway/plugins/codex_provider/chat_handler.py` | yes | `_TERMINAL_EVENTS`, `_INCOMPLETE_REASONS`, `_finish_reason()`; state key `completed` → `final`; the literal `"stop"` replaced |
  | `tests/unit/codex/test_finish_reason.py` | **new file, not an append** | 7 tests — see Deviations |
  | `tests/unit/codex/test_chat_handler.py` | planned as the test home | **not touched** — reverted, see Deviations |

- **Gates:** `run_gates.py aigateway` — **ALL GATES GREEN**. append-only check ✓ · ruff check ✓ ·
  ruff format --check ✓ · pyright ✓ (no `# type: ignore` added) · `check_no_enterprise.py` ✓ ·
  `pytest --cov=aigateway --cov-fail-under=80` ✓. Full suite **2652 passed, 40 skipped**; the new
  module is **7 passed**.
- **Completeness check:** `grep '"finish_reason"'` across `codex_provider/` now returns exactly
  one site, and it is the derived call — every response path (`_model_response_from_sse_events`,
  `_model_response_from_sse_stream`) funnels through `_model_response_from_state`, so there is no
  second place still fabricating a value.

- **Deviations:**
  1. **The unit is larger than filed, and had to be.** The issue described a hardcoded
     `finish_reason`. The real defect underneath it: `_consume_sse_event` treated
     `response.completed` as the *only* terminal event, so a `response.incomplete` stream — how a
     truncated or filtered answer actually arrives — set no state and raised
     `CustomLLMError(502, "Codex upstream did not complete response")`. **A truncated Codex
     answer was being discarded outright, not mislabeled.** The filed acceptance criterion
     ("`max_output_tokens` surfaces as `length`") is unreachable without fixing that, so it is
     part of this unit rather than scope creep. The RED run confirmed the diagnosis: the new
     test failed on that exact 502, not on a wrong `finish_reason`. Issue description updated.
  2. **Tests landed in a new module instead of appended to `test_chat_handler.py`.** The append
     was genuinely additive — `git diff --numstat` showed **86 insertions, 0 deletions**, no
     prior test altered — but the append-only gate compares *file status*, so it read the growth
     as a modified prior test. The line-level fix is already in flight as `OME-369` / PR #383.
     Rather than weaken the gate or argue with it, the tests moved to
     `tests/unit/codex/test_finish_reason.py`, which is unambiguously append-only. The module
     docstring records why, so the split does not read as arbitrary.
  3. **API shape verified, not recalled.** `ResponseIncompleteEvent` (`type` always
     `response.incomplete`, carries the full `Response`) and the `Response.status` enum come from
     the OpenAI OpenAPI spec; `IncompleteDetails.reason =
     Literal["max_output_tokens", "content_filter"]` was read from the installed SDK at
     `openai/types/responses/response.py`. An unrecognized reason degrades to `stop` so a future
     upstream enum value cannot leak into the closed chat-completions vocabulary.
  4. **Out of scope, unchanged:** the byte-identical mapper duplicated in
     `gemini_provider/message_adapter.py` and `antigravity_provider/message_adapter.py`. Real DRY
     debt; a separate refactor with its own blast radius.
