# Plan — rename the Engine app to `screamingface-engine`

- **Ticket:** `OME-876` · **Spec:** `docs/spec/2026-08-18-screamingface-engine-rename.md`
- **Branch / worktree:** `OME-876-rename-engine`

## Why this is one work item

The card splits cross-cutting work (≥2 apps or packages) into an epic. Path A keeps
`apps/aigateway` out of scope, so this touches one app plus repo-level infrastructure.

More decisively, the core cannot be split across pull requests without leaving `main` red: the CI
path filters, the package name, the coverage flag and the chart all name each other. Renaming the
package without renaming `--cov=url4_cloud` in the test workflow fails on the first push.

One worktree, one PR, ordered commits. Deferred names go to `OME-877`.

## Transformation rules

Three tokens, three fates. Case-sensitive throughout.

| Token | Action | Why |
| --- | --- | --- |
| `url4_cloud` | → `screamingface_engine` | Python package path. Never a substring of a legitimate `url4` engine reference. |
| `url4-cloud` | → `screamingface-engine`, minus the exceptions | Directory, distribution, chart, image, CI names. |
| `URL4_CLOUD` | **unchanged** | Env prefix. T2 keeps the config surface; the distinct case makes a case-sensitive pass safe. |
| `url4`, `url4.streaming`, `URL4-Capability` | **never** | `packages/url4` is a different component. |

### `url4-cloud` occurrences that must survive

1. `deploy/helm/values.yaml` — `nameOverride: "url4-cloud"` (added by this plan; the Path A pin)
2. `src/…/subjects.py` — `PREFIX = "url4-cloud"` (renaming orphans live NATS streams)
3. `src/…/adapters/k8s.py` — `RUNNER_LABELS` (`url4-runner`, `part-of: url4-cloud`)
4. `apps/aigateway/charts/aigateway/values.yaml`, `values-prod.yaml` — `clientPodNames`
5. `.github/scripts/verify_chart_wiring.py` — the assertion about that allowlist, and the
   `URL4_CLOUD_RUNNER_IMAGE` ConfigMap key (an env name, not an identity)
6. `CHANGELOG.md`, `docs/work/**`, `docs/tasks/**`
7. Existing git tags `url4-cloud-v1.0.0`…`v1.3.0`

## Batches

Each batch ends green before the next begins. `git mv` for every move, so history follows.

### B0 — RED

Add the three tests from the ledger's test plan. All three must fail for the right reason before
any rename happens:

- `tests/unit/test_chart_identity.py` — the chart is named `screamingface-engine` **and** its
  rendered object names and `matchLabels` still carry `url4-cloud`. This is the Path A invariant;
  it is the one test that would catch a silently broken deploy.
- `tests/unit/test_package_identity.py` — distribution `screamingface-engine`, import package
  `screamingface_engine`, both console scripts resolve, and the `url4-cloud` aliases still resolve.
- `tests/unit/test_no_stale_identifier.py` — no `url4_cloud` under `src/`/`tests/`, and no
  `url4-cloud` outside the exception list above. The exception list is asserted positively, so
  removing a survivor fails too.

### B1 — package + app move

`git mv apps/url4-cloud apps/screamingface-engine`, then
`git mv src/url4_cloud src/screamingface_engine`. Rewrite the identifier across `src/` (100 files)
and `tests/` (119). `pyproject.toml`: `name`, `description`, `[project.scripts]` (add the new pair,
retain the old), hatch `packages`, ruff `known-first-party`, pyright `ignore`, pytest
`filterwarnings`, coverage `omit`. Keep `url4 = { path = "../../packages/url4", editable = true }`.

Then `rm -rf .venv && uv sync` — a moved directory leaves stale absolute shebangs in `.venv/bin/*`
that surface as import errors resembling lockfile corruption. Then `uv lock`.

### B2 — images

`Dockerfile` and `Dockerfile.benchmark`: COPY paths, `WORKDIR`, OCI labels, `CMD`, the build
commands in the header comments, and the `ModuleNotFoundError` diagnostic string. The repo-root
build context is unchanged — still required for the `packages/url4` path dependency.

### B3 — Helm chart

`Chart.yaml` `name`. Rename all 13 `_helpers.tpl` definitions and every `include` call site across
the 14 templates. Add `nameOverride: "url4-cloud"` to `values.yaml` with a comment naming
`OME-877`. Image repositories → `screamingface-engine` and `screamingface-engine-benchmark`
(the `-benchmark` derivation in `runnerImage` needs no logic change). Update
`values.schema.json`, chart `README.md`, `NOTES.txt`. Leave the `url4.screamingface.ai` hostname.

### B4 — CI + release identity

`git mv` the three workflows. Inside them: workflow and job names, concurrency groups, path
filters, `working-directory`, `--cov=screamingface_engine`, tag trigger →
`screamingface-engine-v*`, the bake target, and the console-script smoke steps. Then `charts.yml`
path filters; `release-please-config.json` and `.release-please-manifest.json` (key, `component`,
`package-name`, `version-file`, carrying `1.3.0`); `verify_chart_wiring.py` constants, chart path
and the two workflow filenames it reads; `dependabot.yml` (2 ecosystem paths, 5 group names);
`dependabot-ignores.yml`; `CODEOWNERS`; `.dockerignore`.

### B5 — agent config + live docs

`.claude/scripts/check_layering.py` `SRC` path and docstring (the `CONTROL_PLANE`/`RUN_MODE` lists
are submodule names and need no change). `.claude/skills/working-in-this-repo/SKILL.md` routing row
and the §5 bullet. `.claude/sdlc.local.md` stack name, root and `--cov=` flag.
`.claude/task-board.local.md` — also correct the stale landing label, since live Linear already
uses `screamingface-engine`. Rename the diagram generator and **regenerate** the 6 SVG/PNG
artifacts rather than editing them. Live prose only: `docs/spec`, `docs/plan`, root `README.md`,
`CONTRIBUTING.md`, `public-docs/src`, and the app's own `README.md` and `docs/*.md`.

## Verification

| Gate | Command |
| --- | --- |
| Stack gates | `uv run .claude/scripts/run_gates.py screamingface-engine` |
| Layering | `python3 .claude/scripts/check_layering.py` |
| Chart wiring | `python3 .github/scripts/verify_chart_wiring.py` |
| Lockfile | `uv lock --check` |
| Images | build both; `screamingface-engine --help`, `screamingface-engine run --help` |

**The Path A acceptance test**, run manually once before the PR as a cross-check on B0's unit test:

```sh
helm template url4-cloud <before> --set-string config.natsUrl=nats://n:4222 > /tmp/before.yaml
helm template url4-cloud <after>  --set-string config.natsUrl=nats://n:4222 > /tmp/after.yaml
diff /tmp/before.yaml /tmp/after.yaml
```

Only `helm.sh/chart` and the image repository may differ. Any change to an object name or a
`matchLabels` block means the pin is not working and the deploy is no longer a rolling update.

## Risks

| Risk | Mitigation |
| --- | --- |
| A blind replace catches `packages/url4` | Case-sensitive, token-scoped rules; `URL4_CLOUD` untouched; B0's stale-identifier test asserts the survivors positively |
| The chart pin silently fails | B0's chart-identity test plus the manual `helm template` diff |
| Stale `.venv` after the move | `rm -rf .venv && uv sync` is a named step in B1 |
| Historical docs rewritten | Exception list; the stale-identifier test excludes those paths |
| Release lane and chart disagree on the image | `verify_chart_wiring.py` compares them; updated in B4 and run as a gate |

## Post-merge

Confirm the live release name before anyone runs `helm upgrade`. `URL4_CLOUD_RELEASE` in
`verify_chart_wiring.py` is the CI render name; `fullname` is `<release>-<name>`. If the cloud
release is named differently, re-run the diff above with the real name.
