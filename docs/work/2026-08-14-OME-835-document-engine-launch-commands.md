---
ticket: OME-835
stack: py-screamingface
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-835 — Document engine launch commands

## Intent

Document the packaged ScreamingFace runtime path so users launch their own Engine from the
published client instead of following source-tree `just` or `uv` commands.

## Planned changes

- `public-docs/src/pages/sf-client/InstallationPage.vue` — install, prepare, lifecycle, and
  Tavily guidance for a self-run Engine.
- `public-docs/src/pages/learn/EnginePage.vue` — the same launch commands from the Engine
  overview.
- `packages/screamingface/examples/*.ipynb` — generated notebook copy updated from `just
  stack-*` to the public `screamingface` CLI.
- `packages/screamingface/examples/10_try_it_hosted.ipynb` and report artifacts — include the
  current hosted example artifacts requested for the PR.

## Test plan

- Public docs type-check verifies the edited Vue pages still compile.
- Notebook changes are markdown-only launch instructions and generated example artifacts.

## Acceptance

- Public docs show `pip install "screamingface[runtime,notebook]"`.
- Public docs show `screamingface prepare draco`, `up`, `status`, and `down`.
- Public docs explain when a self-run Engine needs `TAVILY_API_KEY`.
- Notebooks no longer point users at `just stack-*` for the local Engine flow.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus the task mirror.
- **Commits:** this PR commit.
- **Gates:** `npm run type-check` in `public-docs` passed twice.
- **Deviations:** none.
