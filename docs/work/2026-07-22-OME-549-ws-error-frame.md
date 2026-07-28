---
ticket: OME-549
stack: url4-cloud
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-549 — Add ai.url4.error outbound nack frame + bridge emission

## Intent

The WS bridge silently drops rejected inbound frames: an unparseable/invalid client frame is
swallowed, and a `Stop` sent to a bridge with no `JobRunner` is a no-op. The client gets no
signal that its command was refused. This unit adds `ai.url4.error` — an **outbound advisory
nack** (`ErrorData{code, message, ref_id}`) — and makes the bridge emit it for the two
rejection paths, while **preserving the single-writer invariant**: the inbound task only
enqueues onto `self._out` (`put_nowait`); the writer task remains the sole `ws.send` caller.

## Planned changes

- `src/url4_streaming_protocol/signals.py` — add `class ErrorData(BaseModel)` (`code: str`,
  `message: str`, `ref_id: str | None = None`).
- `src/url4_streaming_protocol/unions.py` — import `ErrorData`; add `class ErrorEvent(CloudEvent)`
  (`type: Literal["ai.url4.error"]`, `data: ErrorData`); add `ErrorEvent` LAST to both
  `OutboundFrame` and `Frame` (no reorder of existing members).
- `src/url4_streaming_protocol/__init__.py` — export `ErrorData`, `ErrorEvent` (imports + `__all__`).
- `src/url4_cloud/schemas/protocol_schemas.py` — import `ErrorEvent`; append to `OUTBOUND_EVENTS`
  (LAST); add `EVENT_TYPE["ErrorEvent"] = "ai.url4.error"`.
- `src/url4_cloud/ws/bridge.py` — import `ErrorEvent`/`ErrorData`; add `_error(...)` helper
  mirroring `_heartbeat`; `_inbound` enqueues an `invalid_frame` nack when `_parse_inbound`
  returns `None` (connection survives); `_handle` emits an `unsupported` nack (ref_id = Stop's
  id) when `StopEvent` arrives with `job_runner is None`.
- `apps/url4-cloud/docs/protocol.md` — §4 add `ai.url4.error` to the outbound catalog (app-emitted
  nack); §5 add §5.5 documenting `ErrorData`.
- `docs/spec/2026-07-21-url4-cloud.md` §6 — one-line note that the app may emit `ai.url4.error`.
- `tests/unit/test_ws.py` — NEW RED tests (append-only add): unparseable→invalid_frame nack +
  survives; Stop with no runner → unsupported nack with ref_id == Stop id.
- `tests/unit/test_docs_ops.py` — AUTHORIZED prior-test edit: add `ErrorEvent` to
  `EXPECTED_EVENT_SCHEMAS`; NEW append-only test asserting AsyncAPI `receiveTelemetry` lists
  `ErrorEvent`.

## Test plan

- RED `test_ws_unparseable_frame_yields_invalid_frame_nack_and_survives` — sending `"{not json"`
  yields one `ai.url4.error` with `data.code == "invalid_frame"`, `ref_id is None`; a following
  valid `Attach` still resubscribes and replays the seeded `started` frame (socket lived).
- RED `test_ws_stop_without_runner_yields_unsupported_nack` — app built with `job_runner=None`;
  a valid `ai.url4.stop` yields `ai.url4.error` `code == "unsupported"`, `data.ref_id == "stp"`.
- Authorized edit: `EXPECTED_EVENT_SCHEMAS` gains `ErrorEvent` (owner-approved contract change),
  tightening the OpenAPI/AsyncAPI component-schema + channel assertions to require it.
- NEW `test_asyncapi_receive_operation_includes_error` — AsyncAPI `receive` op lists `ErrorEvent`.

## Acceptance

- Both bridge behaviours hold; single-writer invariant preserved (inbound only `put_nowait`).
- AsyncAPI `receiveTelemetry` includes `ErrorEvent`; OpenAPI 3.1 + AsyncAPI 3.0 validators pass.
- `run_gates.py url4-cloud` green (ruff, format, pyright, pytest cov ≥ 80).

## Outcome — DONE (blocked mid-run; reconciliation authorized + finished by the orchestrator)

The BLOCKED analysis below was correct discipline: the runner-agent stopped at the authorized-edit
boundary (sdlc rule 5) rather than touch a prior test not on its list, then died emitting its
result schema (StructuredOutput retry cap) before it could report `committed:false`. The
orchestrator picked up the complete, gate-green tree and finished the unit:

- **Authorized the reconciliation the agent itself recommended:**
  `test_ws_ignores_malformed_inbound_frames` → `test_ws_malformed_inbound_frames_nacked_stream_survives`.
  The owner-approved W1 behaviour (nack instead of silent-drop) supersedes the old
  "malformed → heartbeat-first" contract; the updated test asserts both malformed paths nack
  `invalid_frame` and the stream survives (a heartbeat resumes). Strengthening, not weakening.
- **Added the docs the agent hadn't reached:** protocol.md §4 (error in the outbound catalog) +
  new §5.5 (`ErrorData`); spec §6 nack note.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` GREEN (ruff · format · pyright · pytest
  118 passed · cov 96.95%). `--skip-append-only` covers the two authorized contract edits
  (`test_docs_ops.py` EXPECTED_EVENT_SCHEMAS += ErrorEvent; the malformed-test reconciliation) —
  neither removes/weakens an assertion.
- **Commit:** see the OME-549 commit on `OME-513-url4-cloud`.

### Original agent BLOCKED analysis (retained for the audit trail)

- **Status:** BLOCKED before commit. Implementation is complete and the two new bridge behaviours
  work (117 passed), but the ticket cannot reach green gates without editing a prior test the brief
  did **not** authorize me to touch. Per sdlc rule 5 + the runner prohibition "never edit a prior
  test [unless authorized]", this is a hard STOP — I did not push through and did not commit.

- **The blocking prior test:** `tests/unit/test_ws.py::test_ws_ignores_malformed_inbound_frames`
  (assertion at line 236: `assert ws.receive_json()["type"] == "ai.url4.heartbeat"`). It sends an
  unparseable frame (`"this is not json {{{"`) plus an unknown-type JSON frame and asserts both are
  *silently dropped* — the next frame is a heartbeat. This ticket's core deliverable (RED test 1,
  and the owner-specified `_inbound` code whose nack message is "unparseable **or invalid** inbound
  frame") makes unparseable/invalid frames emit an `ai.url4.error(invalid_frame)` nack instead of
  being dropped. Both the old test and RED test 1 send an unparseable frame *first*, so no
  implementation of the specified behaviour can keep the old assertion (heartbeat-first) green.

- **Why it isn't reconcilable in code:** the brief's exact `_inbound` nacks on `event is None`,
  which `_parse_inbound` returns for *both* JSON-decode errors and unknown-type frames. Distinguishing
  them to preserve the old test would deviate from the owner-specified code, and would still not save
  it (the old test's *first* inbound frame is unparseable text, which RED test 1 mandates must nack).

- **The change it would need (recommended authorization):** update that prior test so it asserts the
  new contract — the first frame after an unparseable/unknown inbound frame is
  `ai.url4.error` with `data.code == "invalid_frame"`, and liveness is still proven by a following
  heartbeat (its "malformed frames are non-fatal; the socket lives" intent is preserved). This is the
  same coherent, owner-approved contract change as the ticket itself; it was simply omitted from the
  brief's authorized-edit list (which named only `tests/unit/test_docs_ops.py`).

- **Work in the tree (uncommitted, ready to finish once authorized):**
  - Source: `url4_streaming_protocol/{signals.py (ErrorData), unions.py (ErrorEvent + both unions),
    __init__.py (exports)}`, `url4_cloud/schemas/protocol_schemas.py` (OUTBOUND_EVENTS + EVENT_TYPE),
    `url4_cloud/ws/bridge.py` (`_error` helper, `_inbound` invalid_frame nack, `_handle` unsupported
    nack). Single-writer invariant preserved — inbound only `put_nowait`s onto `self._out`.
  - Tests: `tests/unit/test_ws.py` (+2 new RED→GREEN bridge tests, additive), `tests/unit/test_docs_ops.py`
    (authorized `EXPECTED_EVENT_SCHEMAS` edit + 1 additive `receiveTelemetry` test).
  - Docs: NOT yet applied (protocol.md §4/§5.5, spec §6) — deferred until the block is resolved.
  - No DB/ORM schema change → no migration (S1 n/a).

- **Gates:** `run_gates.py url4-cloud` would be RED: `uv run pytest` reports
  `1 failed, 117 passed` (the one failure is the blocking prior test above). ruff/format/pyright were
  not run to green as the suite is red; the append-only check would additionally flag the two edited
  test files. Not run to completion because the correct action at a STOP is to halt, not to skip.

- **Commits:** none (blocked before commit).
