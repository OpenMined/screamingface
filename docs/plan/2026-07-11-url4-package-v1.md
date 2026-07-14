# url4 SDK v1 — Implementation Plan

**Ticket:** OME-397 · **Spec:** `docs/spec/2026-07-11-url4-package-v1-spec.md`

**Goal:** Land url4 v1 into the monorepo at `packages/url4` as a complete, SDLC-tracked
shared library: the framework-free expression engine, the Python SDK product surface on top
of it, and the CI/coverage/release machinery that makes it a first-class monorepo package —
all as one unit off up-to-date `main`, without altering `main` history.

**Architecture:** `packages/url4` is a `packages/`-tier shared library (distribution `url4`),
not an independently deployed app. Framework-free core: `(sources)!intent` → typed-node DAG,
I/O inverted behind the `IOLayer` port (spec §3, §8). The SDK surface (renderer, builders,
client, node/server) sits on that core without widening its import graph; the core never
imports the facades. CI mirrors the existing per-app lanes (`aigateway`/`scoreboard`).

**Tech stack:** Python ≥3.12 · uv · hatchling · ruff · pyright · pytest (asyncio strict) ·
one runtime dependency (`httpx`, lazy) · optional `server` extra (`uvicorn`).

## Phase 1 — Package & commit the engine core

The parser → AST → DAG → executor engine already exists (developed earlier as a local commit
on the divergent `main`); this phase **packages and commits** the reviewed working state onto
a clean branch, then documents it as-built. No re-development of engine code.

- [x] **Sync the working state.** rsync `packages/url4/` from the main checkout into the
      worktree, excluding `.venv`, `.ruff_cache`, `.pytest_cache`, `.coverage`, `__pycache__`,
      `.claude`.
- [x] **Stage & review.** `git add packages/url4` (gitignore-respected); inspect
      `git status`; unstage anything local/junk/env/cache/coverage. Anchor the intended set
      against `git ls-tree -r <base> -- packages/url4` plus the new additions
      (`src/url4/_annotations.py`, `tests/spec/`, `tests/test_scan.py`).
- [x] **Gates.** From `packages/url4`: `uv sync`, then `uv run ruff check`,
      `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q`. All green before
      commit; never weaken a gate.
- [x] **As-built spec + diagrams.** Write the full technical spec
      (`docs/spec/2026-07-11-url4-package-v1-spec.md`) and the three architecture diagrams
      under `docs/diagrams/` (pipeline, hexagonal ports/adapters, DAG execution model).

## Phase 2 — Build the Python SDK product surface

The engine is complete but has no product surface: the only entry is `run(text, io) -> str`,
with no AST→text inverse, no Python constructors, no result envelope, no node/server side.
This phase adds the four facades (spec §15), each as its own TDD cycle (RED → GREEN → gates →
commit), in dependency order. Every facade keeps strings first-class and the core
framework-free.

- [x] **G1 renderer** (`render.py` + `errors.RenderError` + `grammar.parse_value`) —
      `render(node, *, check=True) -> str`, the inverse of `build()`/`parse()`, certified by
      re-parsing its own output (`build(render(x)) == wrap(x)`). Tests: per-node golden cases,
      unrepresentable-value errors, a hand-curated round-trip corpus, and a seeded random-AST
      property.
- [x] **G2 builders** (`builders.py`) — `expr/src/text/ref/self_/identity/iterate/broadcast/
      reduce/expand` lowering to the existing frozen AST with grammar-faithful normalization
      and the two-axis (attribution / execution) `src()` kwargs. Every builder result must
      satisfy `render(node, check=True)`.
- [x] **G3 client** (`client.py`) — `Client` + frozen `Url4Result` envelope over `run()`,
      local + remote (`RemoteExpr` wrapping for a node target), owned-`HttpIOLayer` lifecycle.
- [x] **G4 node SDK** (`server.py` — named to avoid the `nodes.py`/`dag/node.py` collision) —
      `Url4Node` implementing the `IOLayer` + `SupportsHoldings` ports (a node IS an io layer),
      decorator-registered endpoints/holdings/identities, `evaluate()`, a framework-free
      GET-only ASGI shim, and a lazy-uvicorn `serve()` behind the `server` extra.
- [x] **Finalize.** `__init__.py` exports + quickstart; full gates; design-reviewer pass with
      this plan + spec as rubric (STRUCTURAL findings resolved).

## Phase 3 — CI, coverage gate & release-please conformity

Make `packages/url4` conform to how the existing apps run tests and coverage in CI, closing
the new-component coordination contract.

- [x] **Reorganize tests** from flat `tests/*.py` into `tests/unit/` (+ keep `tests/spec/`),
      matching the apps' convention; confirm the full suite still collects and passes.
- [x] **CI workflow** `.github/workflows/url4-tests.yml` — path-filtered to `packages/url4/**`,
      single Python 3.12 (matches `requires-python` and scoreboard's pattern), `uv sync` +
      ruff + pyright + `pytest --cov=url4 --cov-fail-under=95`, mirroring `scoreboard-tests.yml`
      (test-reporter + PR coverage comment). **Coverage gate is 95%, deliberately above the
      repo's usual 80% for the apps** — see the spec's Decisions section.
- [x] **Coverage to ≥95%.** Add targeted tests for previously-uncovered branches in
      `server.py`, `render.py`, `dag/nodes.py`, `dag/compiler.py`, and `grammar.py` (each from
      a per-file coverage-gap analysis) to clear the raised gate.
- [x] **Register the stack** in `.claude/sdlc.local.md` (`url4` → `packages/url4`,
      `sdlc-python`, gates incl. `--cov-fail-under=95`) so gates run via the standard loop.
- [x] **Release lane** — add a `packages/url4` entry to `release-please-config.json`
      (`release-type: python`, `version-file: packages/url4/pyproject.toml`) for version-bump /
      CHANGELOG automation.
- [x] **Gates + review + close.** Full local gates green; design-reviewer pass; fill the
      ledger Outcome.

## Non-goals / follow-ups

- **CODEOWNERS entry** and **`.github/dependabot.yml`** (`uv` ecosystem): no repo-wide
  precedent exists yet (neither app has them) — a separate repo-wide decision, not minted for
  url4 alone.
- **A real package-publish target** (PyPI or a private index): neither app's release lane
  publishes a Python package (both build only Docker images + Helm charts, which don't apply
  to a library); `release-please` registration gets version automation without inventing a
  publish target. Deferred as a separate decision.
- **Part C+ engine features** deferred at the SDK boundary (spec §15.5): trigger enforcement,
  streaming delivery, the response envelope, settlement/attribution, policy registries,
  auth/consent transport, telemetry planes, module-level query sugar, the `screamingface`
  branding layer.
- **Product workstream (`Epic` group) label assignment** — owner-coordinated.

## Risks (and how they were retired)

- **Tracking junk in Phase 1.** Mitigated by gitignore + explicit exclude list + a
  `git status` review against the anchor set.
- **Renderer completeness (Phase 2).** Mitigated by check-on-render (`build(render(x))` per
  call) + a hand-curated corpus + a seeded random-AST property; the §8.1.2 dual-key boundary
  and the top-level hoisting quirk each get an explicit tested `RenderError`/parenthesization.
- **Node wire conventions (Phase 2).** Endpoint handlers receive opaque, already-resolved
  context; only the eval path re-evaluates — both tested.
- **Coverage bar (Phase 3).** The 95% gate can only go green with real tests, not a threshold
  edit; if the suite couldn't reach it, that's a finding to raise, not a bar to lower — the
  gate command is run locally before commit to prove it.
- **Workflow YAML isn't locally executable** (no `act` in the toolchain). Mitigated by copying
  the two proven, green app workflows structurally and diffing against `scoreboard-tests.yml`.
