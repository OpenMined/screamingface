---
ticket: OME-753
stack: repo
status: in_review
started: 2026-08-05
finished:
---

# OME-753 — regenerate uv locks inside the release-please job

## Intent

release-please bumps `version` in a package's `pyproject.toml` but never regenerates the uv
lockfiles that record that version. `url4-cloud-tests` runs `uv lock --check` as its first
step, so every url4 / url4-cloud release PR fails before ruff, pyright, or pytest run, and
`main` goes red for the same reason once the release merges. Observed on PR #504
(`chore(main): release url4 1.2.0`); the same failure was patched by hand twice already
(`f2b46c06`, `9061f40f`). Make the release PR correct when it is opened, and make the drift
visible everywhere instead of only in a neighbouring app's lane.

## Planned changes

- `.github/workflows/release-please.yml` — after the release-please action, a step that
  re-locks every affected uv workspace on each open release branch and pushes the amend
  commit with `RELEASE_PAT`.
- `.github/workflows/url4-tests.yml` — add `uv lock --check` before `uv sync`.
- `.github/workflows/aigateway-tests.yml`, `.github/workflows/scoreboard-tests.yml` — same
  guard.
- `docs/tasks/2026-08-05-ome-753-release-please-uv-locks.md` — mirror.

## Test plan

CI-config work — no unit tests. Verification is behavioural:

- `uv lock --check` fails on a version bump without a re-lock (reproduced by PR #504).
- The re-lock step is a no-op when the locks are already current (idempotent).
- `uv lock --check` passes in every workflow that gains the guard, on `origin/main` as-is.
- The lock-sync step must not run for non-release pushes.

## Acceptance

- A release PR for `url4` / `url4-cloud` / `aigateway` / `scoreboard` opens with its uv locks
  already regenerated, and the checks are green without human intervention.
- The lock-sync push retriggers the branch's checks (PAT, not `GITHUB_TOKEN`).
- Every Python app workflow verifies its lockfile is current before syncing.
- `uv lock --check` is not relaxed or scoped off anywhere.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `.github/scripts/sync_release_locks.py` — the lock-sync
  logic lives in a script (the `.github/scripts/verify_chart_wiring.py` convention) rather
  than inline in the `run:` block, so branch names never reach a shell and each release
  branch is re-locked in its own `git worktree` instead of switching the job's checkout.
- **Commits:** see the PR.
- **Gates:**
  - `uv lock --check` passes in all four workspaces (`apps/aigateway`, `apps/scoreboard`,
    `apps/url4-cloud`, `packages/url4`) on `origin/main`, so the three new guards are green
    from the start.
  - `ruff check` + `ruff format --check` clean on the new script.
  - The four touched workflows parse as YAML.
  - End-to-end rehearsal against a local bare clone acting as `origin`: a branch carrying
    only the `packages/url4` 1.1.0 → 1.2.0 bump was re-locked to exactly the two lockfiles
    that record that version (`packages/url4/uv.lock`, `apps/url4-cloud/uv.lock`, 3 lines),
    committed, and pushed. `uv lock --check` then passed in all four workspaces on the
    pushed branch. A second run reported "lockfiles already current" and pushed nothing;
    empty and `[]` payloads exit 0 without touching the repo.
- **Deviations:** every workspace is re-locked, not only the released one — the churn
  crosses workspace boundaries (releasing `packages/url4` invalidates
  `apps/url4-cloud/uv.lock`), and an unaffected workspace re-locks to a no-op.
- **Not covered:** the step fires on `prs_created`, so an already-open release PR is only
  healed the next time release-please updates it. PR #504 needs a one-off re-lock pushed to
  its branch.
