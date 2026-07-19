---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Implement Phase 2B deterministic majority vote

## Intent

Implement the reviewed deterministic-reducer slice without introducing the Phase 2C SDK compiler
or runtime mocks. ScreamingFace owns the pure reducer behavior; `screamingface-engine` owns the
thin URL4 `Request` adapter and registers it once on the persistent node.

## Changes

- Add private SDK-owned exact-string majority selection with stable input-order tie breaking.
- Register `/reducers/majority-vote` as an in-process URL4 endpoint.
- Require a resolved JSON object containing contiguous `panel_1` through `panel_n` strings.
- Return only the winning plaintext and reject unsupported intent/parameters as permanent
  `malformed_source` errors.
- Cover direct dispatch, literal complete expressions, model-backed complete expressions, atomic
  failures, and the absence of reducer-to-Gateway traffic.
- Add a reproducible no-mock Docker smoke for literal reducer execution and real
  engine-to-Gateway topology.

## Test plan

- Run focused reducer unit and ASGI tests.
- Run SDK and engine lint, formatting, type, test, and coverage gates.
- Validate the lockfile, package build, Compose configuration, and Phase 1 generated fixtures.
- Build and start the real Compose stack, then run `scripts/smoke_phase2b.py`.

## Outcome

- **Actual files:** added the private SDK reducer implementation, persistent engine adapter,
  focused SDK/engine tests, and no-mock Docker smoke script; registered the reducer from the
  application composition root; derived discovery from the registered route constant; made
  Compose host ports overridable; and reconciled the spec, plan, task ledger, READMEs, and generated
  Phase 1 walkthrough.
- **Commits:** none; the user owns commit and push.
- **Gates:** Ruff lint and formatting and Pyright pass; the combined SDK/app suite passes 113 tests
  with 97% SDK coverage; the standalone engine suite passes 47 tests with 98% coverage; lockfile,
  package build, Phase 1 fixtures, Compose configuration, notebook regeneration, and
  `git diff --check` pass.
- **Docker smoke:** an isolated real Compose stack on host ports 14404/19105 evaluated a complete
  literal URL4 reducer expression and returned `A`; a separate model request reached the real AI
  Gateway container and surfaced its expected credential-free response. The isolated stack was
  removed afterward and the pre-existing spike stack was not changed.
- **Deviations:** none within Phase 2B. The successful end-to-end SDK compiler path remains Phase
  2C by design; this slice makes no claim that SDK execution exists yet.
