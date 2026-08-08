---
ticket: OME-672
stack: repo
status: in_progress
started: 2026-08-08
finished:
---

# OME-672 — Add installation tutorial

## Intent

Fourth sub-issue of `OME-666`. `InstallationPage.vue` is an 18-line stub reading "Stub page —
replace with real content", while the sidebar has listed it under Get Started since `OME-667`.
A reader arriving from the Overview or from the Learn section's Architecture page finds nothing.

Nothing on the site currently says how to get a working environment: not how to install the
client, not how to reach an engine, not what a self-hosted stack needs.

## Planned changes

- `public-docs/src/pages/sf-client/InstallationPage.vue` — replace the stub
- this ledger and `docs/tasks/2026-08-08-installation-tutorial.md`

## Test plan

`public-docs` has no test suite. Verification is the gates CI runs, plus manual checks:

- `npx oxlint .` · `npx eslint .` — bare, as CI runs them
- `npm run build`
- `npx prettier --check` on the touched files
- Every command on the page run against a real local stack before it is written down
- Light and dark theme, and at 400px with no horizontal page scroll

## Acceptance

- The page covers two paths, in this order: a hosted engine, then running your own
- It uses the Learn section's vocabulary — bundled / self-hosted / hosted
- Every command is one we have actually run
- Python version, the `[notebook]` extra, and the fact that `screamingface` is not yet on PyPI
  are all stated
- The self-hosted path names what actually blocked us: migrations, `AIGW_AUTH_MODE=disabled`,
  `AIGW_OPENROUTER_ENABLED=true`, benchmark asset preparation
- No invented engine address — the placeholder constant is used
- Gates green: lint, build, format on touched files

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
