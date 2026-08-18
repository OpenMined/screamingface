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

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
