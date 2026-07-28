---
ticket: OME-548
stack: url4-cloud
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-548 — Drop ai.url4.execute from the WebSocket inbound surface

## Intent

`ExecuteEvent` / `ExecuteData` (`ai.url4.execute`) have no consumer anywhere: runs start via
the REST control plane (`GET /?q=…`), never over the WebSocket. Carrying a dead inbound command
bloats the protocol surface, the discriminated unions, the generated OpenAPI/AsyncAPI docs, and
the bridge's inbound type. This unit removes the command entirely so the WS inbound surface is
exactly Stop + Attach — the two commands the bridge actually acts on.

## Planned changes

- `src/url4_streaming_protocol/signals.py` — delete `class ExecuteData`.
- `src/url4_streaming_protocol/unions.py` — delete `class ExecuteEvent`; drop the `ExecuteData`
  import; remove `ExecuteEvent` from `InboundFrame` and `Frame` (leave `OutboundFrame` untouched);
  keep the discriminated-union + `TypeAdapter` structure valid.
- `src/url4_streaming_protocol/__init__.py` — remove `ExecuteData`/`ExecuteEvent` from imports + `__all__`.
- `src/url4_cloud/schemas/protocol_schemas.py` — drop the `ExecuteEvent` import; set
  `INBOUND_EVENTS = (StopEvent, AttachEvent)`; delete the `"ExecuteEvent"` key from `EVENT_TYPE`.
- `src/url4_cloud/schemas/asyncapi.py` — INFO_DESCRIPTION: "sends stop/attach commands" (drop
  `execute/`), now that Execute left the inbound surface (deviation — keeps the served AsyncAPI
  description truthful; same coherent change).
- `src/url4_cloud/ws/bridge.py` — drop `ExecuteEvent` from the import and from `_InboundEvent`
  (→ `AttachEvent | StopEvent`).
- `apps/url4-cloud/docs/protocol.md` §4 — inbound set is Stop + Attach only; note Execute left
  the WS surface (runs start via REST `GET /?q=`).
- `docs/spec/2026-07-21-url4-cloud.md` §6 — same one-line note.
- `tests/unit/test_protocol.py` — NEW RED tests (append-only add).
- `tests/unit/test_docs_ops.py` — AUTHORIZED prior-test edit: drop `ExecuteEvent` from
  `EXPECTED_EVENT_SCHEMAS`; NEW append-only test asserting AsyncAPI `sendCommand` = stop+attach only.

## Test plan

- RED `test_inbound_adapter_rejects_execute` — `InboundFrameAdapter.validate_python` of a
  previously-valid `ai.url4.execute` frame now raises `ValidationError` (unknown discriminator tag).
- RED `test_execute_symbols_removed` — `url4_streaming_protocol` exposes neither `ExecuteEvent`
  nor `ExecuteData` (`not hasattr(...)`).
- RED `test_asyncapi_sendcommand_is_stop_and_attach_only` — the AsyncAPI `send` operation lists
  exactly `StopEvent` + `AttachEvent`, never `ExecuteEvent`.
- Authorized edit: `EXPECTED_EVENT_SCHEMAS` drops `ExecuteEvent` (owner-approved contract change),
  keeping the existing OpenAPI/AsyncAPI component-schema assertions green after removal.

## Acceptance

- `grep` finds no `Execute*` in src/tests/docs (docs/work ledgers excepted).
- AsyncAPI `sendCommand` lists only stop + attach.
- OpenAPI 3.1 + AsyncAPI 3.0 validators pass.
- `run_gates.py url4-cloud` green (ruff, format, pyright, pytest cov ≥ 80).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** exactly as planned. Source: `url4_streaming_protocol/{signals,unions,__init__}.py`,
  `url4_cloud/schemas/{protocol_schemas,asyncapi}.py`, `url4_cloud/ws/bridge.py`. Docs:
  `apps/url4-cloud/docs/protocol.md` §4, `docs/spec/2026-07-21-url4-cloud.md` §6. Tests:
  `tests/unit/test_protocol.py` (+2 RED tests, purely additive), `tests/unit/test_docs_ops.py`
  (authorized `EXPECTED_EVENT_SCHEMAS` edit + 1 additive test). No DB/ORM schema → no migration (S1 n/a).
- **Commits:** refactor(url4-cloud): drop ai.url4.execute from the WS inbound surface (Refs: OME-548)
- **Gates:** `run_gates.py url4-cloud` — ruff ✓, ruff format ✓, pyright ✓, pytest cov 97% (≥80) ✓;
  115 passed. Re-run with `--skip-append-only`: the append-only check flagged the two modified test
  files — `test_docs_ops.py` (the owner-approved contract edit named in the brief: drop `ExecuteEvent`
  from `EXPECTED_EVENT_SCHEMAS`) and `test_protocol.py` (pure additions — no prior assertion changed).
  Neither is a gate weakening. Validators: OpenAPI 3.1 → `OPENAPI OK`; AsyncAPI 3.0 (`@asyncapi/cli`)
  → valid, 0 errors (1 info: newer 3.1.0 available) = PASS; AsyncAPI `sendCommand` = `[StopEvent, AttachEvent]`.
- **Deviations:** one beyond the brief's explicit file list — `url4_cloud/schemas/asyncapi.py`
  INFO_DESCRIPTION changed "sends execute/stop/attach commands" → "sends stop/attach commands" so the
  served AsyncAPI description stays truthful after Execute left the surface (same coherent change, not
  scope creep). `InboundFrame`/`Frame` remain valid 2+-member discriminated unions; `OutboundFrame`
  untouched. The bridge's malformed-frame path now absorbs any stray `ai.url4.execute` as an ignored
  unknown frame (existing test still green).
