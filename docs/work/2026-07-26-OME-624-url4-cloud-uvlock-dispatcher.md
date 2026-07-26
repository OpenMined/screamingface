---
ticket: OME-624
stack: url4-cloud
status: in_progress
started: 2026-07-26
finished:
---

# OME-624 — regenerate url4-cloud uv.lock after the dispatcher → backend rename

## Intent

`apps/url4-cloud/uv.lock` still pins the workspace member to `dispatcher`, a directory that no
longer exists. Commit `87dec815` (this branch) renamed `dispatcher/` → `backend/` and updated
`pyproject.toml` (`url4-cloud = { path = "backend", editable = true }`) but never regenerated the
lockfile, so the two disagree. A cold `uv sync --frozen` — the reproducible-install path used by
CI and container builds — fails outright.

## Planned changes

- `apps/url4-cloud/uv.lock` — regenerate; the corrected diff is exactly two `dispatcher` →
  `backend` entries (`source = { editable = ... }` and the `requires-dist` entry).

No source, no config, no chart changes.

## Test plan

- BEFORE: `uv sync --frozen` fails with `Distribution not found at: .../apps/url4-cloud/dispatcher`.
- AFTER: `uv sync --frozen` resolves cleanly.
- The url4-cloud suite stays green (lockfile-only change, no dependency version moves — verify the
  diff contains no version churn beyond the two path entries).

## Acceptance

`uv sync --frozen` succeeds from a cold checkout; the lockfile references only `backend`; the test
suite is unchanged and green.

## Outcome

- **Actual files:** `apps/url4-cloud/uv.lock` — exactly the two planned `dispatcher` -> `backend`
  entries, no version churn (`git diff --stat` = 2 insertions / 2 deletions). Plus this ledger.
- **Commits:** see the OME-624 commit on `OME-587-url4-cloud-engine-integration`.
- **Gates:** BEFORE — `uv sync --frozen` failed with `Distribution not found at:
  .../apps/url4-cloud/dispatcher`. AFTER — `uv sync --frozen` resolves cleanly. Suite green:
  **276 passed, 3 skipped**, matching the pre-change baseline exactly.
- **Deviations:** none to the change itself. Note for future runs: `uv run pytest` in this tree
  resolved a DIFFERENT pytest (9.0.2) than the project venv holds (9.1.1) and failed collection
  with spurious `ModuleNotFoundError`; `.venv/bin/python -m pytest` is the reliable invocation.
  That is a local tooling quirk, unrelated to the lockfile.
