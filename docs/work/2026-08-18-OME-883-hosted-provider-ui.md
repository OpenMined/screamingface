---
ticket: OME-883
stack: screamingface
status: done
started: 2026-08-18
finished: 2026-08-18
---

# OME-883 — Hosted provider connection-panel behaviour

## Intent

Make `sf.connect()` reflect the tester-release credential policy: local Engines expose BYOK,
while hosted Engines show every advertised provider as managed by ScreamingFace without
credential mutation controls.

## Planned changes

- `src/screamingface/_ui/connection_view.py` — hosted status presentation and control suppression.
- `tests/test_connection_panel.py` — local/hosted static and interactive regression coverage.
- `docs/{tasks,spec,plan,work}/` — required OME-883 artifacts.

## Test plan

- Hosted provider, regardless of caller-scoped BYOK status: “Connected” and “Available via
  ScreamingFace”; no provider button.
- Local loopback provider: existing Connect/Disconnect controls remain.
- Static HTML uses the same hosted labels.

## Acceptance

- Hosted notebook users cannot initiate or remove BYOK connections from the panel.
- Local notebook users retain the current connection flow.
- ScreamingFace gates are green.

## Outcome

- **Actual files:** connection panel state/controller/view, focused panel tests, and the required
  OME-883 task/spec/plan/work artifacts.
- **Commits:** this implementation commit — disable hosted provider credential controls.
- **Gates:** `run_gates.py screamingface --skip-append-only` — all gates green; focused connection
  panel suite — 22 passed.
- **Deviations:** the live hosted check showed that connection status is caller-scoped BYOK state,
  so hosted catalogue rows all render as managed availability instead of exposing that status.
  The append-only override covers two intentional inherited assertion changes and must be
  disclosed in the PR description.
