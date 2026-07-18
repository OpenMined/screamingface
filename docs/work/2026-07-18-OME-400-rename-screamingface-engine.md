---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-18
finished: 2026-07-18
---

# OME-400 — Rename the tracked engine application

## Intent

Rename the tracked engine application's previous short name and all tracked product, Python,
Docker, CI, and documentation references to `screamingface-engine`. Keep the older ignored
`.docs/spikes/`
development stack and unrelated untracked DRACO demo untouched.

## Planned changes

- Rename the application directory and Python import package.
- Rename its project, executable, Compose service/project, Docker paths, tests, and coverage name.
- Rename the superseded engine walkthrough filename/builder and every tracked link to it.
- Regenerate the Phase 1 walkthrough and application lockfile.
- Update plans, specifications, tasks, work records, README files, and code comments.

## Test plan

- Confirm no tracked references to the previous application or Python-package name remain.
- Run Ruff, notebook formatting, Pyright, SDK and application coverage tests.
- Validate Compose, build the renamed Docker image, and smoke-test the registry over HTTP.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** renamed the application directory, Python package, executable, Docker/Compose
  identities, architecture notebook and builder; updated all tracked code, CI configuration,
  documentation, plans, specifications, tasks, and notebook links; regenerated notebooks and the
  application lockfile.
- **Commits:** none created; the user owns commit and push.
- **Gates:** Ruff check and format, Pyright, SDK tests (57 passed, 97% coverage), application tests
  (9 passed, 100% coverage), Compose validation, Docker build, and HTTP health/registry smoke test
  all pass.
- **Deviations:** the older ignored `.docs/spikes/` stack and unrelated untracked DRACO demo were
  intentionally left untouched.
