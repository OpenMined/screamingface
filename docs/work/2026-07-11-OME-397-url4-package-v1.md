---
ticket: OME-397
stack: pkg/url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-11
finished: 2026-07-14
---

# OME-397 — url4 SDK v1 (engine, SDK surface, CI integration)

## Intent

Land url4 v1 into the monorepo at `packages/url4` as one SDLC-tracked unit: the framework-free
expression engine, the Python SDK product surface on top of it, and the CI/coverage/release
machinery that makes it a first-class monorepo package. url4 is a standalone core library for
the url4 expression protocol — `(sources)!intent` compiles into an executable DAG of typed
nodes (`url4.dag`); independent nodes run in parallel and all I/O is inverted behind an
`IOLayer` port. The engine already existed (developed earlier as a local commit on the
divergent `main`); the SDK surface and CI integration are new. Delivered in three phases off
up-to-date `main`, without altering `main` history. Lands the package that the earlier
deferred extraction item `OME-367` anticipated.

## Planned changes

**Phase 1 — package the engine core.** Sync the reviewed `packages/url4/` working state into
the worktree (rsync, excluding `.venv`/caches/`.coverage`/`__pycache__`/`.claude`); commit the
engine (parser/AST/DAG/executor/IOLayer + conformance suite) with an as-built technical spec
and three architecture diagrams. No re-development of engine code.

**Phase 2 — the SDK product surface** (`packages/url4/src/url4/`):
- `render.py` (new) + `errors.RenderError` + public `grammar.parse_value()` — the renderer.
- `builders.py` (new) — Python AST constructors.
- `client.py` (new) — `Client` + `Url4Result`.
- `server.py` (new) — `Url4Node` + framework-free ASGI shim (lazy uvicorn behind the `server`
  extra); `pyproject.toml` gains the `server` optional-dependency.
- `__init__.py` exports; new `tests/` for each facade.

**Phase 3 — CI/coverage/release conformity:**
- `.github/workflows/url4-tests.yml` (new) — path-filtered, Python 3.12, ruff + pyright +
  `pytest --cov=url4 --cov-fail-under=95`, mirroring `scoreboard-tests.yml`.
- `.claude/sdlc.local.md` — `url4` stack entry (gates incl. `--cov-fail-under=95`).
- `release-please-config.json` — `packages/url4` entry.
- `packages/url4/tests/` — reorganize flat files into `tests/unit/` (keep `tests/spec/`).
- Targeted new tests to clear the 95% coverage gate.

Docs artifacts (this unit): `docs/spec/2026-07-11-url4-package-v1-spec.md`,
`docs/plan/2026-07-11-url4-package-v1.md`, this ledger, and the
`docs/tasks/2026-07-11-url4-package-v1.md` mirror.

## Test plan

- **Phase 1** (packaging of pre-existing, already-tested engine code — no RED/GREEN cycle):
  acceptance is that url4's own conformance/unit suite passes under its own toolchain, proving
  the packaged state is coherent and self-contained.
- **Phase 2** (new facade code — TDD per facade): G1 per-node render golden cases + a
  round-trip property `build(render(x)) == wrap(x)` over the corpus + a seeded random-AST
  generator + unrepresentable-value `RenderError`s; G2 builder→render golden strings, coercion
  matrix, validation errors; G3 `Client` over `StaticIOLayer` (query/broadcast/iterate/reduce,
  remote target, `Url4Result.text/.data/.elements`, aclose lifecycle); G4 endpoint dispatch,
  holdings/identity incl. error codes, eval-path loop via `httpx.ASGITransport`, ASGI status
  mapping (200/400/403/404/405/502), GET-only.
- **Phase 3** (config/infra + coverage): the suite still passes after the directory reorg; the
  new gate commands run clean locally (proving the CI workflow's commands before they ever run
  in Actions); the 95% coverage gate is cleared by real tests targeting uncovered branches.

## Acceptance

- Engine packaged; tracked set is the reviewed file set (no caches/venv/coverage/tooling junk).
- All four SDK facades land with tests; the round-trip property holds for every corpus
  expression; prior engine tests stay green and unmodified.
- `packages/url4/tests/` reorganized (`tests/unit/` + `tests/spec/`); no import-path breakage.
- Local gates green from `packages/url4`: `uv run ruff check`, `uv run ruff format --check`,
  `uv run pyright`, `uv run pytest --cov=url4 --cov-fail-under=95 -q`.
- `.github/workflows/url4-tests.yml`, the `.claude/sdlc.local.md` `url4` stack entry, and the
  `release-please-config.json` `packages/url4` entry all present.
- Conventional commits, bodies `Refs: OME-397`; nothing pushed; `main` history untouched.

## Outcome

- **Actual files:**
  - *Engine (Phase 1):* the reviewed `packages/url4/` engine set (parser/AST/DAG/executor,
    `io_layer`/`io_static`/`io_http`, `subrequest`, `context`, `ensemble`, `errors`,
    `_annotations`, `_scan`, `nodes`, `dag/*`) + the `tests/spec/` conformance suite; `git add`
    (gitignore-respected) staged exactly the intended set, verified against
    `git ls-tree -r b1277c4 -- packages/url4` plus the known additions. Plus the as-built spec,
    plan, this ledger, the task mirror, and the three `docs/diagrams/` architecture diagrams
    (SVG + PNG): `url4-pipeline`, `url4-hexagonal-ports-adapters`, `url4-dag-execution-model`.
  - *SDK surface (Phase 2):* `render.py`, `builders.py`, `client.py`, `server.py`, the
    `errors.RenderError` + `grammar.parse_value()` additions, `__init__.py` exports,
    `pyproject.toml` `server` extra, `io_static.py` (routes accept canonical `?params&q=`
    forms), and the new facade tests. Two shape decisions from the design review: the node SDK
    landed as `server.py` (not `node.py` — avoids the `nodes.py`/`dag/node.py` name pileup),
    and the dual-wire-convention decode was relocated into `subrequest.py` (its single-owner
    codec module) rather than living in the server.
  - *CI/coverage (Phase 3):* `.github/workflows/url4-tests.yml`, the `.claude/sdlc.local.md`
    `url4` stack entry, the `release-please-config.json` `packages/url4` entry; the flat
    `tests/*.py` files moved into `tests/unit/` (`tests/spec/` and `tests/conftest.py`
    untouched); and substantial new tests added to `tests/unit/test_server.py`,
    `test_render.py`, `test_dag.py`, `test_grammar.py` to clear the 95% gate. No
    `packages/url4/src/**` production file was changed in Phase 3.
- **Commits (this branch, oldest first):**
  - `ffc1c95` feat(url4): package v1 SDK · `1ed9c8f` docs(OME-397): record package commit sha
  - `24d9128` docs(url4): rewrite spec as a full technical specification ·
    `c720187` docs(url4): add architecture diagrams · `9d58d08` chore(url4): gitignore Jupyter
    checkpoints, log pre-PR cleanliness scan
  - `8257ad0` feat(url4): expression renderer · `c4a5ab5` feat(url4): builder facade ·
    `c87ca11` feat(url4): client facade — Client + Url4Result envelope ·
    `b800d93` feat(url4): node SDK — Url4Node registries, evaluation, ASGI shim ·
    `404de24` feat(url4): export the SDK facades from the package root ·
    `abf1eb6` refactor(url4): apply design-review findings + close out the ledger ·
    `3e5638e` fix(url4): restore RenderError + parse_value dropped from the cherry-pick set
  - `7b3b150` feat(url4): register CI, coverage gate, and release-please conformity ·
    `62ab19b` docs(url4): record CI integration commit sha in work ledger
- **Gates (final state):** from `packages/url4` — `uv run ruff check` → all checks passed;
  `uv run ruff format --check` → 50 files already formatted; `uv run pyright` → 0 errors,
  0 warnings; `uv run pytest --cov=url4 --cov-fail-under=95 -q` → **697 passed**, **97.86%**
  total coverage (95% gate cleared with margin). Per-file coverage of the five gap-closed
  files: server.py 99%, render.py 96%, dag/nodes.py 99%, dag/compiler.py 99%, grammar.py 99%.
- **Design reviews:** two design-reviewer passes, both verdict ACCEPT-WITH-FIXES, zero
  structural findings. Phase-2 review fixes applied: wire-decode moved to its single-owner
  codec module; grammar `_STRUCT_KEY_RE` and `_annotations._VALID_ON_ERROR` reused instead of
  re-derived; `Url4Node(data=…)` restored; one identity-name rule; two findings resolved by
  amending the spec (`Url4Result.elements` raises `ValueError`; quorum IS enforced by the
  executor). Phase-3 review fixes: spec/plan/ledger coverage references reconciled to 95%; the
  ledger Outcome filled; the two real gate failures below fixed.
- **Deviations:**
  1. **Coverage gate is 95%, not the repo's usual 80%.** `apps/aigateway`/`apps/scoreboard`
     stay at 80%; this is url4-specific by explicit instruction. Clearing it required writing
     new tests (actual coverage after the test reorg was 92.47%), not just a threshold edit —
     each of the five gap-closed files was analyzed for its uncovered branches, and genuinely
     unreachable/defensive lines were left uncovered and documented (e.g. `server.py`'s
     blocking `uvicorn.run()`, `render.py:518-524` which is intercepted upstream and
     unreachable via the public `render()` entry, `dag/nodes.py`'s defensive `_run_all`
     fallback) rather than forced with artificial tests.
  2. **Two real gate failures found and fixed on the final full-suite run** (not caught by the
     per-file test runs): a ruff `F841` unused variable and two pyright
     `reportAttributeAccessIssue` errors in `test_dag.py` (accessing `.quorum` on a
     `DagNode`-typed value) — fixed with `assert isinstance(graph.sink, ProcessNode)`, which
     both narrows the type and asserts a real structural invariant.
  3. **`packages/url4` was not registered in `.claude/sdlc.local.md` during Phases 1–2** (gates
     were run manually); Phase 3 closed that card gap.
  4. **`render.py` (633 lines) exceeds the sdlc-python ≤450-line guidance** but matches package
     norms (`grammar.py` 739, `dag/nodes.py` 857); kept whole rather than split for a
     line-count target.
  5. **No RED/GREEN TDD cycle in Phase 1** (packaging of pre-existing, already-tested code) and
     **no new Linear filing** — this whole unit is tracked under OME-397 per explicit
     instruction (the Linear MCP/CLI were unavailable this session; the work is recorded here
     and in the task mirror, with `main` history untouched and nothing pushed).
- **Engine findings for the grammar owner (Kevin)** — surfaced while building the SDK surface,
  not yet actioned:
  1. A top-level `/p(c)!'i'` / `url4://…(c)!'i'` **hoists** the intent to expression level —
     spec §3.1.1 reads as whole-expression-remote; the SDK parenthesizes to compensate.
  2. The envelope's reduce-over-iteration decode is greedy: `(…, A*(b)!'p')!'r'` swallows
     sibling sources into the collection prefix (silent data loss on some shapes) — consider
     requiring double parens for expression collections.
  3. Spec §5.3.1's direct `(expr)!'Clean'*(…)` form does not parse; the engine needs
     `((expr)!'Clean')*(…)`.
  4. Unnamed structured weights and unnamed budget-first descriptors are parser-unreachable
     (sugar/value-shape capture) — worth a spec note.
