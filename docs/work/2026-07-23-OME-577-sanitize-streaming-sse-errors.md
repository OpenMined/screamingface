---
ticket: OME-577
stack: aigateway
status: done
started: 2026-07-23
finished: 2026-07-23
---

# OME-577 - Sanitize provider errors in streaming SSE responses

## Intent

Make the streaming chat failure boundary match the non-streaming security contract: clients receive only stable gateway-authored error data, while raw provider messages and exception class names remain server-side.

## Planned changes

- Modify `apps/aigateway/src/aigateway/routes/chat_dispatch.py` to emit a fixed streaming error code and message.
- Add `apps/aigateway/tests/unit/test_chat_streaming_errors.py` with focused SSE disclosure regressions.
- Update this ledger with actual files, verification, and deviations before commit.

## Test plan

- Add a failing test where a stream emits one valid chunk and then raises an exception containing sentinel secret/provider text.
- Assert the successful frame remains unchanged, the terminal error frame has only the stable gateway code/message, no raw text or exception class escapes, and `[DONE]` is not emitted after failure.
- Cover failures representing authentication and generic provider exceptions.
- Run the focused streaming tests and the complete AIGateway quality gates.

## Acceptance

- Streaming error frames contain only gateway-authored `provider_error` code/message fields.
- Raw provider text, exception messages, exception class names, credentials, and sentinel secrets never appear in SSE output.
- Detailed exception context remains in server-side logging.
- Existing successful streaming and non-streaming behavior remains unchanged.

## Outcome (fill at the end - required before COMMIT)

- **Actual files:** `apps/aigateway/src/aigateway/routes/chat_dispatch.py`, `apps/aigateway/tests/unit/test_chat_streaming_errors.py`, and this ledger.
- **Commits:** `fix(aigateway): sanitize streaming provider errors` (this commit).
- **Verification:** focused streaming tests `4 passed`; related route/provider tests `60 passed`; existing non-streaming sanitization tests `21 passed`; all required AIGateway quality gates passed, including append-only checks, lint, formatting, type checking, enterprise-import protection, full tests, and coverage.
- **Deviations:** review found that server-side logs still included provider-controlled exception text after client SSE sanitization. The final implementation sanitizes both SSE output and server logs, preserves safe type/plugin context, and covers formatted-traceback and hostile exception-string behavior. No product-scope deviation remains.
