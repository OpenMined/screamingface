---
title: OME-400 — implementation plan: packages/screamingface v0.1 + 00_quickstart
status: approved (owner, 2026-07-13, in-session)
created: 2026-07-13
ticket: OME-400
spec: docs/spec/2026-07-13-screamingface-sdk-quickstart-spec.md
ledger: docs/work/2026-07-13-OME-400-quickstart-sdk.md
---

# Plan — screamingface SDK v0.1 quickstart slice

Branch `OME-400-quickstart-sdk` off `origin/main`. One SDLC unit (sdlc-python loop);
commits land in reviewable slices, each `Refs: OME-400`.

## Owner decisions (recorded)

1. **Simulated backend now** — port the prototype's deterministic `SimulatedBackend`
   behind an `EngineBackend` port; real engine (OME-296) is a later adapter swap.
2. **No `packages/url4` dependency** — url4 v1 is unmerged (PR #389) and the real grammar
   integration is OME-408's scope. The flat `url4://` codec stays isolated in `share.py`.
3. **Name:** dir `packages/screamingface`, import + PyPI `screamingface` (checked free).
   Not `py-screamingface` (that's only the Linear label). A future Node SDK follows the
   url4 precedent (`packages/screamingface-js`, npm `@openmined/screamingface`).
4. **Widgets:** mock/static rendering path only; live ipywidgets are OME-407.

## Steps

1. **Scaffold** `packages/screamingface` mirroring `packages/url4` (pyproject/hatchling,
   uv, ruff, pyright basic, pytest strict-asyncio, src layout) + in-package README.
   Register a `screamingface` stack entry in `.claude/sdlc.local.md` (gates: ruff check,
   ruff format --check, pyright, pytest --cov=screamingface --cov-fail-under=80 -q) —
   the card had no packages/ stack (url4 gap, surfaced).
2. **RED** — failing tests for the spec surface (catalog, Fusion/judge, url shape, reduce
   strategies, evaluate determinism, Run metrics, port conformance, session key safety,
   mock-widget smoke).
3. **GREEN** — port the quickstart slice from
   `screamingface-brand/product-demos/screamingface-contract/src/screamingface/`:
   `backend.py→engine.py` (+ new `EngineBackend` Protocol), `catalog.py`, `models.py`
   (Pool internal; `sf.models` becomes a thin service), `_fusion.py→fusion.py` (drop
   Script hooks; keep the seam), `reduce.py`, `evaluate.py`, `results.py`+`run.py`,
   `datasets.py` (+`_data/gpqa.json`; HF-hub loader retained, offline-first),
   `session.py`, `share.py` (emit only), `widgets.py` (mock path + the `wv` HTML builders
   it needs), facade `__init__.py`. Dropped modules: scripts, loop-scripts, leaderboard,
   stacked fusions, live widgets, html reprs beyond what the notebook shows.
4. **Notebook** — `examples/00_quickstart.ipynb`, the ticket's 5 steps, executed via
   nbconvert with outputs committed; determinism verified by double execution.
5. **CI + repo wiring** — `screamingface-tests.yml` (path-filtered, mirrors
   aigateway-tests.yml), CODEOWNERS entry, dependabot uv ecosystem. Release lane:
   "not released" documented in README (owner registers release-please at name lock).
6. **Gates → wisdom → ledger outcome → PR** — `run_gates.py screamingface` green; PR to
   main; close OME-400 + mirror with the close template. Owner-verify: create + register
   the `pkg/screamingface` landing label (Linear UI / card same-change rule).

## Out of scope (tickets exist)

Leaderboard + submit (OME-402) · widgets live mode (OME-407) · url4 parse/import + real
grammar (OME-408) · telemetry stamps (OME-416) · full series green + 00_overview (OME-403).
