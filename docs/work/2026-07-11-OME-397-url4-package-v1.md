---
ticket: OME-397
stack: pkg/url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-11
finished: 2026-07-11
---

# OME-397 — Package & commit url4 SDK v1 under SDLC

## Intent

Land the url4 SDK v1 into the monorepo at `packages/url4` as one fresh, SDLC-tracked unit of
work. url4 is a standalone, framework-free core library for the url4 expression protocol:
`(sources)!intent` compiles into an executable DAG of typed nodes (`url4.dag`); independent
nodes run in parallel and all I/O is inverted behind an `IOLayer` port. The library already
exists (developed earlier as a local commit on the divergent `main`); this unit **packages
and commits** the current working state onto a clean branch off up-to-date `main` so it
enters history under the AI SDLC process. **No re-development or rewrite of the code.**

## Planned changes

- Sync the current `packages/url4/` working state from the main checkout into the worktree
  (rsync, excluding `.venv`/`.ruff_cache`/`.pytest_cache`/`.coverage`/`__pycache__`/`.claude`).
- Track set = the 32-file prior base **plus** the new files: `src/url4/_annotations.py`,
  `tests/spec/` (11 files), `tests/test_scan.py` → 44 files total.
- Docs artifacts for this unit: `docs/spec/2026-07-11-url4-package-v1-spec.md`,
  `docs/plan/2026-07-11-url4-package-v1.md`, this ledger, and the
  `docs/tasks/2026-07-11-url4-package-v1.md` mirror.

## Test plan

- Packaging unit (no new production code, no TDD RED/GREEN): the acceptance is that url4's
  **own** existing test suite passes under its own toolchain, proving the packaged state is
  coherent and self-contained.
- Gates run from `packages/url4`: `uv run ruff check`, `uv run ruff format --check`,
  `uv run pyright`, `uv run pytest -q`.

## Acceptance

- Tracked set matches prior base + the three new source/test additions; no
  caches/venv/coverage/tooling junk tracked.
- url4 gates green (ruff, pyright, pytest) before commit.
- Conventional commit(s) with `Refs: OME-397`; nothing pushed; `main` history untouched.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — 44 files under `packages/url4/` (32-file prior base + the 12
  new source/test files: `src/url4/_annotations.py`, `tests/spec/` (10 files),
  `tests/test_scan.py`), plus 4 docs artifacts (this ledger, the task mirror, spec, plan).
  No caches/venv/coverage/`.claude` tracked. rsync excludes did the filtering; `git add`
  (gitignore-respected) staged exactly 44 package files — verified against the anchor
  `git ls-tree -r b1277c4 -- packages/url4` + the three known additions.
- **Commits:** `ffc1c95` — `feat(url4): package v1 SDK` (code + docs); a small docs
  follow-up records this sha in the ledger.
- **Gates:** ruff check → All checks passed; ruff format --check → 41 files already formatted;
  pyright → 0 errors, 0 warnings; pytest → **385 passed** in ~0.5s. (`uv sync` from the
  committed `uv.lock` first; lock unchanged afterward.)
- **Deviations:** (1) Linear transport — filed via the `linear-cli` skill (vault-resolved
  API key) per the launching task's explicit instruction, since the card's MCP transport was
  not available in this environment. (2) No RED/GREEN TDD cycle: this is a packaging unit of
  pre-existing, already-tested code (no new production code authored); acceptance is that the
  package's own suite passes. (3) The new-component coordination contract (CI workflow,
  CODEOWNERS, dependabot, release lane, `sdlc.local.md` stack entry) is intentionally out of
  scope — follow-up. (4) `main` history untouched; nothing pushed.

## Follow-up work (same branch, post-package)

- **Spec upgraded to a real technical spec.** `docs/spec/2026-07-11-url4-package-v1-spec.md`
  was rewritten from a packaging note into a full as-built technical specification of the url4
  core (language grammar, parse→compile→execute pipeline, expression-problem flip, lowering &
  reference-edge model, dataflow executor + concurrency/admission control, execution/iteration
  semantics, hexagonal IOLayer ports/adapters, sub-request codec, variable/reference model,
  error model, extensibility, trade-offs). Commit `24d9128`.
- **Architecture diagrams added** under `docs/diagrams/` (SVG + PNG), referenced from the spec:
  `url4-pipeline`, `url4-hexagonal-ports-adapters`, `url4-dag-execution-model`. Hand-authored
  via a scratchpad generator (no diagramming plugin installed); rendered with `rsvg-convert`;
  visually verified for legibility and no overlaps. Committed with the spec diagram references.
- No docs gate exists for markdown/SVG (the repo's gates are the Python stack gates); these are
  docs artifacts verified by review + visual render, not TDD. The url4 code was untouched, so
  its gates remain green from the package commit.
