---
ticket: OME-605
stack: url4-cloud + py-screamingface
status: complete
started: 2026-07-31
finished: 2026-07-31
---

# OME-605 — Connect providers from the Python Client

## Intent

Restore the provider-connection notebook experience through the current Client → SF
Engine → AI Gateway architecture so a researcher can authorize any enabled provider
before running a benchmark.

## Planned changes

- Add the Engine connection port, AI Gateway adapter, REST routes, composition wiring,
  and focused tests under `apps/url4-cloud`.
- Add typed sync/async connection operations, lazy module helpers, the previous rich
  widget UI, public exports, and focused tests under `packages/screamingface`.
- Update package quickstart documentation and notebook sources.

## Test plan

- RED Engine tests for disconnected/connected state, create-or-replace, idempotent
  delete, identity forwarding, malformed upstream responses, timeouts, and secret-safe
  errors.
- RED Client tests for sync/async operations, strict response decoding, public lazy
  helpers, capability-driven provider rows, password clearing, and static display.
- Run focused tests followed by each available lint, typecheck, test, and coverage gate.

## Acceptance

- `sf.connect()` displays the full connection widget with the providers and methods
  currently advertised by AI Gateway.
- A submitted key or OAuth authorization is validated and stored by AI Gateway through
  the SF Engine.
- `sf.connections.list/get`, explicit sync/async Clients, and disconnect work.
- No provider secret or AI Gateway-private credential data crosses back to the Client.
- Existing Evaluation behavior remains green.

## Outcome

- **Actual files:** `apps/url4-cloud/src/url4_cloud/connections/`,
  `apps/url4-cloud/src/url4_cloud/rest/connections.py`, Engine composition/OpenAPI/README,
  `packages/screamingface/src/screamingface/connections.py`,
  `packages/screamingface/src/screamingface/_connection_panel.py`, Client/default-client/public
  exports, package README/notebook generator/generated notebooks, and focused tests.
- **Commits:** none requested
- **Gates:** Client `ruff` and `pyright` pass; Client suite 249 passed / 15 skipped; notebook,
  wheel/sdist build, and distribution checks pass. The repository-wide 95% coverage gate remains
  at 92.48% because the wider in-progress branch currently leaves `recipe.py` and `reducers.py`
  largely uncovered; this connection slice's focused tests pass. url4-cloud `ruff`, formatting,
  and `pyright` pass. Its focused connection tests pass (17), while the latest full run has 527
  passing / 5 skipped. Final focused
  connection/public-surface tests: Client/widget 18 passed; Engine 17 passed.
- **Deviations:** No Linear changes by explicit user request; implementation is recorded
  under the active OME-605 Client work item.
