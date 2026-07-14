# packages/url4 — CI, coverage & release-please conformity spec

**Ticket:** OME-397 (folded in — see `docs/work/2026-07-14-OME-397-url4-ci-coverage-integration.md`)

## Problem

`packages/url4` landed under OME-397 with its own `pyproject.toml` test/coverage config
(pytest, ruff, pyright, `pytest-cov`) but nothing wiring it into the repo's actual CI/CD or
SDLC gate machinery:

- No `.github/workflows/url4-tests.yml` — pushes/PRs touching `packages/url4/**` trigger no
  checks at all today.
- No entry in `.claude/sdlc.local.md` — the `sdlc-python` loop's `run_gates.py` doesn't know
  about a `url4` stack, so gates are run manually (confirmed stale note in
  `docs/work/2026-07-13-no-ticket-url4-sdk-facades.md:3`).
- No entry in `release-please-config.json` — no automated version-bump/CHANGELOG PR on merge.
- `packages/url4/tests/` is flat (individual `test_*.py` files + a `tests/spec/` subdir),
  unlike the apps' `tests/unit/` convention.

This was explicitly named as deferred, out-of-scope follow-up in OME-397's own plan and
ledger (`docs/plan/2026-07-11-url4-package-v1.md:36-38`,
`docs/work/2026-07-11-OME-397-url4-package-v1.md:64-65`), and is called out generically in the
`working-in-this-repo` skill's 6-step "adding a new component" checklist. This spec defines
what "conformity" means for url4 specifically, given what the two existing components
(`apps/aigateway`, `apps/scoreboard`) actually have — not an idealized checklist.

## Reference: what conformity means today

Both existing Python components share one CI shape (`.github/workflows/aigateway-tests.yml`,
`.github/workflows/scoreboard-tests.yml`):

```
uv sync
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest --tb=short --junitxml=results.xml \
  --cov=<module> --cov-report=xml:coverage.xml --cov-report=term-missing \
  --cov-fail-under=80 -v
```

...plus `dorny/test-reporter` (GitHub check annotations) and `orgoro/coverage` (PR comment,
80% threshold, PR-only). Both are path-filtered to their own `apps/<name>/**` and self-trigger
on their own workflow file changing. `apps/aigateway` additionally runs a 3.12/3.13 matrix and
a `not live and not needs_postgres` marker split — neither applies to url4 (no live upstream
calls, no Postgres). `apps/scoreboard` runs single-version 3.12 — the pattern url4 follows,
since `requires-python = ">=3.12"` gives no reason for a matrix.

`.claude/sdlc.local.md` registers each component as a `stacks[]` entry (root, skill, gates) so
the `sdlc-python` loop's gate runner exercises it automatically instead of by hand.

`release-please-config.json` currently only registers `apps/aigateway`
(`release-type: python`, `version-file` pointing at its `pyproject.toml`). `apps/scoreboard`
has a release workflow (`release-scoreboard.yml`) but is **not** in `release-please-config.json`
— a pre-existing gap in scoreboard, not a pattern to copy for url4. url4 follows aigateway's
complete pattern instead (decided in conversation): a `release-please-config.json` entry for
version-bump/CHANGELOG automation, matched to aigateway's field shape.

## Decisions (settled in conversation, with rationale)

1. **CODEOWNERS / dependabot: out of scope.** Neither file exists anywhere in this repo —
   not at the root, not for aigateway, not for scoreboard. Creating them for url4 alone would
   invent unreviewed repo-wide convention as a side effect of a package-conformity task, not
   mirror an existing pattern. Left as a genuinely separate, repo-wide decision.

2. **No package-publish step.** Neither `release-aigateway.yml` nor `release-scoreboard.yml`
   publishes a Python package anywhere — both build only Docker images + Helm charts, which
   don't apply to a library (`packages/url4` currently has zero consumers; the one apparent
   consumer, `apps/server`, was removed from `main` on 2026-07-08 as part of the legacy
   teardown — confirmed via `git cat-file -e main:apps/server/pyproject.toml` failing). No
   PyPI, private index, or `uv publish` precedent exists in the repo at all. Registering
   `release-please-config.json` gets version-bump automation without inventing a publish
   target; an actual index (public PyPI, since this is OpenMined open-source, or otherwise) is
   a separate future decision, not made here.

3. **Test layout: reorganize to match the apps' convention.** Move the flat `test_*.py` files
   under `packages/url4/tests/` into `tests/unit/`; keep `tests/spec/` as its own subdir
   (it's already a coherent grouping — spec-conformance tests against the url4 grammar spec,
   distinct from unit tests of individual modules). `[tool.pytest.ini_options] testpaths =
   ["tests"]` in `packages/url4/pyproject.toml` already points at the directory, not
   individual files, so pytest's recursive discovery should need no config change — verify
   this holds (in particular that `conftest.py` fixtures, which currently sit at
   `tests/conftest.py`, still apply to `tests/unit/**` — pytest conftest scoping is by
   directory ancestry, so this is expected to just work, but the plan verifies it rather than
   assuming it).

4. **No new Python version matrix.** Single 3.12, matching scoreboard and url4's own
   `requires-python`.

5. **Coverage gate: 95%, not the repo's usual 80%.** Explicit instruction mid-session,
   after the initial 80%-conformity plan was already approved and partway implemented.
   Actual coverage after the test-directory reorg was 92.47%, below 95%, so this unit also
   added targeted new tests (not a threshold-only change) to close the gap — see the
   Coverage gap-closing subsection below. `apps/aigateway`/`apps/scoreboard` remain at 80%;
   this is url4-specific, not a repo-wide bar raise.

## Target changes

### `.github/workflows/url4-tests.yml` (new)

Structurally mirrors `scoreboard-tests.yml` (single Python version, no live/postgres markers,
no enterprise-import guard — none of those concerns exist for url4):

- Trigger: push/PR on `packages/url4/**` or the workflow file itself; `workflow_dispatch`.
- `working-directory: packages/url4`, Python 3.12, `uv sync`.
- Lint/typecheck: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- Test: `uv run pytest --tb=short --junitxml=results.xml --cov=url4
  --cov-report=xml:coverage.xml --cov-report=term-missing --cov-fail-under=95 -v`.
- `dorny/test-reporter` on `results.xml`; `orgoro/coverage` on `coverage.xml` (PR-only, 95%
  threshold) — same actions/versions as the existing two workflows, but a deliberately higher
  bar: raised from the repo's usual 80% to 95% by explicit instruction mid-session, not a copy
  error. Do not "correct" this back to 80% to match aigateway/scoreboard.

### `.claude/sdlc.local.md`

New `stacks[]` entry:

```yaml
- name: url4
  root: packages/url4
  skill: sdlc-python
  test_globs: ["tests/**"]
  gates:
    - uv run ruff check
    - uv run ruff format --check
    - uv run pyright
    - uv run pytest --cov=url4 --cov-fail-under=95 -q
```

No new `## url4 (python)` invariants subsection is needed yet — url4 has no credential/secret
or public-artifact-allowlist invariant comparable to aigateway/scoreboard's; add one later if
a real invariant emerges.

### `release-please-config.json`

New `packages.["packages/url4"]` entry mirroring the `apps/aigateway` entry:

```json
"packages/url4": {
  "release-type": "python",
  "package-name": "url4",
  "component": "url4",
  "tag-separator": "-",
  "include-component-in-tag": true,
  "version-file": "packages/url4/pyproject.toml"
}
```

### `packages/url4/tests/`

Move flat `test_*.py` files into `tests/unit/`; `tests/spec/` unchanged. No production code
touched. Re-run the full suite after the move to confirm nothing broke (import paths inside
test files are relative to the installed `url4` package, not to the test file's own location,
so the move is expected to be inert — verified, not assumed).

## Non-goals

- CODEOWNERS, dependabot.yml (repo-wide decisions, not made here).
- A real package publish/release target (PyPI or otherwise).
- Any change to `packages/url4/src/**` (production code untouched).
- A Python-version test matrix for url4.

## Acceptance

See `docs/work/2026-07-14-OME-397-url4-ci-coverage-integration.md` § Acceptance.
