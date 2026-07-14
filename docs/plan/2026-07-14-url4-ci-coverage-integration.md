# packages/url4 CI/coverage/release-please conformity — Implementation Plan

**Ticket:** OME-397 (folded in) · **Spec:** `docs/spec/2026-07-14-url4-ci-coverage-integration-spec.md`

**Goal:** Wire `packages/url4` into the repo's actual CI, gate-runner, and release-automation
machinery the same way `apps/aigateway`/`apps/scoreboard` already are — closing the
"new-component coordination contract" gap OME-397 explicitly deferred.

**Architecture:** Config/workflow-only unit — no production code in `packages/url4/src/`
changes. Test files move (flat → `tests/unit/`), don't change content.

**Tech stack:** GitHub Actions YAML · `.claude/sdlc.local.md` (YAML frontmatter) ·
`release-please-config.json` (JSON) · pytest/uv (Python ≥3.12).

## Steps

- [ ] **Reorganize tests.** `git mv` each flat `packages/url4/tests/test_*.py` into
      `packages/url4/tests/unit/`; leave `tests/spec/`, `tests/conftest.py` in place. Run
      `uv run pytest -q` from `packages/url4` to confirm full collection + pass, no import
      breakage, `conftest.py` fixtures still apply.
- [ ] **CI workflow.** Add `.github/workflows/url4-tests.yml` per the spec's target-changes
      section, copying `scoreboard-tests.yml` structurally (path filter, `working-directory`,
      single Python 3.12, `uv sync`, ruff/pyright/pytest steps, test-reporter + coverage PR
      comment steps). Adjust module name (`--cov=url4`) and paths only.
- [ ] **sdlc.local.md.** Add the `url4` stack entry to `stacks[]` in `.claude/sdlc.local.md`
      (root, skill, test_globs, gates) exactly as specified.
- [ ] **release-please-config.json.** Add the `packages/url4` entry to `packages{}`, matching
      the `apps/aigateway` entry shape (release-type, package-name/component, tag-separator,
      include-component-in-tag, version-file).
- [ ] **Coverage gate raised to 95% (explicit instruction mid-session, after this plan was
      already approved and partway implemented).** Not a copy error — url4 deliberately
      diverges from aigateway/scoreboard's 80%. Actual coverage after the test reorg was
      92.47%, below 95%, so this step also required writing new tests (dispatched to four
      parallel implementers, one per test file, each briefed from a scout's line-by-line
      coverage-gap analysis of the corresponding source file) to close the gap before the
      gate could go green — not just editing the threshold number.
- [ ] **Gates.** From `packages/url4`: `uv sync`, `uv run ruff check`, `uv run ruff format
      --check`, `uv run pyright`, `uv run pytest --cov=url4 --cov-report=term-missing
      --cov-fail-under=95 -q`. All green before commit — this also proves the new CI
      workflow's commands are correct before they ever run in GitHub Actions (workflow syntax
      itself isn't locally testable without `act`; visual review substitutes).
- [ ] **Commit.** Conventional commit(s), body `Refs: OME-397`; no `Co-Authored-By`. Do not
      push, do not commit to `main`.
- [ ] **Close.** Fill the ledger Outcome (`docs/work/2026-07-14-OME-397-url4-ci-coverage-
      integration.md`). No Linear update this round (explicit instruction — Linear MCP/CLI
      both unavailable in this session; folded into OME-397 without a status change).

## Non-goals / follow-ups

- CODEOWNERS, `.github/dependabot.yml` — no repo-wide precedent; separate decision.
- Python package publish target (PyPI or otherwise) — no repo precedent; separate decision.
- `apps/aigateway` also runs a 3.12/3.13 matrix and postgres/live markers — deliberately not
  mirrored; url4 has neither concern.

## Risks

- **Test-move breakage.** `tests/unit/` files losing access to `tests/conftest.py` fixtures or
  relative-path test assets. Mitigated by running the full suite immediately after the `git
  mv`, before touching any CI file.
- **Workflow YAML can't be exercised locally.** No `act`/local GitHub Actions runner in this
  repo's toolchain today. Mitigated by copying the two proven, currently-green workflows
  structurally rather than hand-writing from scratch, and a careful diff review against
  `scoreboard-tests.yml`.
- **Coverage threshold surprise.** If url4's current suite doesn't already clear 80% coverage,
  `--cov-fail-under=80` would fail on first CI run. Mitigated by running the exact gate
  command locally before committing (see Gates step) — if it fails, that's a real finding to
  raise, not a bar to quietly lower.
