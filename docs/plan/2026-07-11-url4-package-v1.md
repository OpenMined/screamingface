# url4 SDK v1 — Package & Commit Implementation Plan

**Ticket:** OME-397 · **Spec:** `docs/spec/2026-07-11-url4-package-v1-spec.md`

**Goal:** Land the existing url4 SDK v1 into `packages/url4` as one fresh, SDLC-tracked unit
— package and commit the current working state onto a clean branch off up-to-date `main`,
without re-developing the code and without altering `main` history.

**Architecture:** `packages/url4` is a `packages/`-tier shared library (distribution `url4`),
not an independently deployed app. Framework-free core: `(sources)!intent` → typed-node DAG,
I/O inverted behind the `IOLayer` port. This unit adds no code — it commits the reviewed file
set plus the SDLC docs artifacts.

**Tech stack:** Python ≥3.12 · uv · hatchling · ruff · pyright · pytest (asyncio strict).

## Steps

- [ ] **Sync the working state.** rsync `packages/url4/` from the main checkout into the
      worktree, excluding `.venv`, `.ruff_cache`, `.pytest_cache`, `.coverage`, `__pycache__`,
      `.claude`.
- [ ] **Stage & review.** `git add packages/url4` (gitignore-respected); inspect
      `git status`; unstage anything local/junk/env/cache/coverage. Anchor the intended set
      against `git ls-tree -r <base> -- packages/url4` **plus** the three new additions
      (`src/url4/_annotations.py`, `tests/spec/`, `tests/test_scan.py`).
- [ ] **Gates.** From `packages/url4`: `uv sync`, then `uv run ruff check`,
      `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q`. All green before
      commit; never weaken a gate.
- [ ] **Docs artifacts.** Commit spec, plan, work ledger, and task mirror alongside the code.
- [ ] **Commit.** Conventional commit `feat(url4): package v1 SDK`, body `Refs: OME-397`; no
      `Co-Authored-By`. One commit (code + docs) or a small coherent set. Do **not** push.
- [ ] **Close.** Fill the ledger Outcome; close the Linear issue with commits + gates +
      ledger comment; set the task mirror status to done.

## Non-goals / follow-ups

- New-component coordination contract: `.github/workflows/url4-tests.yml`, CODEOWNERS entry,
  dependabot `uv` ecosystem, release lane, and a `packages/url4` stack entry in
  `.claude/sdlc.local.md`. File separately — out of scope here.
- Product workstream (`Epic` group) label assignment — owner-coordinated.

## Risks

- **Tracking junk.** Mitigated by gitignore + explicit exclude list + a `git status` review
  against the anchor set.
- **Gate failures in a fresh checkout.** Mitigated by `uv sync` from the committed `uv.lock`
  before running gates; the suite is the package's own and already authored.
