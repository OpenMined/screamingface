---
ticket: OME-499
stack: url4
status: in_progress
started: 2026-07-20
finished:
---

# OME-499 — reorganize src/url4 into core/io/dag/peer/cli subpackages

## Intent

`packages/url4/src/url4/` is 24 flat modules with no internal package
boundaries — the SDK's own layering (language core, I/O adapters, DAG engine,
client/server, CLI) is invisible on disk. Reorganize into subpackages whose
boundaries match the real import graph (verified via CodeGraph), so a reader
can see the hexagonal shape (core defines the language + IOLayer port; io/,
dag/, peer/, cli/ are adapters on top) without reading every file. Pure
internal reorg — no public API or behavior change.

## Planned changes

- `core/`: errors.py, nodes.py, _scan.py, _annotations.py, grammar.py,
  parser.py, render.py, builders.py, context.py, ensemble.py, subrequest.py
  (moved, unrenamed)
- `io/`: io_layer.py → io/layer.py, io_http.py → io/http.py,
  io_static.py → io/static.py
- `dag/`: unchanged (node.py, nodes.py, compiler.py, executor.py, __init__.py)
- `peer/`: client.py → peer/client.py, server.py → peer/server.py
- `cli/`: cli.py → cli/app.py, _serve.py → cli/_serve.py
- `__init__.py`: re-export paths updated, public surface unchanged
- `pyproject.toml`: `[project.scripts] url4 = "url4.cli.app:main"`
- All intra-package `from url4.X import ...` updated across src/, plus ~161
  deep-import references across ~24 test files and examples/utils.py

## Test plan

- No new behavior — existing test suite is the spec. Every test file's
  imports updated to the new paths; the suite must pass with the same test
  count as pre-reorg (no tests silently dropped by a broken import).
- `tests/unit/test_import_isolation.py` specifically re-verified: import
  boundaries (no eager httpx/uvicorn import) must survive the move.

## Acceptance

- `uv run pytest` green, same test count as `main`.
- `uv run ruff check` / `uv run ruff format --check` / `uv run pyright` clean.
- `uv run url4 --version` and `uv run url4 eval '"x"'` work (console-script
  entry point moved to `url4.cli.app:main`).
- `import url4` public surface (`Client`, `Url4Node`, `run`, `StaticIOLayer`,
  etc.) unchanged — no consumer-visible break.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** matches planned mapping exactly — 18 files moved via
  `git mv` (core/: 11, io/: 3, peer/: 2, cli/: 2), `dag/` untouched, plus
  `__init__.py` and `pyproject.toml` edited in place. 32 test files' imports
  updated (spec estimated ~24 — actual grep-confirmed count was 32; no test
  logic changed, import-lines only, confirmed by `design-reviewer`).
- **Commits:** none yet — awaiting explicit instruction to commit.
- **Gates:** `uv run ruff check` clean · `uv run ruff format --check` 67
  files formatted · `uv run pyright` 0 errors/0 warnings ·
  `uv run pytest -q` 812 passed (baseline 812 collected pre-reorg, unchanged)
  · `uv run url4 --version` / `uv run url4 eval '"ok"'` both work via the new
  `url4.cli.app:main` entry point. Independently re-verified (not just the
  mover's self-report), then `design-reviewer` ran an independent fidelity
  check against the spec/plan: **ACCEPT, no findings**.
- **Deviations:** none from the spec/plan. (Minor: test-file count was 32,
  not the ~24 estimated in the plan/spec — an estimation gap, not a scope
  deviation; every touched file was import-lines only.)
