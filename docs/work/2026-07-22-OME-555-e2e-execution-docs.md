---
ticket: OME-555
stack: url4-cloud
status: in_progress
started: 2026-07-22
finished: 2026-07-22
---

# OME-555 — e2e execution docs: sync / async / streaming (diagrams + Scalar-exercisable)

## Intent

Give developers the end-to-end execution picture for the three modes (sync / async / streaming),
**and make sync vs async actually exercisable in `/scalar`**. Two parts:

1. **Diagrams** — produced with the **`/diagramming:architecture-diagram` skill** (SVG + PNG in
   `docs/diagrams/`, verified SVG→PNG per repo convention), covering the sync / async / streaming
   flows across Client → App (REST+WS) → NATS/JetStream → Runner Job. Referenced from the served
   docs. (NOT ad-hoc Mermaid — owner corrected this; the diagramming skill is the tool.)
2. **Prefer header** — declare `Prefer` (and its `wait`) as a documented OpenAPI **header
   parameter** on `GET /`, so Scalar renders an input and a developer can drive sync vs async
   (today `routes.py` reads it via `request.headers.get("Prefer")`, so it never reaches OpenAPI and
   Scalar shows no way to select the mode — the gap the owner flagged).

The three flows (from the code):
- **sync** — `GET /` holds to the terminal frame (bounded by `SYNC_MAX_WAIT`), returns the Result
  body; WS carries live telemetry (`rest/routes.py::_run_sync`).
- **async** — `Prefer: respond-async` → `202` + `Location`/`Link`; Result/Terminated arrive on the
  WS stream (JetStream-buffered, resumable).
- **streaming/resume** — WS attach (`?ticket=`) + `sequence` + `ai.url4.attach{from_sequence}`
  replay + `ai.url4.stop` cancel (`ws/endpoint.py`, `ws/bridge.py`).

## Planned changes

- `src/url4_cloud/rest/routes.py` — declare `Prefer` as a typed `Header()` parameter on `GET /`
  (documented, optional) and parse from it, so the sync/async control is visible + tryable in
  Scalar. Keep behaviour identical.
- Diagrams via the diagramming skill → `docs/diagrams/url4-cloud-execution-*.svg|png`.
- Reference the diagrams from the served docs (`docs/protocol.md` and/or the OpenAPI description).
- `tests/unit/test_*` — assert the `Prefer` header parameter is documented on `GET /`.

## Test plan

- **RED:** a test asserting `GET /` documents a `Prefer` header parameter — fails today.
- **GREEN:** declare the `Header()` param → passes; existing sync/async behaviour tests stay green.
- **Browser acceptance:** `/scalar` shows the `Prefer` input on `GET /`; the diagrams render/are
  linked.

## Acceptance

Sync vs async is selectable/visible in `/scalar` (Prefer header documented); the execution diagrams
exist (diagramming skill, SVG+PNG) and are reachable from the docs; `run_gates.py url4-cloud` green.

## Deviations (running)

- Initially drafted Mermaid-in-OpenAPI-description; **reverted** — owner asked for the
  `/diagramming:architecture-diagram` skill. Header name stays `URL4-Capability` (owner-confirmed).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** see the OME-555 commit on `OME-513-url4-cloud`.
- **Gates:** <run_gates result>
- **Deviations:** <none | list>
