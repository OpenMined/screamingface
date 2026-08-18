---
ticket: OME-876
stack: screamingface-engine
status: in_progress
started: 2026-08-18
finished:
---

# OME-876 — Rename `apps/url4-cloud` to `apps/screamingface-engine`

## Intent

The Engine app is named `url4-cloud` in the repo while the product, the Linear landing label,
and the published image prefix all say ScreamingFace Engine. This unit renames the repo-side
identity so the three agree. `url4-cloud` reads as a component of the url4 language, which it is
not — it is the Engine that executes url4, and `packages/url4` is the language.

Scope is **T2 / Path A** (see `docs/spec/2026-08-18-screamingface-engine-rename.md`): identity,
CI, release and chart naming change; the runtime config surface, the NATS names and the
Kubernetes pod labels do not. `packages/url4` is never touched.

## Planned changes

**B1 — package + app move**
- `git mv apps/url4-cloud apps/screamingface-engine`
- `git mv .../src/url4_cloud .../src/screamingface_engine`
- Rewrite `url4_cloud` → `screamingface_engine` in `src/` (100 files) and `tests/` (119 files)
- `pyproject.toml`: `name`, `description`, `[project.scripts]`, hatch `packages`, ruff
  `known-first-party`, pyright `ignore`, pytest `filterwarnings`, coverage `omit`
- `rm -rf .venv && uv sync`; `uv lock`

**B2 — images**
- `Dockerfile`, `Dockerfile.benchmark`: COPY paths, `WORKDIR`, OCI labels, `CMD`, comments

**B3 — Helm chart**
- `Chart.yaml` `name`; all 13 `_helpers.tpl` definitions + call sites across 14 templates
- `values.yaml`: **add `nameOverride: "url4-cloud"`** (the Path A pin) + image repositories
- `values-cloud.yaml`, `values.schema.json`, chart `README.md`, `NOTES.txt`

**B4 — CI + release identity**
- `git mv` `url4-cloud-tests.yml`, `dev-build-url4-cloud.yml`, `release-url4-cloud.yml`
- Inside: names, concurrency groups, path filters, `working-directory`, `--cov=`, tag trigger,
  bake target, console-script smoke steps
- `charts.yml` path filters; `release-please-config.json`; `.release-please-manifest.json`
- `.github/scripts/verify_chart_wiring.py`; `dependabot.yml`; `dependabot-ignores.yml`;
  `CODEOWNERS`; `.dockerignore`

**B5 — agent config + live docs**
- `.claude/scripts/check_layering.py` (`SRC` + docstring)
- `.claude/skills/working-in-this-repo/SKILL.md`; `.claude/sdlc.local.md`;
  `.claude/task-board.local.md`
- `docs/diagrams/url4-cloud-execution-flows.gen.py` → rename + **regenerate** the 6 artifacts
- Live prose: `docs/spec`, `docs/plan`, root `README.md`, `CONTRIBUTING.md`, `public-docs/src`,
  the app's own `README.md` and `docs/*.md`

**Explicitly NOT changed** (tracked in `OME-877`): the `URL4_CLOUD_*` env prefix, `subjects.py`
`PREFIX`, `RUNNER_LABELS`, `URL4_RUNNER_CONFIG`, the `url4.screamingface.ai` hostname,
`apps/aigateway`, `CHANGELOG.md`, `docs/work/**`, `docs/tasks/**`, existing git tags.

## Test plan

RED first. Two new tests encode the properties this rename must establish; both fail today.

1. **Path A chart equivalence** (the load-bearing invariant) — render the chart and assert the
   chart is *named* `screamingface-engine` while its rendered identity is still `url4-cloud`:
   every object name equals `url4-cloud-url4-cloud`-style, and every `matchLabels` carries
   `app.kubernetes.io/name: url4-cloud`. Fails today because `Chart.yaml` still says
   `url4-cloud`. Guards the reason the deploy stays a rolling update.
2. **Package identity** — the distribution is `screamingface-engine`, the import package is
   `screamingface_engine`, and both console scripts resolve. Fails today.
3. **No stale identifier** — no `url4_cloud` identifier remains under `src/` or `tests/`, and no
   `url4-cloud` string remains outside the named exception list. Fails today.

Existing tests are the regression net: the `git mv` in B1 breaks all 119 test modules until the
imports are rewritten, which is the natural RED→GREEN for a mechanical rename. **No prior test is
modified except for its import path**, which is the rename itself, not a weakening.

Boundary/error cases covered by test 3's exception list: the `nameOverride` pin, `subjects.py`
`PREFIX`, `RUNNER_LABELS`, and the historical-record paths must each still contain `url4-cloud`.

## Acceptance

- `uv run .claude/scripts/run_gates.py screamingface-engine` all green (ruff, format, pyright,
  `check_layering.py`, pytest with `--cov=screamingface_engine --cov=url4.streaming`
  `--cov-fail-under=80`)
- `python3 .github/scripts/verify_chart_wiring.py` passes
- `helm template` before vs after differs **only** in `helm.sh/chart` and the image repository;
  all object names and `matchLabels` byte-identical
- Both images build; `screamingface-engine --help` and `screamingface-engine run --help` resolve;
  the `url4-cloud` aliases still resolve
- `uv lock --check` clean
- Release identity carries `1.3.0` forward → next tag `screamingface-engine-v1.4.0`

## Outcome

- **Actual files:** 353 changed — 301 renames, 10 added, 7 deleted, 35 modified. Matches the plan's
  five batches. The 7 deletions are 4 heavily-rewritten modules and the 3 regenerated PNGs, which
  git recorded as delete+add rather than rename; the 10 additions are their counterparts plus the
  3 new test modules.

- **Commits:**
  - `d79e3a4e` — docs(screamingface-engine): spec, plan and ledger for the app rename
  - `b36dc3b4` — feat(screamingface-engine): rename the app, package and chart from url4-cloud
  - `be47dabc` — ci(screamingface-engine): rename the CI lanes, release identity and images
  - `1da55586` — docs(screamingface-engine): update agent config, diagrams and stale paths

- **Gates:** `run_gates.py screamingface-engine` → **ALL GATES GREEN** (append-only test check ·
  ruff check · ruff format · pyright · check_layering · pytest with
  `--cov=screamingface_engine --cov=url4.streaming --cov-fail-under=80`). Engine suite **1733
  passed, 5 skipped**. Also verified: `verify_chart_wiring.py` **31/31**; `packages/url4` **1146
  passed**; `apps/aigateway` ruff/format clean + **844 passed**; `packages/screamingface`
  ruff/format clean + the 3 touched modules **47 passed**.

- **Acceptance — the Path A test:** `helm template` of the pristine `main` chart vs the renamed one
  (309 lines each) differs only in `# Source:`, `helm.sh/chart`, the image repository, the
  per-render random `jwt-secret`, and the two `checksum/*` annotations. **All 9 object names are
  identical**, `app.kubernetes.io/name` is `url4-cloud` on both sides, and the Deployment selector
  is unchanged. The `checksum/*` change is the intended mechanism — the ConfigMap content changed,
  so pods roll.

### Deviations

1. **Dated `docs/spec/` and `docs/plan/` are NOT rewritten.** The plan listed them as live docs.
   They are per-unit historical artifacts like `docs/work/`, so rewriting their prose would falsify
   them. The new spec carries a supersession note instead. Their filenames are also referenced by
   historical ledgers, which the rewrite would have dangled.
2. **Runtime invocation names retained.** `K8sJobRunner`'s `("url4-cloud", "run")` and the image
   `CMD ["url4-cloud"]` stay, alongside both console aliases, because App and image are separate
   objects that roll at different moments. The chart's Deployment `command` DID move — it travels
   in the same pod template as its image, so it has no skew. `OME-877` moves the rest together.
3. **76 line-length violations**, unanticipated: `screamingface_engine` is 9 characters longer than
   `url4_cloud`, so wrapped prose overflowed. Re-wrapped across 44 files (delegated as a mechanical
   transform, then independently re-verified against the gates and the survivor assertions).
4. **Two task-board card entries were stale independently of this rename** and were corrected
   against live Linear: `url4-engine` had been renamed to `url4-sdk`, and the `screamingface-engine`
   landing label — already applied to live issues — had no entry at all.
5. **Broken paths fixed in three other components**, beyond the planned scope but factually broken
   by the move: `packages/screamingface/justfile` (executable recipes), the public-docs Engine and
   Architecture pages (GitHub links that would 404), and `apps/aigateway-ui/.dockerignore`. Paths
   only — prose in other components was left for its owners.
6. **`pre-commit run --all-files` had to be partially reverted.** It "fixed" 37 files of
   pre-existing non-compliance across unrelated apps, packages and a historical `docs/tasks/`
   mirror. All 37 were restored to `HEAD` so this PR carries only its own change.

7. **The unit became genuinely cross-component mid-flight, and cannot be split.** `main` advanced
   by two commits while this was in progress, and PR #590 ("Add pip-installable ScreamingFace
   runtime") introduced coupling that did not exist at the branch point:
   `packages/screamingface/scripts/runtime_build_hook.py` **vendors the Engine's source tree into
   the SDK wheel and sdist**, and `screamingface._runtime.server` **imports the Engine as a Python
   module**. The scan done at planning time correctly concluded that nothing outside the app
   imported `url4_cloud`; that answer expired.

   Owner decision: keep one PR and record it here rather than decompose into an epic. Atomicity is
   forced — the SDK's build hook validates that the Engine paths exist before building, so any
   split leaves `main` unbuildable. Five sites needed updating (the hook's two source tuples
   including the wheel destination, five imports in `_runtime/server.py`, the prepare-module path
   in `_runtime/cli.py`, the expected vendored path in `check_distribution.py`, and the checkout
   fallback in `_runtime/config.py`).

   **Only CI caught this.** Nothing local did: an already-installed editable venv does not re-run
   the build hook, so `uv run pytest` stayed green while a fresh `uv sync` failed.

8. **One prior test changed with explicit owner approval** (`packages/screamingface/tests/
   test_runtime_cli.py`). It asserts that importing `screamingface` does not eagerly load heavy
   modules and named `url4_cloud` in that list. Leaving it was the unsafe option: the module cannot
   appear in `sys.modules` under the old name again, so the assertion would have passed vacuously
   forever. The append-only gate flagged it and the work stopped until approved.

### Notes for the next agent

- **A path built from separate components defeats a literal search.**
  `_runtime/config.py` had `Path(...) / "apps" / "url4-cloud" / "url4.toml"`, which no grep for
  `apps/url4-cloud` can find. When auditing a rename, search the bare token too, not only the
  joined path — and read the whole result rather than truncating it, which is how this one survived
  the first pass.
- **The append-only gate is blind under a directory rename.** Test files that move to a new path
  have no counterpart at `HEAD`, so they read as *added* and any change inside them goes unflagged.
  This branch did sweep 13 prior engine test files (comment prose, opaque fixture strings, and two
  real path constants); no assertion's meaning changed and the suite total held at 1738, but the
  green gate is not evidence of that — only reading the diff is.
- **The shell wrapper truncates `helm` stdout before a redirect**, writing a literal
  `... (262 lines truncated)` marker into the output file — and a wrapped `diff` then reported two
  truncated renders as "Files are identical". Use `rtk proxy helm …` for any chart measurement. The
  `test_chart_identity.py` helm test is unaffected because it shells out from Python.
- `packages/screamingface` has **pre-existing failures unrelated to this work**, confirmed identical
  on pristine `main`: 1 collection error (`ipywidgets` absent) and 4 progress-panel timing failures.
- Version `1.3.0` carries forward. Commit types are non-breaking deliberately, so release-please
  cuts **`screamingface-engine-v1.4.0`** rather than a major bump. Renaming a published image
  repository is arguably major; if a `2.0.0` is wanted, that is an owner call and needs a
  `BREAKING CHANGE:` footer.

**Status:** work complete, gates green, awaiting PR review. Closes on merge.
