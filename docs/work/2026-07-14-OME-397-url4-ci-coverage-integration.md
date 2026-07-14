---
ticket: OME-397
stack: pkg/url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-14
finished: 2026-07-14
---

# OME-397 — Register packages/url4 CI, coverage, and release-please conformity

## Intent

`packages/url4` shipped under OME-397 with its own pytest/ruff/pyright config but no CI
wiring: no `.github/workflows/url4-tests.yml`, no entry in `.claude/sdlc.local.md` (gates run
manually), and no `release-please-config.json` entry. This was flagged as an intentional,
named follow-up in this same ticket's ledger ("(3) the new-component coordination contract
... is intentionally out of scope — follow-up") and in the `working-in-this-repo` skill's
6-step new-component checklist. This unit closes that gap so `packages/url4` conforms to how
`apps/aigateway`/`apps/scoreboard` run tests and coverage in CI, per explicit instruction to
fold this into OME-397 rather than file a separate ticket.

Scope was narrowed in conversation against what the two existing apps actually have (not
their aspirational ideal):
- **CODEOWNERS / dependabot: dropped.** Neither exists anywhere in the repo today (not even
  for aigateway/scoreboard) — adding them for url4 only would invent unreviewed repo-wide
  convention as a side effect of a package-level conformity task.
- **Package publishing (PyPI/registry): dropped.** Neither release workflow publishes a
  Python package — both only build Docker images + Helm charts, which don't apply to a
  library. `release-please-config.json` registration (version-bump/CHANGELOG automation) is
  in scope; an actual publish target is a separate future decision.
- **Test layout reorg: in scope.** `packages/url4/tests/` is currently flat; apps use
  `tests/unit/` (+ `tests/integration/`, `tests/live/` for aigateway). Reorganize into
  `tests/unit/` + keep `tests/spec/` as its own subdir.
- **Coverage gate: 95%, not 80% (mid-session correction, not a copy error).** Raised by
  explicit instruction after this plan was already approved and partway implemented.
  `apps/aigateway`/`apps/scoreboard` remain at 80% — this is url4-specific. Actual coverage
  after the test reorg was 92.47%, below 95%, so closing the gap required writing new tests
  (not just editing the threshold) — see Outcome.

## Planned changes

- `.github/workflows/url4-tests.yml` (new) — path-filtered to `packages/url4/**` (+ self),
  working-directory `packages/url4`, single Python 3.12 (matches `requires-python = ">=3.12"`
  and scoreboard's single-version pattern — no evidence url4 needs a matrix). Steps: `uv sync`,
  `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, then
  `uv run pytest --tb=short --junitxml=results.xml --cov=url4 --cov-report=xml:coverage.xml
  --cov-report=term-missing --cov-fail-under=95 -v`. dorny/test-reporter + orgoro/coverage
  (PR-only) steps mirroring `scoreboard-tests.yml`.
- `.claude/sdlc.local.md` — add a `url4` stack entry (root `packages/url4`, skill
  `sdlc-python`, `test_globs: ["tests/**"]`, gates: ruff check, ruff format --check, pyright,
  `pytest --cov=url4 --cov-fail-under=95 -q`) so gates run via the standard loop instead of
  manually.
- `release-please-config.json` — add a `packages/url4` entry (`release-type: python`,
  `package-name`/`component: url4`, `tag-separator: "-"`, `include-component-in-tag: true`,
  `version-file: packages/url4/pyproject.toml`), matching the aigateway entry shape.
- `packages/url4/tests/` — move the flat `test_*.py` files into `tests/unit/`; keep
  `tests/spec/` as-is; verify `conftest.py` fixtures and `testpaths = ["tests"]` still resolve
  correctly with the new layout (pytest discovers recursively, so no config change expected,
  but confirm).

## Test plan

Infra/config unit, no new production code — same acceptance shape as OME-397's original
packaging unit (no RED/GREEN TDD cycle). The acceptance is that url4's **own** existing test
suite still passes, unchanged in content, after the directory reorg, and that the new gate
commands run clean locally (proving the CI workflow's commands are correct before they ever
run in GitHub Actions).

## Acceptance

- `packages/url4/tests/` reorganized (`tests/unit/` + `tests/spec/`); all pre-existing tests
  still collected and passing; no import-path breakage.
- Local gates green from `packages/url4`: `uv run ruff check`, `uv run ruff format --check`,
  `uv run pyright`, `uv run pytest --cov=url4 --cov-fail-under=95 -q`.
- `.github/workflows/url4-tests.yml` present, path-filtered, structurally consistent with
  `aigateway-tests.yml`/`scoreboard-tests.yml`.
- `.claude/sdlc.local.md` has a `url4` stack entry.
- `release-please-config.json` has a `packages/url4` entry.
- Conventional commit(s), body `Refs: OME-397`; nothing pushed; no commit to `main`.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** As planned, plus the coverage gap-closing work the 95% raise required:
  `.github/workflows/url4-tests.yml` (new), `.claude/sdlc.local.md` (url4 stack entry),
  `release-please-config.json` (`packages/url4` entry), 15 flat test files moved into
  `packages/url4/tests/unit/` (`tests/spec/` and `tests/conftest.py` untouched), and
  substantial new test functions added to `tests/unit/test_server.py` (+151 lines),
  `tests/unit/test_render.py` (+190 lines), `tests/unit/test_dag.py` (+390 lines, covering
  both `dag/nodes.py` and `dag/compiler.py`), `tests/unit/test_grammar.py` (+259 lines) — each
  written by a separate implementer agent from a scout's line-by-line coverage-gap analysis of
  the corresponding source file, with a design-reviewer pass (verdict: ACCEPT-WITH-FIXES,
  findings were documentation-only — see Deviations) before commit. No `packages/url4/src/**`
  production file was touched.
- **Commits:** pending — this ledger's Outcome is filled pre-commit per this branch's
  established pattern (see the original OME-397 ledger); the sha will be recorded in a small
  follow-up if not already present in the same commit.
- **Gates:** from `packages/url4` — `uv run ruff check` → all checks passed; `uv run ruff
  format --check` → 50 files already formatted; `uv run pyright` → 0 errors, 0 warnings, 0
  informations; `uv run pytest --cov=url4 --cov-fail-under=95 -q` → **697 passed**, **97.86%**
  total coverage (up from 92.47% before the gap-closing tests), gate (95%) cleared with
  margin. Per-file coverage after: server.py 99%, render.py 96%, dag/nodes.py 99%,
  dag/compiler.py 99%, grammar.py 99% (all four scouted/implemented files); remaining
  untouched-but-still-≥86%-covered files (builders.py, client.py, dag/executor.py,
  dag/node.py, ensemble.py, io_layer.py, io_static.py, nodes.py, parser.py, subrequest.py)
  were not targeted since the five scouted files alone cleared the 95% package-wide bar.
- **Deviations:**
  (1) Coverage threshold raised from the originally-planned 80% to 95% by explicit
  mid-session instruction, after this plan was already approved and partway implemented —
  required writing new tests to close a real 92.47%→95% gap, not just a threshold edit; spec
  and plan were corrected post-hoc to say 95 throughout (a design-review pass caught that the
  first draft of both still said 80 in the url4-target sections after the correction).
  (2) Two real gate failures were found and fixed during the final local gate run (not present
  in any implementer's own verification, since each implementer only ran its own file's tests
  in isolation, not the full suite + lint + typecheck together): a ruff `F841` unused-variable
  in `test_dag.py`, and two pyright `reportAttributeAccessIssue` errors in `test_dag.py` from
  accessing `.quorum` on a `DagNode`-typed variable without narrowing — fixed with
  `assert isinstance(graph.sink, ProcessNode)`, which both satisfies pyright and asserts a
  real structural invariant (not a suppress-and-move-on fix).
  (3) `dag/nodes.py` lines 275-277 and 780 were investigated per a scout's flagged discrepancy
  (scout believed existing tests already covered them; pytest-cov said otherwise) — confirmed
  genuinely uncovered: `StaticIOLayer` always implements `fetch_holdings`, so the existing
  holdings tests never reached `HoldingsNode.resolve()`'s own port-support check; a
  `NoHoldingsIOLayer` test double was added to reach it for real.
  (4) One coverage line (`render.py:518-524`) was investigated and found genuinely unreachable
  via the public `render()` entry point (upstream interception in `_source_value_and_tail`) —
  documented in-line as an `AIDEV-NOTE` rather than forced with an artificial direct-call test,
  matching the spec's own precedent for other unreachable/defensive branches.
  (5) No Linear update this round — Linear MCP unavailable (not connected this session) and
  linear-cli unavailable (vault master password not available in this session); explicit user
  instruction to skip the Linear step and fold this work into OME-397 without a status change.
