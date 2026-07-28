---
ticket: OME-518
stack: url4-cloud
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-518 — REST control plane (GET /?q= sync/async, DELETE, POST /token wiring)

## Intent
The stateless App's HTTP surface (spec §5; docs/protocol.md §7): mint a capability token, start a
run (`GET /?q=<url4>`) with RFC 7240 `Prefer`-selected sync/async and a `SYNC_MAX_WAIT` degrade,
and stop+purge (`DELETE`). Sync outcome maps `TerminatedEvent.data.status` → HTTP. Every error is
an RFC 9457 `application/problem+json`. Deps (bus, job_runner, clock, subscriber-gate) are
injected so the control plane runs headless with in-memory fakes.

## Planned changes
- `src/url4_cloud/rest/__init__.py` — package exports (router, gate).
- `src/url4_cloud/rest/interest.py` — `SubscriberGate` port + `DenyAllGate` default (the NATS
  interest seam for the `428` guard, spec §4; the real gate wires with the WS unit OME-521).
- `src/url4_cloud/rest/routes.py` — `POST /token`, `GET /`, `DELETE /`.
- `src/url4_cloud/app.py` — additive: install RFC 9457 handlers, inject deps, `include_router`.
- `tests/unit/test_rest.py` — behaviour tests (new file, append-only).

## Test plan (RED first)
- `POST /token` returns a verifiable token; `GET` 401 (bad/absent bearer); 428 (no subscriber,
  default DenyAllGate); 409 (job exists) and 409 (schedule raises JobAlreadyExists); async
  `202` + `Location` + `Preference-Applied` headers; sync `200` + Result body; sync `502` (failed);
  degrade `202` past `SYNC_MAX_WAIT`; `DELETE` `204` (stop+purge) and `403` (topic≠sub); missing
  `q` → `400`. Error bodies assert `application/problem+json`.

## Acceptance
- Gates green (ruff · format · pyright · pytest+cov ≥ 80); every branch of the §5 outcome table
  exercised; errors are problem+json; no live NATS/k8s (InMemoryBus + fake JobRunner via DI).

## Outcome
- **Actual files:** as planned — `rest/{__init__,interest,routes}.py`, `app.py` (additive: inject
  deps + install RFC 9457 handlers + `include_router`), `tests/unit/test_rest.py` (20 tests).
- **Commits:** see the OME-518 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud` ALL GREEN (ruff · format · pyright · pytest+cov — new REST
  modules at 100%, project TOTAL 96%, threshold 80%).
- **Deviations:** the `428` "active NATS subscriber" precondition is modeled as its own injectable
  `SubscriberGate` port (`rest/interest.py`) rather than a method on `Bus` — interface segregation
  (interest is not the pub/sub transport's job); the real gate wires with the WS bridge (OME-521),
  and `create_app` defaults it to a conservative `DenyAllGate` (start is `428` until wired). `DELETE`
  additionally rejects a `topic` query param that does not match the token's `sub` (`403`) so a
  capability can only stop its own run.
